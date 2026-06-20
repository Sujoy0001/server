import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from server.app.db.postgressdb import engine, Base, get_db
from server.app.db.models import Job, Transaction, JobSummary
from server.app.schemas import schemas
from server.app.tasks.pipeline_tasks import process_transaction_file

# Initialize DB tables on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="AI-Powered Transaction Processing API",
    description="Asynchronously clean, analyze, and summarize financial transactions using Celery, Postgres, Redis, and Gemini.",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
def read_root():
    return {
        "message": "AI-Powered Transaction Processing Pipeline API is running.",
        "docs": "/docs"
    }

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
        
    return {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else "disconnected"
    }

@app.post("/jobs/upload", response_model=schemas.JobUploadResponse, status_code=201)
async def upload_transactions(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Accepts a transactions CSV file, validates its format, creates a pending job in the database,
    and enqueues the processing pipeline worker.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
        
    try:
        content = await file.read()
        file_content_str = content.decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read CSV content: {str(e)}")

    # Create a new Job record
    new_job = Job(
        filename=file.filename,
        status="pending"
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # Enqueue background processing
    process_transaction_file.delay(new_job.id, file_content_str)

    return {
        "job_id": new_job.id,
        "status": new_job.status,
        "filename": new_job.filename
    }

@app.get("/jobs/{job_id}/status", response_model=schemas.JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """
    Retrieves the status of a job. If completed, includes high-level statistics.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    summary_data = None
    if job.status == "completed" and job.summary:
        summary_data = {
            "total_spend_inr": job.summary.total_spend_inr,
            "total_spend_usd": job.summary.total_spend_usd,
            "anomaly_count": job.summary.anomaly_count,
            "risk_level": job.summary.risk_level
        }

    return {
        "job_id": job.id,
        "status": job.status,
        "filename": job.filename,
        "row_count_raw": job.row_count_raw,
        "row_count_clean": job.row_count_clean,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "error_message": job.error_message,
        "summary": summary_data
    }

@app.get("/jobs/{job_id}/results", response_model=schemas.JobResultsResponse)
def get_job_results(job_id: str, db: Session = Depends(get_db)):
    """
    Retrieves the full processing results for a job, including the cleaned transaction list,
    flagged anomalies, category spending breakdown, and LLM-generated narrative summary.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"Job results are not available. Job status is currently: '{job.status}'"
        )

    # Group transactions into full cleaned list and anomalies
    cleaned_txs = job.transactions
    anomalies = [tx for tx in cleaned_txs if tx.is_anomaly]

    # Calculate category spend breakdown: {"Category": {"Currency": Amount}}
    category_breakdown = {}
    for tx in cleaned_txs:
        cat = tx.category or "Uncategorised"
        curr = (tx.currency or "INR").upper()
        amt = tx.amount or 0.0
        
        if cat not in category_breakdown:
            category_breakdown[cat] = {}
        category_breakdown[cat][curr] = category_breakdown[cat].get(curr, 0.0) + amt

    # Prepare summary data schema
    summary_data = None
    if job.summary:
        summary_data = {
            "total_spend_inr": job.summary.total_spend_inr,
            "total_spend_usd": job.summary.total_spend_usd,
            "top_merchants": job.summary.top_merchants or [],
            "anomaly_count": job.summary.anomaly_count,
            "narrative": job.summary.narrative,
            "risk_level": job.summary.risk_level
        }

    return {
        "job_id": job.id,
        "status": job.status,
        "filename": job.filename,
        "row_count_raw": job.row_count_raw,
        "row_count_clean": job.row_count_clean,
        "summary": summary_data,
        "category_breakdown": category_breakdown,
        "transactions": cleaned_txs,
        "anomalies": anomalies
    }

@app.get("/jobs", response_model=List[schemas.JobListItem])
def list_jobs(status: Optional[str] = Query(None, description="Filter jobs by status"), db: Session = Depends(get_db)):
    """
    Lists all jobs. Supports filtering by status (e.g. pending, processing, completed, failed).
    """
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status.lower().strip())
        
    jobs = query.order_by(Job.created_at.desc()).all()
    
    result = []
    for job in jobs:
        result.append({
            "job_id": job.id,
            "status": job.status,
            "filename": job.filename,
            "row_count_raw": job.row_count_raw,
            "created_at": job.created_at
        })
        
    return result
