# AI-Powered Transaction Processing Pipeline

An asynchronous backend API to process, clean, and analyze raw financial transaction data. It uses FastAPI for the API layer, PostgreSQL for storing structured jobs and transaction records, Redis as a message broker/backend, Celery for background queue processing, and Gemini 1.5 Flash for transaction classification and narrative summary reports.

---

## Architecture & Tech Stack
- **FastAPI:** High-performance web framework for Python.
- **Uv:** Astral's extremely fast Python package and environment installer.
- **PostgreSQL 16:** Relational database for storing Job metadata, Cleaned Transactions, and Job Summaries.
- **Celery + Redis:** Asynchronous task queue and broker for background execution.
- **Gemini 1.5 Flash:** LLM integration via `google-generativeai` SDK for category classification and analytical narrative synthesis.
- **Docker & Docker Compose:** Containerization for all services, enabling one-command setup.

---

## Project Structure
```text
transaction_pipeline/
├── app/
│   ├── __init__.py
│   ├── config.py              # Configuration & Environment loading
│   ├── main.py                # FastAPI routes & lifespan setup
│   ├── db/
│   │   ├── __init__.py
│   │   ├── postgressdb.py     # SQLAlchemy connection & session utility
│   │   └── models.py          # Job, Transaction, and JobSummary SQL models
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── schemas.py         # Pydantic schemas for serialization/validation
│   ├── services/
│   │   ├── __init__.py
│   │   ├── cleaning.py        # Date parsing, currency stripping, & deduplication
│   │   ├── anomalies.py       # 3x median statistical outlier & USD merchant checks
│   │   └── llm_service.py     # Gemini SDK connection, backoff retry, & mock fallback
│   └── tasks/
│       ├── __init__.py
│       ├── celery_app.py      # Celery broker configuration
│       └── pipeline_tasks.py  # Asynchronous workflow coordination
├── tests/
│   ├── __init__.py
│   └── test_pipeline.py       # Unit tests for data cleaning & heuristics
├── Dockerfile                 # Multi-stage slim Docker image utilizing uv
├── docker-compose.yml         # Dev cluster orchestrator (db, redis, web, worker)
├── pyproject.toml             # Python 3.11 dependency manifest
├── .python-version            # 3.11 version declaration
├── .env                       # App environmental variables
├── generate_sample_csv.py     # Script to generate dummy transactions for testing
├── transactions.csv           # Sample CSV file generated for evaluation
└── README.md                  # Setup & usage instructions
```

---

## Processing Pipeline Workflow

When a job is uploaded:
1. **Data Cleaning:** Normalizes dates (ISO 8601 `YYYY-MM-DD`), strips currency symbols (like `$`), converts amount to float, upper-cases status (`SUCCESS`, `PENDING`, `FAILED`), sets missing categories to `"Uncategorised"`, and drops exact duplicate rows.
2. **Anomaly Detection:** 
   - **Statistical Outliers:** Flags transactions where the amount exceeds $3\times$ the account's median spend.
   - **Domain Anomaly:** Flags transactions processed in `USD` containing domestic-only merchant brands (`Swiggy`, `Ola`, `IRCTC`).
3. **LLM Classification:** Selects transactions that lack categories and calls Gemini 1.5 Flash in batches of 20 to map them into: `Food`, `Shopping`, `Travel`, `Transport`, `Utilities`, `Cash Withdrawal`, `Entertainment`, or `Other`.
4. **LLM Summary Report:** Synthesizes metrics (spend sum by currency, top merchants, anomaly count) alongside transaction records, calling Gemini to construct a 2-3 sentence narrative review and risk evaluation (`low`, `medium`, `high`).
5. **Backoff Retry & Fallback:** All LLM calls employ exponential backoff retry logic (up to 3 times). If the Gemini API is unreachable, has exhausted its quota, or is missing the `GEMINI_API_KEY`, the task falls back to local heuristic classifiers and mathematical summaries, marking the batch as `llm_failed = true` without crashing the processing job.

---

## Setup & Running

Ensure you have Docker and Docker Compose installed.

### 1. Configure the environment
A template `.env` is already configured in the folder. If you wish to use the Gemini LLM features, provide your Gemini API key:
```env
# e:\Alemeno\transaction_pipeline\.env
GEMINI_API_KEY=your_actual_gemini_api_key
```
*Note: If no API key is specified, the pipeline will gracefully run using the built-in local heuristics and analytical summaries.*

### 2. Start the application
Run the following command from the root of the `transaction_pipeline` folder:
```bash
docker compose up --build
```
This builds and boots up four containers:
- **`pipeline_db`**: PostgreSQL on port `5432`
- **`pipeline_redis`**: Redis on port `6379`
- **`pipeline_web`**: FastAPI Web API on port `8000`
- **`pipeline_worker`**: Celery Worker processing jobs

---

## API Endpoints & Testing Commands

You can test the system using the sample file `transactions.csv` generated in the folder.

### 1. Upload transactions CSV
Upload a CSV to the pipeline to enqueue it:
```bash
curl -X POST -F "file=@transactions.csv" http://localhost:8000/jobs/upload
```
**Response:**
```json
{
  "job_id": "b3e34b9d-5a8b-49d7-8d9e-10b2a3c4d5e6",
  "status": "pending",
  "filename": "transactions.csv"
}
```

### 2. Check Job Status
Poll the job status using the `job_id` returned:
```bash
curl http://localhost:8000/jobs/b3e34b9d-5a8b-49d7-8d9e-10b2a3c4d5e6/status
```
**Response (while processing):**
```json
{
  "job_id": "b3e34b9d-5a8b-49d7-8d9e-10b2a3c4d5e6",
  "status": "processing",
  "filename": "transactions.csv",
  "row_count_raw": 89,
  "row_count_clean": null,
  "created_at": "2026-06-19T10:45:00",
  "completed_at": null,
  "error_message": null,
  "summary": null
}
```
**Response (when completed):**
```json
{
  "job_id": "b3e34b9d-5a8b-49d7-8d9e-10b2a3c4d5e6",
  "status": "completed",
  "filename": "transactions.csv",
  "row_count_raw": 89,
  "row_count_clean": 86,
  "created_at": "2026-06-19T10:45:00",
  "completed_at": "2026-06-19T10:45:15",
  "error_message": null,
  "summary": {
    "total_spend_inr": 18450.00,
    "total_spend_usd": 120.00,
    "anomaly_count": 3,
    "risk_level": "medium"
  }
}
```

### 3. Fetch Full Job Results
Fetch the full transaction details, anomalies, spend category metrics, and LLM text narrative:
```bash
curl http://localhost:8000/jobs/b3e34b9d-5a8b-49d7-8d9e-10b2a3c4d5e6/results
```
**Response:**
```json
{
  "job_id": "b3e34b9d-5a8b-49d7-8d9e-10b2a3c4d5e6",
  "status": "completed",
  "filename": "transactions.csv",
  "row_count_raw": 89,
  "row_count_clean": 86,
  "summary": {
    "total_spend_inr": 18450.0,
    "total_spend_usd": 120.0,
    "top_merchants": ["Swiggy", "Amazon", "IRCTC"],
    "anomaly_count": 3,
    "narrative": "The transaction log details a total expenditure of INR 18450.00 and USD 120.00. Top merchants include Swiggy, Amazon, IRCTC. A total of 3 transactions were flagged as anomalous, indicating a medium-risk spend pattern.",
    "risk_level": "medium"
  },
  "category_breakdown": {
    "Food": {
      "INR": 4850.0,
      "USD": 20.0
    },
    "Shopping": {
      "INR": 6200.0,
      "USD": 45.0
    },
    "Travel": {
      "INR": 3400.0,
      "USD": 55.0
    }
  },
  "transactions": [
    {
      "id": 1,
      "txn_id": "TXN001",
      "date": "2026-06-19",
      "merchant": "Swiggy",
      "amount": 450.0,
      "currency": "INR",
      "status": "SUCCESS",
      "category": "Food",
      "account_id": "ACC100",
      "is_anomaly": false,
      "anomaly_reason": null,
      "llm_category": null,
      "llm_failed": false
    }
  ],
  "anomalies": [
    {
      "id": 11,
      "txn_id": "TXN011",
      "date": "2026-06-08",
      "merchant": "Swiggy",
      "amount": 950.0,
      "currency": "INR",
      "status": "SUCCESS",
      "category": "Food",
      "account_id": "ACC400",
      "is_anomaly": true,
      "anomaly_reason": "Amount (950.0) exceeds 3x account median (150.00)",
      "llm_category": "Food",
      "llm_failed": false
    }
  ]
}
```

### 4. List All Jobs
List all upload records with filtering support:
```bash
curl http://localhost:8000/jobs?status=completed
```

---

## Running Unit Tests Locally
To run the test suite locally (without Docker):
1. Install dependencies: `uv pip install -r pyproject.toml` or `pip install .`
2. Run pytest:
```bash
pytest
```
