import csv
import io
import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Job
from app.models.schemas import DailySummaryResponse, JobDetailResponse, JobResponse, UploadResponse
from app.services import blob_service, queue_service, job_service

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
REQUIRED_CSV_COLUMNS = {"date", "product_id", "quantity", "price"}


def _validate_csv_headers(file: UploadFile) -> None:
    """Read the first line and validate CSV has the required columns."""
    first_line = file.file.readline().decode("utf-8").strip()
    file.file.seek(0)  # Reset for subsequent reads
    columns = {c.strip() for c in first_line.split(",")}
    missing = REQUIRED_CSV_COLUMNS - columns
    if missing:
        raise HTTPException(status_code=400, detail=f"CSV missing required columns: {', '.join(missing)}")


@router.post("/upload", response_model=UploadResponse)
def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Validate file extension
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")

    # Validate content type
    if file.content_type and file.content_type not in ("text/csv", "application/octet-stream"):
        raise HTTPException(status_code=400, detail=f"Invalid content type: {file.content_type}")

    # Validate file size
    file.file.seek(0, 2)  # Seek to end
    size = file.file.tell()
    file.file.seek(0)  # Reset
    if size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)} MB")
    if size == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Validate CSV headers
    _validate_csv_headers(file)

    blob_name = f"{uuid.uuid4()}_{file.filename}"

    # 1. Upload to Azure Blob Storage
    try:
        blob_url = blob_service.upload_blob(blob_name, file)
    except Exception as e:
        logger.error(f"Blob upload failed: {e}")
        raise HTTPException(status_code=502, detail="Failed to upload file to storage")

    # 2. Create job record in DB
    job = job_service.create_job(db, filename=file.filename, blob_url=blob_url)

    # 3. Send message to queue for async processing
    try:
        queue_service.send_message(job_id=str(job.id), blob_name=blob_name)
    except Exception as e:
        logger.error(f"Queue send failed: {e}")
        job_service.update_job_status(db, str(job.id), "FAILED", error_message="Failed to enqueue processing")
        raise HTTPException(status_code=502, detail="Failed to enqueue file for processing")

    return UploadResponse(job_id=str(job.id), message="File uploaded. Processing started.")


@router.get("/job/{job_id}", response_model=JobResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job_id format")

    job = job_service.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse(job_id=str(job.id), status=job.status)


@router.get("/jobs/completed", response_model=List[JobDetailResponse])
def get_completed_jobs(db: Session = Depends(get_db)):
    """List all completed jobs. Used by N8N workflow."""
    jobs = db.query(Job).filter(Job.status == "COMPLETED").all()
    return [
        JobDetailResponse(
            job_id=str(j.id),
            status=j.status,
            filename=j.filename,
            records_processed=j.records_processed or 0,
            created_at=j.created_at,
        )
        for j in jobs
    ]


@router.post("/summary/calculate", response_model=List[DailySummaryResponse])
def calculate_daily_summary(db: Session = Depends(get_db)):
    """Calculate and upsert daily sales summary. Called by N8N workflow."""
    db.execute(text("""
        INSERT INTO sales_daily_summary (date, total_sales, record_count, updated_at)
        SELECT date, SUM(total), COUNT(*), NOW()
        FROM sales
        GROUP BY date
        ON CONFLICT (date) DO UPDATE SET
            total_sales = EXCLUDED.total_sales,
            record_count = EXCLUDED.record_count,
            updated_at = NOW()
    """))
    db.commit()

    rows = db.execute(text(
        "SELECT date, total_sales, record_count FROM sales_daily_summary ORDER BY date"
    )).fetchall()

    return [
        DailySummaryResponse(date=r[0], total_sales=float(r[1]), record_count=r[2])
        for r in rows
    ]
