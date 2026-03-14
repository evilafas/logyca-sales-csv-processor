from datetime import date, datetime

from pydantic import BaseModel


class JobResponse(BaseModel):
    job_id: str
    status: str


class JobDetailResponse(BaseModel):
    job_id: str
    status: str
    filename: str
    records_processed: int
    created_at: datetime


class UploadResponse(BaseModel):
    job_id: str
    message: str


class DailySummaryResponse(BaseModel):
    date: date
    total_sales: float
    record_count: int
