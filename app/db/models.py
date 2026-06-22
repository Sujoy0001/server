import uuid
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON, func
from sqlalchemy.orm import relationship
from app.db.postgressdb import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    status = Column(String(50), default="pending", nullable=False)  # pending, processing, completed, failed
    row_count_raw = Column(Integer, nullable=True)
    row_count_clean = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    transactions = relationship("Transaction", back_populates="job", cascade="all, delete-orphan")
    summary = relationship("JobSummary", back_populates="job", uselist=False, cascade="all, delete-orphan")

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    txn_id = Column(String(100), nullable=True)
    date = Column(String(50), nullable=True)  # Normalized to ISO 8601 (YYYY-MM-DD)
    merchant = Column(String(255), nullable=True)
    amount = Column(Float, nullable=True)
    currency = Column(String(10), nullable=True)
    status = Column(String(50), nullable=True)
    category = Column(String(100), nullable=True)
    account_id = Column(String(100), nullable=True)
    is_anomaly = Column(Boolean, default=False, nullable=False)
    anomaly_reason = Column(Text, nullable=True)
    llm_category = Column(String(100), nullable=True)
    llm_raw_response = Column(Text, nullable=True)
    llm_failed = Column(Boolean, default=False, nullable=False)

    job = relationship("Job", back_populates="transactions")

class JobSummary(Base):
    __tablename__ = "job_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    total_spend_inr = Column(Float, default=0.0, nullable=False)
    total_spend_usd = Column(Float, default=0.0, nullable=False)
    top_merchants = Column(JSON, nullable=True)  # e.g., ["Merchant A", "Merchant B", "Merchant C"]
    anomaly_count = Column(Integer, default=0, nullable=False)
    narrative = Column(Text, nullable=True)
    risk_level = Column(String(20), nullable=True)  # low, medium, high

    job = relationship("Job", back_populates="summary")
