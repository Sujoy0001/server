import json
import logging
from datetime import datetime
import pandas as pd
from sqlalchemy import func

from app.tasks.celery_app import celery_app
from app.db.postgressdb import SessionLocal
from app.db.models import Job, Transaction, JobSummary
from app.services.cleaning import clean_csv
from app.services.anomalies import detect_anomalies
from app.services.llm_service import classify_transactions_batch, generate_narrative_summary

logger = logging.getLogger(__name__)

@celery_app.task(name="app.tasks.process_transaction_file")
def process_transaction_file(job_id: str, file_content_str: str) -> str:
    """
    Asynchronous task to run the transaction processing pipeline.
    `file_content_str` is the raw CSV data passed as a string.
    """
    logger.info(f"Starting processing pipeline for job {job_id}")
    db = SessionLocal()
    
    try:
        # 1. Update status to processing
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found in database.")
            return f"Job {job_id} not found"
            
        job.status = "processing"
        db.commit()

        # Convert string content to bytes for pandas reader
        file_bytes = file_content_str.encode('utf-8')
        
        # Calculate raw row count (approximate lines minus header)
        raw_rows = len(file_content_str.strip().split('\n')) - 1
        if raw_rows < 0:
            raw_rows = 0
        job.row_count_raw = raw_rows
        db.commit()

        # 2. Data Cleaning
        cleaned_df = clean_csv(file_bytes)
        clean_rows_count = len(cleaned_df)
        job.row_count_clean = clean_rows_count
        db.commit()

        if cleaned_df.empty:
            logger.info("Cleaned dataset is empty.")
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()
            return f"Job {job_id} finished (empty dataset)"

        # 3. Anomaly Detection
        processed_df = detect_anomalies(cleaned_df)

        # Convert to records to proceed with LLM processing and DB storage
        transactions_data = processed_df.to_dict(orient="records")

        # 4. LLM Classification (Batching uncategorized transactions)
        uncat_txns = [t for t in transactions_data if t["category"].lower() == "uncategorised"]
        logger.info(f"Found {len(uncat_txns)} uncategorized transactions to classify.")

        batch_size = 20
        for i in range(0, len(uncat_txns), batch_size):
            batch = uncat_txns[i:i + batch_size]
            batch_payload = []
            for idx, tx in enumerate(batch):
                # Setup temp ID to map classifications back
                temp_id = f"temp_{i + idx}"
                tx["_temp_id"] = temp_id
                batch_payload.append({
                    "id": temp_id,
                    "merchant": tx.get("merchant"),
                    "amount": tx.get("amount"),
                    "currency": tx.get("currency"),
                    "notes": tx.get("notes")
                })
            
            # Call LLM service
            classifications, llm_failed = classify_transactions_batch(batch_payload)

            for tx in batch:
                temp_id = tx.get("_temp_id")
                category = classifications.get(temp_id)
                
                # If classification is returned, we update both category and llm_category
                if category:
                    tx["category"] = category
                    tx["llm_category"] = category
                else:
                    tx["llm_category"] = None
                
                tx["llm_failed"] = llm_failed
                tx["llm_raw_response"] = json.dumps(classifications)

        # 5. Save Transaction Records to Database
        db_transactions = []
        for tx in transactions_data:
            db_tx = Transaction(
                job_id=job_id,
                txn_id=tx.get("txn_id"),
                date=tx.get("date"),
                merchant=tx.get("merchant"),
                amount=tx.get("amount"),
                currency=tx.get("currency"),
                status=tx.get("status"),
                category=tx.get("category"),
                account_id=tx.get("account_id"),
                is_anomaly=bool(tx.get("is_anomaly", False)),
                anomaly_reason=tx.get("anomaly_reason"),
                llm_category=tx.get("llm_category"),
                llm_raw_response=tx.get("llm_raw_response"),
                llm_failed=bool(tx.get("llm_failed", False))
            )
            db.add(db_tx)
            db_transactions.append(db_tx)
        
        db.commit()

        # 6. Calculate JobSummary Statistics
        total_spend_inr = sum(t.get("amount", 0.0) for t in transactions_data if str(t.get("currency")).upper() == "INR")
        total_spend_usd = sum(t.get("amount", 0.0) for t in transactions_data if str(t.get("currency")).upper() == "USD")
        anomaly_count = sum(1 for t in transactions_data if t.get("is_anomaly", False))

        # Calculate top 3 merchants by sum of transaction amounts
        merchant_spending = {}
        for t in transactions_data:
            m = t.get("merchant", "Unknown")
            merchant_spending[m] = merchant_spending.get(m, 0.0) + t.get("amount", 0.0)
        
        top_merchants = sorted(merchant_spending, key=merchant_spending.get, reverse=True)[:3]

        stats = {
            "total_spend_inr": total_spend_inr,
            "total_spend_usd": total_spend_usd,
            "top_merchants": top_merchants,
            "anomaly_count": anomaly_count
        }

        # 7. LLM Narrative Summary
        summary_payload, summary_llm_failed = generate_narrative_summary(transactions_data, stats)

        db_summary = JobSummary(
            job_id=job_id,
            total_spend_inr=summary_payload.get("total_spend_inr", total_spend_inr),
            total_spend_usd=summary_payload.get("total_spend_usd", total_spend_usd),
            top_merchants=summary_payload.get("top_merchants", top_merchants),
            anomaly_count=summary_payload.get("anomaly_count", anomaly_count),
            narrative=summary_payload.get("narrative"),
            risk_level=summary_payload.get("risk_level", "low")
        )
        db.add(db_summary)

        # 8. Mark Job as Completed
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Job {job_id} successfully completed.")
        return f"Job {job_id} processed successfully"

    except Exception as e:
        logger.exception(f"Error occurred while processing job {job_id}")
        db.rollback()
        
        # Reload job in a clean transaction and mark as failed
        db_fail = SessionLocal()
        try:
            job_fail = db_fail.query(Job).filter(Job.id == job_id).first()
            if job_fail:
                job_fail.status = "failed"
                job_fail.error_message = str(e)
                job_fail.completed_at = datetime.utcnow()
                db_fail.commit()
        except Exception as fe:
            logger.error(f"Failed to set job status to failed: {fe}")
        finally:
            db_fail.close()
            
        return f"Job {job_id} failed: {e}"
        
    finally:
        db.close()
