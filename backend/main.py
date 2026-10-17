"""
Apni Kheti — FastAPI Application
Exposes endpoints for weather-aware crop feasibility recommendations and serves the interactive UI.
"""

from datetime import date
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.feasibility_service import FeasibilityRecommendationService

app = FastAPI(
    title="Apni Kheti Agro-Climatic Advisory",
    description="Dual-horizon weather feasibility and soil health card crop recommendation engine.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = FeasibilityRecommendationService()

class SoilReportRequest(BaseModel):
    farmer_name: Optional[str] = "Farmer"
    district: Optional[str] = "Rajasthan"
    latitude: float = Field(26.9124, description="Latitude coordinate")
    longitude: float = Field(75.7873, description="Longitude coordinate")
    query_date: str = Field("2024-10-10", description="Date in YYYY-MM-DD")
    N: float = Field(35.0, description="Available N index or kg/ha")
    P: float = Field(25.0, description="Available P index or kg/ha")
    K: float = Field(45.0, description="Available K index or kg/ha")
    ph: float = Field(7.8, description="Soil pH")
    ec: Optional[float] = Field(2.4, description="Electrical Conductivity dS/m")
    oc: Optional[float] = Field(0.42, description="Organic Carbon %")
    sulphur_ppm: Optional[float] = Field(9.5, description="Available Sulphur ppm")
    zinc_ppm: Optional[float] = Field(0.5, description="Available Zinc ppm")
    previous_crop: Optional[str] = Field("Bajra", description="Previous harvested crop")

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Apni Kheti Advisory"}

@app.post("/api/recommend")
def get_recommendation(req: SoilReportRequest):
    try:
        q_date = date.fromisoformat(req.query_date)
    except Exception:
        q_date = date.today()

    soil_features = {
        "N": req.N,
        "P": req.P,
        "K": req.K,
        "ph": req.ph
    }

    try:
        rec = service.get_weather_aware_recommendation(
            soil_features=soil_features,
            latitude=req.latitude,
            longitude=req.longitude,
            query_date=q_date,
            top_k=5
        )

        # Append soil health card specific agronomic flags
        shc_notes = []
        if req.ec and req.ec >= 2.0:
            shc_notes.append(f"SALINE SOIL DETECTED (EC = {req.ec:.1f} dS/m): Chickpea/pulses highly susceptible. Salt-tolerant crops (Mustard/Barley/Wheat) favored.")
        if req.sulphur_ppm and req.sulphur_ppm < 10.0:
            shc_notes.append(f"SULPHUR DEFICIENCY (S = {req.sulphur_ppm:.1f} ppm): Apply 200-250 kg/ha Gypsum or 25 kg/ha Bentonite Sulphur.")
        if req.zinc_ppm and req.zinc_ppm < 0.6:
            shc_notes.append(f"ZINC DEFICIENCY (Zn = {req.zinc_ppm:.1f} ppm): Apply 25 kg/ha Zinc Sulphate (ZnSO4) basal dose.")
        if req.oc and req.oc < 0.5:
            shc_notes.append(f"LOW ORGANIC CARBON (OC = {req.oc:.2f}%): Apply 8-10 tons/ha Farmyard Manure (FYM).")

        rec["soil_health_card_diagnostics"] = {
            "farmer_name": req.farmer_name,
            "district": req.district,
            "previous_crop": req.previous_crop,
            "ec_ds_m": req.ec,
            "shc_prescriptions": shc_notes
        }

        return rec
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount static frontend
FRONTEND_DIR = PROJECT_ROOT / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Apni Kheti API Running. Frontend index.html not yet built."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
