import io
import pandas as pd

def parse_date(date_str) -> str | None:
    if pd.isna(date_str) or not str(date_str).strip() or str(date_str).strip().lower() == "nan":
        return None
    date_str = str(date_str).strip()
    
    # Try DD-MM-YYYY format
    # Try YYYY/MM/DD format
    # Try other common formats
    for fmt in ("%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return pd.to_datetime(date_str, format=fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
            
    try:
        return pd.to_datetime(date_str).strftime("%Y-%m-%d")
    except Exception:
        # If parsing fails, return as-is or None. We return None so it is cleaned.
        return None

def clean_amount(val) -> float:
    if pd.isna(val) or not str(val).strip() or str(val).strip().lower() == "nan":
        return 0.0
    val_str = str(val).replace("$", "").replace(",", "").replace(" ", "").strip()
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def clean_status(val) -> str:
    if pd.isna(val) or not str(val).strip() or str(val).strip().lower() == "nan":
        return "PENDING"
    status_str = str(val).strip().upper()
    if status_str not in ("SUCCESS", "FAILED", "PENDING"):
        return "PENDING"
    return status_str

def clean_category(val) -> str:
    if pd.isna(val) or not str(val).strip() or str(val).strip().lower() == "nan":
        return "Uncategorised"
    val_str = str(val).strip()
    if not val_str:
        return "Uncategorised"
    return val_str.capitalize()  # Normalize to e.g. "Food", "Shopping"

def clean_csv(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(file_bytes))
    
    # Normalize column names by stripping spaces
    df.columns = [col.strip() for col in df.columns]
    
    # Fill in missing columns if any are completely absent in the CSV
    required_cols = ['txn_id', 'date', 'merchant', 'amount', 'currency', 'status', 'category', 'account_id', 'notes']
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    # Apply clean procedures
    df['txn_id'] = df['txn_id'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip().lower() != "nan" and str(x).strip() != "" else None)
    df['date'] = df['date'].apply(parse_date)
    df['merchant'] = df['merchant'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip().lower() != "nan" else "Unknown")
    df['amount'] = df['amount'].apply(clean_amount)
    df['currency'] = df['currency'].apply(lambda x: str(x).strip().upper() if pd.notna(x) and str(x).strip().lower() != "nan" else "INR")
    df['status'] = df['status'].apply(clean_status)
    df['category'] = df['category'].apply(clean_category)
    
    # Account ID normalization
    df['account_id'] = df['account_id'].apply(lambda x: str(int(float(x))) if pd.notna(x) and str(x).replace('.0', '').isdigit() else (str(x).strip() if pd.notna(x) and str(x).strip().lower() != "nan" else "Unknown"))
    
    # Notes normalization
    df['notes'] = df['notes'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip().lower() != "nan" else "")

    # Drop duplicate rows across all columns
    df = df.drop_duplicates()
    
    return df
