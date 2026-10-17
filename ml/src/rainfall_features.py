"""
Apni Kheti — Monthly Rainfall Feature Engineering
Builds inter-annual same-month trend and antecedent lag features.

Features explicitly address:
"predict rainfall in a particular month analysing previous year same month trends"
"""

from pathlib import Path
import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
CSV_PATH = PROCESSED_DATA_DIR / "punjab_monthly_rainfall_2015_2025.csv"

def compute_linear_slope(y_vals: list) -> float:
    """Computes linear trend slope (rate of change per year)."""
    if len(y_vals) < 2:
        return 0.0
    x = np.arange(len(y_vals))
    # slope = cov(x, y) / var(x)
    x_mean = np.mean(x)
    y_mean = np.mean(y_vals)
    denom = np.sum((x - x_mean) ** 2)
    if denom == 0:
        return 0.0
    slope = np.sum((x - x_mean) * (y_vals - y_mean)) / denom
    return float(slope)

def build_rainfall_features(df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Constructs multi-year same-month trend features and antecedent lags.
    Requires at least 2 preceding years of data to form reliable same-month trend features.
    """
    if df is None:
        if not CSV_PATH.exists():
            from ml.src.rainfall_extractor import extract_all_districts
            df = extract_all_districts()
        else:
            df = pd.read_csv(CSV_PATH)

    # Sort strictly chronologically by district, year, month
    df = df.sort_values(by=["district", "year", "month"]).reset_index(drop=True)

    feature_rows = []
    districts = df["district"].unique()

    for dist in districts:
        sub = df[df["district"] == dist].copy()
        
        # Build lookup table: (year, month) -> rainfall_mm, rainy_days
        rf_dict = {}
        rd_dict = {}
        for _, row in sub.iterrows():
            rf_dict[(int(row["year"]), int(row["month"]))] = float(row["rainfall_mm"])
            rd_dict[(int(row["year"]), int(row["month"]))] = int(row["rainy_days"])

        all_years = sorted(sub["year"].unique())

        for idx, row in sub.iterrows():
            y = int(row["year"])
            m = int(row["month"])
            target_rf = float(row["rainfall_mm"])

            # Collect historical same-month observations from past years (prior to y)
            past_same_month_rf = [rf_dict[(past_y, m)] for past_y in all_years if past_y < y and (past_y, m) in rf_dict]
            past_same_month_rd = [rd_dict[(past_y, m)] for past_y in all_years if past_y < y and (past_y, m) in rd_dict]

            # Require at least 2 prior years of history for same-month trend modeling (e.g. 2017 onwards)
            if len(past_same_month_rf) < 2:
                continue

            # Prior year same month lags
            lag_1yr = past_same_month_rf[-1]
            lag_2yr = past_same_month_rf[-2]
            lag_3yr = past_same_month_rf[-3] if len(past_same_month_rf) >= 3 else lag_2yr

            mean_3yr = float(np.mean(past_same_month_rf[-3:]))
            mean_5yr = float(np.mean(past_same_month_rf[-5:]))
            hist_mean = float(np.mean(past_same_month_rf))
            hist_std = float(np.std(past_same_month_rf)) if len(past_same_month_rf) > 1 else 0.0
            hist_min = float(np.min(past_same_month_rf))
            hist_max = float(np.max(past_same_month_rf))
            hist_rd_avg = float(np.mean(past_same_month_rd))

            # Linear trend slope of same month rainfall over time (mm per year)
            trend_slope = compute_linear_slope(past_same_month_rf)

            # Antecedent months in current sequence: (m-1, m-2)
            prev_m1_year = y if m > 1 else y - 1
            prev_m1_month = m - 1 if m > 1 else 12
            lag_1m = rf_dict.get((prev_m1_year, prev_m1_month), hist_mean)

            prev_m2_year = y if m > 2 else y - 1
            prev_m2_month = m - 2 if m > 2 else (12 if m == 2 else 11)
            lag_2m = rf_dict.get((prev_m2_year, prev_m2_month), hist_mean)

            # Season categorization:
            # 0: Winter Rabi (Jan-Feb), 1: Summer/Zaid (Mar-May), 2: Monsoon/Kharif (Jun-Sep), 3: Post-Monsoon (Oct-Dec)
            if m in [1, 2]:
                season_code = 0
            elif m in [3, 4, 5]:
                season_code = 1
            elif m in [6, 7, 8, 9]:
                season_code = 2
            else:
                season_code = 3

            # Cyclical month encoding
            month_sin = float(np.sin(2 * np.pi * m / 12.0))
            month_cos = float(np.cos(2 * np.pi * m / 12.0))

            feature_rows.append({
                "district": dist,
                "grid_lat": float(row["grid_lat"]),
                "grid_lon": float(row["grid_lon"]),
                "year": y,
                "month": m,
                "month_sin": month_sin,
                "month_cos": month_cos,
                "season_code": season_code,
                "same_month_lag_1yr": lag_1yr,
                "same_month_lag_2yr": lag_2yr,
                "same_month_lag_3yr": lag_3yr,
                "same_month_3yr_mean": mean_3yr,
                "same_month_5yr_mean": mean_5yr,
                "same_month_hist_mean": hist_mean,
                "same_month_hist_std": hist_std,
                "same_month_hist_min": hist_min,
                "same_month_hist_max": hist_max,
                "same_month_trend_slope": trend_slope,
                "same_month_rainy_days_avg": hist_rd_avg,
                "prior_month_rf": lag_1m,
                "prior_2month_rf": lag_2m,
                "target_rainfall_mm": target_rf,
                "target_rainy_days": int(row["rainy_days"])
            })

    df_features = pd.DataFrame(feature_rows)
    features_csv = PROCESSED_DATA_DIR / "rainfall_model_features.csv"
    df_features.to_csv(features_csv, index=False)
    print(f"[OK] Built {len(df_features)} training samples with same-month trend features -> {features_csv.name}")
    return df_features

if __name__ == "__main__":
    df_feat = build_rainfall_features()
    print("Feature columns:", list(df_feat.columns))
    print(df_feat.head(3))
