"""ML Router: Online Model Contract & Inference endpoints for Crop & Rainfall prediction."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config import get_settings
from ml.src.predict import CropPredictor
from ml.src.predict_rainfall import RainfallPredictor

router = APIRouter(prefix="/ml", tags=["Machine Learning"])

# Singleton predictor instances
_crop_predictor: Optional[CropPredictor] = None
_rainfall_predictor: Optional[RainfallPredictor] = None


def get_crop_predictor() -> CropPredictor:
    global _crop_predictor
    if _crop_predictor is None:
        _crop_predictor = CropPredictor()
    return _crop_predictor


def get_rainfall_predictor() -> RainfallPredictor:
    global _rainfall_predictor
    if _rainfall_predictor is None:
        _rainfall_predictor = RainfallPredictor()
    return _rainfall_predictor


class CropPredictRequest(BaseModel):
    features: Dict[str, Any] = Field(
        ...,
        description="Features: N, P, K, temperature, humidity, ph, rainfall",
        example={
            "N": 70, "P": 40, "K": 40,
            "temperature": 25.0, "humidity": 75.0,
            "ph": 6.8, "rainfall": 150.0
        }
    )
    mode: str = Field(default="rules_with_ml", description="'rules_only' or 'rules_with_ml'")
    regional_approved: bool = Field(default=True, description="Approval gate for regional agronomic deployment")
    candidate_crop: Optional[str] = Field(default=None, description="Optional target candidate crop to check")
    top_k: int = Field(default=3, ge=1, le=10)


@router.get("/status")
async def ml_status():
    """Returns the operational status and metadata of ML models."""
    s = get_settings()
    cp = get_crop_predictor()
    rp = get_rainfall_predictor()

    return {
        "ml_enabled": s.ml_enabled,
        "crop_model": {
            "loaded": cp.model is not None,
            "model_type": type(cp.model).__name__ if cp.model else None,
            "classes_count": len(cp.label_map.get("classes", [])) if cp.label_map else 0,
            "classes": cp.label_map.get("classes", []) if cp.label_map else [],
            "required_features": cp.REQUIRED_FEATURES,
            "metadata": cp.metadata or {}
        },
        "rainfall_model": {
            "loaded": rp.model is not None,
            "model_type": type(rp.model).__name__ if rp.model else None,
            "history_rows": len(rp.df_history) if hasattr(rp, "df_history") else 0,
            "manifest_available": rp.manifest is not None
        }
    }


@router.post("/predict-crop")
async def predict_crop(body: CropPredictRequest):
    """
    Executes crop suitability prediction adhering to TRD Section 5.3 enablement gates.
    """
    cp = get_crop_predictor()
    try:
        res = cp.predict(
            features=body.features,
            mode=body.mode,
            regional_approved=body.regional_approved,
            candidate_crop=body.candidate_crop,
            top_k=body.top_k
        )
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ML inference error: {str(exc)}")


@router.get("/predict-rainfall")
async def predict_rainfall(
    district: Optional[str] = Query(default=None, description="Punjab district name (e.g. Ludhiana, Bathinda)"),
    lat: Optional[float] = Query(default=None, description="Latitude"),
    lon: Optional[float] = Query(default=None, description="Longitude"),
    month: Optional[int] = Query(default=None, ge=1, le=12, description="Target month (1-12)"),
    year: Optional[int] = Query(default=None, ge=2024, le=2035, description="Target year")
):
    """
    Predicts monthly rainfall and returns multi-year same-month trend analysis for Punjab.
    """
    rp = get_rainfall_predictor()
    s = get_settings()
    today = s.today()
    target_month = month or today.month
    target_year = year or today.year

    coords = (lat, lon) if (lat is not None and lon is not None) else None
    if not district and not coords:
        district = "Ludhiana"

    try:
        res = rp.predict_month(
            district=district,
            coords=coords,
            target_month=target_month,
            target_year=target_year
        )
        return res
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
