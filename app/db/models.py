import uuid

from sqlalchemy import Column, String, Integer, Numeric, Date, DateTime, BigInteger, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    status = Column(String(20), nullable=False, default="PENDING")
    filename = Column(String(255), nullable=False)
    blob_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    error_message = Column(String, nullable=True)
    records_processed = Column(Integer, default=0)


class Sale(Base):
    __tablename__ = "sales"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    total = Column(Numeric(14, 2), nullable=False)


class SalesDailySummary(Base):
    __tablename__ = "sales_daily_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, unique=True, nullable=False)
    total_sales = Column(Numeric(16, 2), nullable=False)
    record_count = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
