from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime

class JobUploadResponse(BaseModel):
    job_id: str
    status: str
    filename: str

    class Config:
        from_attributes = True

class HighLevelSummary(BaseModel):
    total_spend_inr: float
    total_spend_usd: float
    anomaly_count: int
    risk_level: Optional[str] = None

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    filename: str
    row_count_raw: Optional[int] = None
    row_count_clean: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    summary: Optional[HighLevelSummary] = None

class TransactionSchema(BaseModel):
    id: int
    txn_id: Optional[str] = None
    date: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    account_id: Optional[str] = None
    is_anomaly: bool
    anomaly_reason: Optional[str] = None
    llm_category: Optional[str] = None
    llm_failed: bool

    class Config:
        from_attributes = True

class JobSummarySchema(BaseModel):
    total_spend_inr: float
    total_spend_usd: float
    top_merchants: List[str]
    anomaly_count: int
    narrative: Optional[str] = None
    risk_level: Optional[str] = None

    class Config:
        from_attributes = True

class JobResultsResponse(BaseModel):
    job_id: str
    status: str
    filename: str
    row_count_raw: Optional[int] = None
    row_count_clean: Optional[int] = None
    summary: Optional[JobSummarySchema] = None
    category_breakdown: Dict[str, Dict[str, float]]
    transactions: List[TransactionSchema]
    anomalies: List[TransactionSchema]

    class Config:
        from_attributes = True

class JobListItem(BaseModel):
    job_id: str
    status: str
    filename: str
    row_count_raw: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
