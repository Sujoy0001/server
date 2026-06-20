import pandas as pd

def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    # Set default values for anomaly flags
    df['is_anomaly'] = False
    df['anomaly_reason'] = ""

    # Group by account_id and compute median
    # We filter out accounts named 'Unknown' or empty, or handle them normally.
    # Grouping by account_id is standard.
    account_medians = df.groupby('account_id')['amount'].median().to_dict()

    domestic_brands = {"swiggy", "ola", "irctc"}

    for idx, row in df.iterrows():
        reasons = []
        account_id = row['account_id']
        amount = row['amount']
        currency = str(row['currency']).strip().upper()
        merchant = str(row['merchant']).strip().lower()

        # Check 1: 3x account median outlier
        median = account_medians.get(account_id, 0.0)
        # We only check outliers for positive amounts and when median is non-zero
        if median > 0 and amount > 3 * median:
            reasons.append(f"Amount ({amount}) exceeds 3x account median ({median:.2f})")

        # Check 2: Domestic brand transacting in USD
        # Match if the merchant name contains 'swiggy', 'ola', or 'irctc'
        if currency == "USD" and any(brand in merchant for brand in domestic_brands):
            reasons.append(f"Domestic brand ({row['merchant']}) transacting in USD")

        if reasons:
            df.at[idx, 'is_anomaly'] = True
            df.at[idx, 'anomaly_reason'] = " & ".join(reasons)

    return df
