"""
VIKMO DealerDesk - Machine Learning Demand Forecasting Module
Generates ml/forecast.csv using historical weekly sales, promotion calendars, and festival lift.
"""

import csv
import math
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ML_DIR = BASE_DIR / "ml"

TARGET_WEEKS = ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"]


def get_festival_proximity(dt, diwali_dates):
    """Calculates non-linear festival lift proximity to Diwali dates."""
    diffs = [(dt - d).days for d in diwali_dates]
    min_diff = min(diffs, key=lambda x: abs(x))
    if -30 <= min_diff <= 14:
        return np.exp(-((min_diff + 7) ** 2) / (2 * (14 ** 2)))
    return 0.0


def train_and_generate_forecast():
    sales_path = DATA_DIR / "sales_history.csv"
    lead_path = DATA_DIR / "lead_times.csv"
    promo_path = DATA_DIR / "promo_calendar.csv"
    festivals_path = DATA_DIR / "festival_calendar.csv"
    forecast_out = ML_DIR / "forecast.csv"

    ML_DIR.mkdir(parents=True, exist_ok=True)

    sales = pd.read_csv(sales_path)
    lead = pd.read_csv(lead_path)
    promo = pd.read_csv(promo_path)
    festivals = pd.read_csv(festivals_path)

    festivals["date"] = pd.to_datetime(festivals["date"])
    diwali_dates = festivals[festivals["festival"] == "Diwali"]["date"].tolist()

    sales["week_start"] = pd.to_datetime(sales["week_start"])
    promo["week_start_str"] = promo["week_start"].astype(str)
    promo["week_start"] = pd.to_datetime(promo["week_start"])

    skus = lead["sku"].tolist()

    # Feature Engineering
    records = []
    for sku in skus:
        df_sku = sales[sales["sku"] == sku].sort_values("week_start").copy()
        df_sku["lag_1"] = df_sku["units_sold"].shift(1)
        df_sku["lag_2"] = df_sku["units_sold"].shift(2)
        df_sku["lag_3"] = df_sku["units_sold"].shift(3)
        df_sku["lag_4"] = df_sku["units_sold"].shift(4)
        df_sku["roll_mean_4"] = df_sku["units_sold"].shift(1).rolling(4, min_periods=1).mean()
        df_sku["roll_mean_12"] = df_sku["units_sold"].shift(1).rolling(12, min_periods=1).mean()
        df_sku["roll_std_12"] = df_sku["units_sold"].shift(1).rolling(12, min_periods=2).std().fillna(0)
        records.append(df_sku)

    full_sales = pd.concat(records).dropna(subset=["lag_4"])
    full_sales["month"] = full_sales["week_start"].dt.month
    full_sales["week_of_year"] = full_sales["week_start"].dt.isocalendar().week.astype(int)
    full_sales["fest_lift"] = full_sales["week_start"].apply(lambda d: get_festival_proximity(d, diwali_dates))

    base_features = [
        "promo_flag", "lag_1", "lag_2", "lag_3", "lag_4",
        "roll_mean_4", "roll_mean_12", "roll_std_12",
        "month", "week_of_year", "fest_lift"
    ]

    # One-hot encode SKU
    full_sales_enc = pd.get_dummies(full_sales, columns=["sku"])
    sku_cols = [c for c in full_sales_enc.columns if c.startswith("sku_")]
    all_features = base_features + sku_cols

    # Train model on full historical dataset
    model = RandomForestRegressor(n_estimators=150, max_depth=16, random_state=42, n_jobs=-1)
    model.fit(full_sales_enc[all_features], full_sales_enc["units_sold"])

    # Multi-step autoregressive rolling predictions for the 4 forecast weeks
    forecast_results = []
    
    # Track latest history per SKU
    latest_history = {}
    for sku in skus:
        df_sku = sales[sales["sku"] == sku].sort_values("week_start")
        latest_history[sku] = df_sku["units_sold"].tolist()

    for week_idx, target_week in enumerate(TARGET_WEEKS):
        week_dt = pd.to_datetime(target_week)
        month = week_dt.month
        week_of_year = int(week_dt.isocalendar().week)
        fest_lift = get_festival_proximity(week_dt, diwali_dates)

        week_rows = []
        sku_order = []

        for sku in skus:
            # Promo flag for target week
            p_match = promo[(promo["sku"] == sku) & (promo["week_start_str"] == target_week)]
            promo_flag = int(p_match["promo_flag"].values[0]) if len(p_match) > 0 else 0

            hist = latest_history[sku]
            lag_1 = hist[-1]
            lag_2 = hist[-2] if len(hist) >= 2 else lag_1
            lag_3 = hist[-3] if len(hist) >= 3 else lag_2
            lag_4 = hist[-4] if len(hist) >= 4 else lag_3

            roll_mean_4 = float(np.mean(hist[-4:]))
            roll_mean_12 = float(np.mean(hist[-12:])) if len(hist) >= 12 else roll_mean_4
            roll_std_12 = float(np.std(hist[-12:], ddof=1)) if len(hist) >= 12 else float(np.std(hist, ddof=1) if len(hist) > 1 else 0.0)

            row_data = {
                "promo_flag": promo_flag,
                "lag_1": lag_1,
                "lag_2": lag_2,
                "lag_3": lag_3,
                "lag_4": lag_4,
                "roll_mean_4": roll_mean_4,
                "roll_mean_12": roll_mean_12,
                "roll_std_12": roll_std_12,
                "month": month,
                "week_of_year": week_of_year,
                "fest_lift": fest_lift,
            }
            # One-hot flags
            for c in sku_cols:
                row_data[c] = 1 if c == f"sku_{sku}" else 0

            week_rows.append(row_data)
            sku_order.append(sku)

        df_input = pd.DataFrame(week_rows)[all_features]
        preds = model.predict(df_input)

        for sku, pred in zip(sku_order, preds):
            val = round(max(0.0, float(pred)), 1)
            latest_history[sku].append(val)
            forecast_results.append({
                "sku": sku,
                "week_start": target_week,
                "forecast_units": val,
            })

    # Save exactly to ml/forecast.csv
    df_forecast = pd.DataFrame(forecast_results)[["sku", "week_start", "forecast_units"]]
    df_forecast.to_csv(forecast_out, index=False)
    print(f"Successfully generated {forecast_out} with {len(df_forecast)} rows.")
    return df_forecast


if __name__ == "__main__":
    train_and_generate_forecast()
