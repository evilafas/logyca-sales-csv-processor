import uuid

from sqlalchemy.orm import Session

from app.db.models import Job


def create_job(db: Session, filename: str, blob_url: str) -> Job:
    """Create a new job with PENDING status."""
    job = Job(
        id=uuid.uuid4(),
        filename=filename,
        blob_url=blob_url,
        status="PENDING",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> Job | None:
    """Get a job by ID."""
    return db.query(Job).filter(Job.id == job_id).first()


def update_job_status(db: Session, job_id: str, status: str, error_message: str = None, records_processed: int = None) -> None:
    """Update job status and optional fields."""
    updates = {"status": status}
    if error_message is not None:
        updates["error_message"] = error_message
    if records_processed is not None:
        updates["records_processed"] = records_processed
    db.query(Job).filter(Job.id == job_id).update(updates)
    db.commit()
