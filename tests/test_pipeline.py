import pandas as pd
from server.app.services.cleaning import parse_date, clean_amount, clean_csv
from server.app.services.anomalies import detect_anomalies
from server.app.services.llm_service import mock_classify

def test_parse_date():
    assert parse_date("19-06-2026") == "2026-06-19"
    assert parse_date("2026/06/19") == "2026-06-19"
    assert parse_date("2026-06-19") == "2026-06-19"
    assert parse_date("   ") is None
    assert parse_date(None) is None
    assert parse_date("invalid-date") is None

def test_clean_amount():
    assert clean_amount("$1,200.50") == 1200.50
    assert clean_amount("  $45.0  ") == 45.0
    assert clean_amount("abc") == 0.0
    assert clean_amount(None) == 0.0
    assert clean_amount("") == 0.0

def test_detect_anomalies_statistical():
    # ACC1 has 5 transactions. Median of [10, 12, 11, 13, 100] is 12.0.
    # 3x median is 36.0. Therefore, 100 is an outlier.
    data = {
        "account_id": ["ACC1", "ACC1", "ACC1", "ACC1", "ACC1"],
        "amount": [10.0, 12.0, 11.0, 13.0, 100.0],
        "currency": ["INR", "INR", "INR", "INR", "INR"],
        "merchant": ["Swiggy", "Zomato", "Uber", "Airtel", "Ola"]
    }
    df = pd.DataFrame(data)
    df_result = detect_anomalies(df)
    
    assert df_result.iloc[4]["is_anomaly"] == True
    assert "exceeds 3x account median" in df_result.iloc[4]["anomaly_reason"]
    assert df_result.iloc[0]["is_anomaly"] == False

def test_detect_anomalies_domestic_usd():
    # Domestic merchant in USD
    data = {
        "account_id": ["ACC2"],
        "amount": [20.0],
        "currency": ["USD"],
        "merchant": ["Swiggy Bangalore"]
    }
    df = pd.DataFrame(data)
    df_result = detect_anomalies(df)
    
    assert df_result.iloc[0]["is_anomaly"] == True
    assert "Domestic brand (Swiggy Bangalore) transacting in USD" in df_result.iloc[0]["anomaly_reason"]

def test_mock_classify():
    txs = [
        {"id": "1", "merchant": "Swiggy Pune", "notes": ""},
        {"id": "2", "merchant": "Uber Cab", "notes": ""},
        {"id": "3", "merchant": "Netflix subscription", "notes": ""},
        {"id": "4", "merchant": "Airtel Bill", "notes": ""},
        {"id": "5", "merchant": "Amazon Shopping", "notes": ""},
        {"id": "6", "merchant": "SBI ATM", "notes": "Cash Withdrawal"}
    ]
    results = mock_classify(txs)
    assert results["1"] == "Food"
    assert results["2"] == "Transport"
    assert results["3"] == "Entertainment"
    assert results["4"] == "Utilities"
    assert results["5"] == "Shopping"
    assert results["6"] == "Cash Withdrawal"
