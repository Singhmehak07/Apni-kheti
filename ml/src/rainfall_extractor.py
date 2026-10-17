"""
Apni Kheti — IMD Gridded Rainfall Extraction Pipeline
Extracts daily & monthly rainfall series from 0.25° x 0.25° NetCDF files (2015–2025).

Supported Geography:
- All 22 official districts of Punjab.
- Nearest-grid coordinate lookup for any latitude/longitude in India.
"""

import os
import glob
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import scipy.io

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
RAW_NC_DIR = PROJECT_ROOT / "data" / "rainfal 10 yrs"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"

# Punjab District Center Coordinates
PUNJAB_DISTRICTS = {
    "Ludhiana": (30.9010, 75.8573),
    "Amritsar": (31.6340, 74.8723),
    "Patiala": (30.3398, 76.3869),
    "Bathinda": (30.2110, 74.9455),
    "Jalandhar": (31.3260, 75.5762),
    "Sangrur": (30.2458, 75.8421),
    "Firozpur": (30.9237, 74.6114),
    "Gurdaspur": (32.0419, 75.4053),
    "Hoshiarpur": (31.5273, 75.9149),
    "Mansa": (29.9880, 75.3934),
    "Mohali": (30.7046, 76.7179),
    "Rupnagar": (30.9664, 76.5331),
    "Fazilka": (30.4036, 74.0254),
    "Kapurthala": (31.3801, 75.3813),
    "Muktsar": (30.4762, 74.5122),
    "Faridkot": (30.6769, 74.7583),
    "Barnala": (30.3819, 75.5469),
    "Fatehgarh Sahib": (30.6490, 76.3980),
    "SBS Nagar": (31.1256, 76.1186),
    "Pathankot": (32.2686, 75.6499),
    "Tarn Taran": (31.4518, 74.9272),
    "Malerkotla": (30.5247, 75.8872)
}

def extract_all_districts(nc_dir: Path = RAW_NC_DIR) -> pd.DataFrame:
    """
    Reads all IMD .nc files and compiles monthly rainfall aggregates for Punjab districts.
    """
    nc_files = sorted(glob.glob(str(nc_dir / "*.nc")))
    if not nc_files:
        raise FileNotFoundError(f"No NetCDF (.nc) files found in {nc_dir}")

    # Read grid coordinates from the first file
    f0 = scipy.io.netcdf_file(nc_files[0], 'r', mmap=False)
    lons = f0.variables['LONGITUDE'][:]
    lats = f0.variables['LATITUDE'][:]
    f0.close()

    # Map each district to the nearest IMD grid cell (0.25 deg resolution)
    district_grid_map = {}
    for name, (lat, lon) in PUNJAB_DISTRICTS.items():
        lat_idx = int(np.argmin(np.abs(lats - lat)))
        lon_idx = int(np.argmin(np.abs(lons - lon)))
        grid_lat = float(lats[lat_idx])
        grid_lon = float(lons[lon_idx])
        district_grid_map[name] = (lat_idx, lon_idx, grid_lat, grid_lon)

    base_date = datetime(1900, 12, 31)
    monthly_records = []

    print(f"Extracting 10-year rainfall from {len(nc_files)} IMD NetCDF files...")

    for filepath in nc_files:
        f = scipy.io.netcdf_file(filepath, 'r', mmap=False)
        time_vals = f.variables['TIME'][:]
        dates = [base_date + timedelta(days=float(t)) for t in time_vals]
        years = np.array([d.year for d in dates])
        months = np.array([d.month for d in dates])
        year_val = int(years[0])

        rf_var = f.variables['RAINFALL'] # shape: (days, lat, lon)

        for dist_name, (lat_idx, lon_idx, g_lat, g_lon) in district_grid_map.items():
            daily_rf = rf_var[:, lat_idx, lon_idx]
            # Replace fill values (-999.0) with 0.0
            daily_rf = np.where(daily_rf < 0, 0.0, daily_rf)

            for m in range(1, 13):
                m_mask = (months == m)
                if not np.any(m_mask):
                    continue
                m_vals = daily_rf[m_mask]
                tot_rf = float(np.sum(m_vals))
                rainy_days = int(np.sum(m_vals >= 2.5)) # IMD standard: >= 2.5mm is a rainy day
                max_daily = float(np.max(m_vals)) if len(m_vals) > 0 else 0.0

                monthly_records.append({
                    "state": "Punjab",
                    "district": dist_name,
                    "grid_lat": g_lat,
                    "grid_lon": g_lon,
                    "year": year_val,
                    "month": m,
                    "rainfall_mm": round(tot_rf, 2),
                    "rainy_days": rainy_days,
                    "max_daily_mm": round(max_daily, 2)
                })
        f.close()

    df_monthly = pd.DataFrame(monthly_records)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DATA_DIR / "punjab_monthly_rainfall_2015_2025.csv"
    df_monthly.to_csv(out_csv, index=False)
    print(f"[OK] Extracted {len(df_monthly)} monthly observations to {out_csv.name}")
    return df_monthly

if __name__ == "__main__":
    df = extract_all_districts()
    print("Sample rows:")
    print(df.head())
