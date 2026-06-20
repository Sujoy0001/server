import os
import json
import time
import logging
import importlib
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    # For type checkers only; at runtime we'll attempt a dynamic import.
    import google.generativeai as genai  # type: ignore
else:
    try:
        genai = importlib.import_module("google.generativeai")
    except Exception:
        genai = None
        logger.warning("google.generativeai package is not installed; running in mock mode.")

# Initialize Gemini SDK if API key is provided and package is available
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
IS_MOCK_MODE = (
    not GEMINI_API_KEY
    or GEMINI_API_KEY == "your_gemini_api_key_here"
    or genai is None
)

if not IS_MOCK_MODE:
    genai.configure(api_key=GEMINI_API_KEY)

def parse_json_safety(text: str) -> dict:
    text = text.strip()
    # Remove markdown code block wrappers if present
    if text.startswith("```json"):
        text = text[7:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end+1])
            except Exception as e:
                logger.error(f"Failed parsing inner json: {e}")
        raise ValueError("Response was not a valid JSON object")

def call_gemini_with_retry(prompt: str, response_mime_type: str = "application/json") -> str:
    """
    Calls Gemini 1.5 Flash API with exponential backoff retry (up to 3 retries / 4 total attempts).
    """
    if IS_MOCK_MODE:
        raise ConnectionError("Gemini API key is not configured, running in mock mode.")

    model = genai.GenerativeModel("gemini-1.5-flash")
    
    # Exponential backoff parameters
    max_retries = 3
    base_delay = 2.0  # seconds

    for attempt in range(max_retries + 1):
        try:
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": response_mime_type}
            )
            return response.text
        except Exception as e:
            logger.warning(f"Gemini API call attempt {attempt + 1} failed: {e}")
            if attempt == max_retries:
                raise e
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
            
    raise ConnectionError("Failed to communicate with Gemini API after retries.")

def mock_classify(transactions: list[dict]) -> dict:
    """
    Rule-based mock classifier used as a fallback.
    """
    results = {}
    for tx in transactions:
        tx_id = str(tx.get("id"))
        merchant = str(tx.get("merchant", "")).lower()
        notes = str(tx.get("notes", "")).lower()

        if any(w in merchant for w in ["swiggy", "zomato", "starbucks", "cafe", "mcdonald", "food", "restaurant"]):
            cat = "Food"
        elif any(w in merchant for w in ["uber", "ola", "cab", "taxi", "metro"]):
            cat = "Transport"
        elif any(w in merchant for w in ["irctc", "flight", "hotel", "airways", "makemytrip", "travel"]):
            cat = "Travel"
        elif any(w in merchant for w in ["amazon", "flipkart", "walmart", "target", "nike", "shopping"]):
            cat = "Shopping"
        elif any(w in merchant for w in ["electricity", "water", "bill", "airtel", "jio", "power", "utility"]):
            cat = "Utilities"
        elif any(w in merchant or w in notes for w in ["atm", "cash", "withdrawal"]):
            cat = "Cash Withdrawal"
        elif any(w in merchant for w in ["netflix", "spotify", "cinema", "movie", "disney", "entertainment"]):
            cat = "Entertainment"
        else:
            cat = "Other"
            
        results[tx_id] = cat
    return results

def classify_transactions_batch(transactions: list[dict]) -> tuple[dict, bool]:
    """
    Classify a batch of transactions using Gemini 1.5 Flash.
    Returns:
        dict: mapping of transaction ID -> category
        bool: True if LLM call failed and fallback was used, False otherwise
    """
    if not transactions:
        return {}, False

    # Standardize list of transactions for LLM context
    llm_payload = [
        {
            "id": str(tx.get("id")),
            "merchant": tx.get("merchant"),
            "amount": tx.get("amount"),
            "currency": tx.get("currency"),
            "notes": tx.get("notes")
        }
        for tx in transactions
    ]

    prompt = f"""
    You are an expert financial transaction classification assistant.
    You are given a list of financial transactions.
    For each transaction, classify it into exactly one of the following categories:
    - Food
    - Shopping
    - Travel
    - Transport
    - Utilities
    - Cash Withdrawal
    - Entertainment
    - Other

    Transactions:
    {json.dumps(llm_payload, indent=2)}

    Return a JSON object where keys are transaction IDs and values are the classification categories. Do not return any other text.
    Example:
    {{
      "1": "Food",
      "2": "Shopping"
    }}
    """

    try:
        response_text = call_gemini_with_retry(prompt)
        results = parse_json_safety(response_text)
        return results, False
    except Exception as e:
        logger.error(f"LLM Classification failed, falling back to mock classifier. Error: {e}")
        # Run mock classifier
        results = mock_classify(transactions)
        return results, True

def generate_narrative_summary(transactions: list[dict], stats: dict) -> tuple[dict, bool]:
    """
    Generate a JSON narrative summary of transaction data.
    Returns:
        dict: JobSummary data
        bool: True if LLM call failed and fallback was used, False otherwise
    """
    total_spend_inr = stats.get("total_spend_inr", 0.0)
    total_spend_usd = stats.get("total_spend_usd", 0.0)
    top_merchants = stats.get("top_merchants", [])
    anomaly_count = stats.get("anomaly_count", 0)

    # Convert first 50 transactions to JSON to keep prompt within reasonable tokens
    tx_subset = [
        {
            "merchant": tx.get("merchant"),
            "amount": tx.get("amount"),
            "currency": tx.get("currency"),
            "category": tx.get("category"),
            "is_anomaly": tx.get("is_anomaly"),
            "anomaly_reason": tx.get("anomaly_reason"),
            "status": tx.get("status")
        }
        for tx in transactions[:50]
    ]

    prompt = f"""
    You are a financial analyst summarizing user transaction records.
    Generate a summary of the spending patterns based on the statistics and sample transactions below:

    Aggregate Statistics:
    - Total spend in INR: {total_spend_inr:.2f}
    - Total spend in USD: {total_spend_usd:.2f}
    - Top Merchants: {json.dumps(top_merchants)}
    - Total Anomalies Flagged: {anomaly_count}

    Sample Transactions:
    {json.dumps(tx_subset, indent=2)}

    Please produce a JSON response with the following keys:
    - total_spend_inr: (float, copy the value {total_spend_inr:.2f})
    - total_spend_usd: (float, copy the value {total_spend_usd:.2f})
    - top_merchants: (array of strings, copy the array {json.dumps(top_merchants)})
    - anomaly_count: (int, copy the value {anomaly_count})
    - narrative: A 2-3 sentence spending narrative summarizing patterns, major merchants, and highlight any anomalies or risk behaviors.
    - risk_level: one of "low", "medium", or "high" (low if no anomalies and successful, medium if few outliers, high if many anomalies or large failed/suspicious rows).

    Response JSON structure:
    {{
      "total_spend_inr": {total_spend_inr:.2f},
      "total_spend_usd": {total_spend_usd:.2f},
      "top_merchants": {json.dumps(top_merchants)},
      "anomaly_count": {anomaly_count},
      "narrative": "Narrative string...",
      "risk_level": "low/medium/high"
    }}
    """

    try:
        response_text = call_gemini_with_retry(prompt)
        results = parse_json_safety(response_text)
        return results, False
    except Exception as e:
        logger.error(f"LLM Summary generation failed, falling back to mock summary. Error: {e}")
        # Mock summary generator
        risk = "low"
        if anomaly_count > 3:
            risk = "high"
        elif anomaly_count > 0:
            risk = "medium"

        merchants_str = ", ".join(top_merchants[:3]) if top_merchants else "various merchants"
        narrative = (
            f"The transaction log details a total expenditure of INR {total_spend_inr:.2f} and USD {total_spend_usd:.2f}. "
            f"Top merchants include {merchants_str}. A total of {anomaly_count} transactions were flagged as anomalous, "
            f"indicating a {risk}-risk spend pattern."
        )
        results = {
            "total_spend_inr": total_spend_inr,
            "total_spend_usd": total_spend_usd,
            "top_merchants": top_merchants,
            "anomaly_count": anomaly_count,
            "narrative": narrative,
            "risk_level": risk
        }
        return results, True
