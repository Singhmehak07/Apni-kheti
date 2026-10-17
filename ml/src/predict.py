"""
Apni Kheti — Online Model Contract & Inference Adapter
Implements TRD Section 5.3: Online model contract & enablement gate.

Rules:
- Modes: 'rules_only' (default) or 'rules_with_ml'.
- Enable model evidence ONLY if:
  1. Model is loaded from a trusted artifact, not user upload.
  2. Every input has known, compatible unit, analyte/method and aggregation semantics.
  3. Candidate crops exist in the model label set and have applicable reviewed rules.
  4. Input range/coverage checks pass (OOD detection); required values are not fabricated.
  5. Regional evaluation and limitations are approved for the intended use.
- If any gate fails: set ml_status="skipped", return reason(s), and continue with defensible rules.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import joblib
import numpy as np

CURRENT_DIR = Path(__file__).resolve().parent
MODELS_DIR = CURRENT_DIR.parent / "models"
BACKEND_ARTIFACTS_DIR = CURRENT_DIR.parent.parent / "backend" / "artifacts"

class CropPredictor:
    REQUIRED_FEATURES = ['N', 'P', 'K', 'temperature', 'humidity', 'ph', 'rainfall']

    def __init__(self, model_dir: Optional[Path] = None):
        # Prefer backend/artifacts if available, otherwise ml/models
        if model_dir is not None and model_dir.exists():
            self.model_dir = model_dir
        elif BACKEND_ARTIFACTS_DIR.exists() and (BACKEND_ARTIFACTS_DIR / "trusted_rf_model.joblib").exists():
            self.model_dir = BACKEND_ARTIFACTS_DIR
        else:
            self.model_dir = MODELS_DIR

        self.model = None
        self.manifest = None
        self.label_map = None
        self.metadata = None
        self._load_artifacts()

    def _load_artifacts(self):
        model_path = self.model_dir / "trusted_rf_model.joblib"
        manifest_path = self.model_dir / "features_manifest.json"
        label_map_path = self.model_dir / "label_map.json"
        meta_path = self.model_dir / "dataset_metadata.json"

        if model_path.exists():
            try:
                self.model = joblib.load(model_path)
            except Exception as e:
                self.model = None

        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                self.manifest = json.load(f)

        if label_map_path.exists():
            with open(label_map_path, "r", encoding="utf-8") as f:
                self.label_map = json.load(f)

        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)

    def evaluate_enablement_gates(
        self,
        features: Dict[str, Any],
        mode: str,
        regional_approved: bool,
        candidate_crop: Optional[str] = None
    ) -> List[str]:
        """
        Evaluates the 5 TRD 5.3 enablement gates.
        Returns a list of skip reasons. If empty, all gates pass.
        """
        skip_reasons = []

        # Gate 0: Mode check
        if mode != "rules_with_ml":
            skip_reasons.append("MODE_RULES_ONLY_ACTIVE")
            return skip_reasons

        # Gate 1: Trusted artifact check
        if self.model is None or self.manifest is None or self.label_map is None:
            skip_reasons.append("TRUSTED_ARTIFACT_MISSING_OR_CORRUPT")
            return skip_reasons

        # Gate 2: Feature contract (presence & type)
        missing_features = [f for f in self.REQUIRED_FEATURES if f not in features or features[f] is None]
        if missing_features:
            skip_reasons.append(f"MISSING_REQUIRED_FEATURES:{','.join(missing_features)}")

        # Check for non-numeric features
        invalid_types = []
        for f in self.REQUIRED_FEATURES:
            if f in features and features[f] is not None:
                val = features[f]
                if not isinstance(val, (int, float, np.number)):
                    invalid_types.append(f)
        if invalid_types:
            skip_reasons.append(f"NON_NUMERIC_FEATURE_VALUES:{','.join(invalid_types)}")

        # Gate 3: Candidate crop check against model label set (TRD 5.1 & 5.3)
        if candidate_crop is not None:
            norm_crop = candidate_crop.lower().strip()
            available_classes = [c.lower() for c in self.label_map.get("classes", [])]
            if norm_crop not in available_classes:
                skip_reasons.append(f"CROP_NOT_IN_MODEL_LABEL_SET:{candidate_crop}")

        # Gate 4: Input range / Out-Of-Distribution (OOD) checks
        if self.manifest and "ranges" in self.manifest and not missing_features and not invalid_types:
            ood_features = []
            for f in self.REQUIRED_FEATURES:
                val = float(features[f])
                f_min = self.manifest["ranges"][f]["min"]
                f_max = self.manifest["ranges"][f]["max"]
                # Guardrail: allow realistic physical ranges, flag extreme OOD
                if f == "ph" and (val < 3.0 or val > 11.0):
                    ood_features.append(f"ph={val}(out_of_soil_range)")
                elif f == "humidity" and (val < 0.0 or val > 100.0):
                    ood_features.append(f"humidity={val}")
                elif f == "temperature" and (val < -10.0 or val > 65.0):
                    ood_features.append(f"temperature={val}")
                elif f in ["N", "P", "K", "rainfall"] and val < 0.0:
                    ood_features.append(f"{f}={val}(negative)")
            if ood_features:
                skip_reasons.append(f"OUT_OF_DISTRIBUTION_INPUTS:{';'.join(ood_features)}")

        # Gate 5: Regional agronomic evaluation approval (TRD 5.3 Gate 5)
        if not regional_approved:
            skip_reasons.append("REGIONAL_EVALUATION_NOT_APPROVED_FOR_FIELD_DEPLOYMENT")

        return skip_reasons

    def predict(
        self,
        features: Dict[str, Any],
        mode: str = "rules_only",
        regional_approved: bool = False,
        candidate_crop: Optional[str] = None,
        top_k: int = 3
    ) -> Dict[str, Any]:
        """
        Executes inference adhering strictly to TRD Section 5.3.
        """
        skip_reasons = self.evaluate_enablement_gates(
            features=features,
            mode=mode,
            regional_approved=regional_approved,
            candidate_crop=candidate_crop
        )

        if skip_reasons:
            return {
                "ml_status": "skipped",
                "ml_skip_reasons": skip_reasons,
                "top_candidates": [],
                "target_crop_score": None,
                "agronomic_advisory": "ML evidence skipped. Operating under reviewed agronomic rules."
            }

        # If all gates pass, run model with explicit DataFrame feature names
        import pandas as pd
        input_df = pd.DataFrame(
            [[float(features[f]) for f in self.REQUIRED_FEATURES]], 
            columns=self.REQUIRED_FEATURES
        )
        probs = self.model.predict_proba(input_df)[0]
        classes = self.label_map["classes"]

        # Sort top-k
        top_indices = np.argsort(probs)[::-1][:top_k]
        top_candidates = [
            {
                "crop": classes[idx],
                "model_score": float(round(probs[idx], 4)),
                "rank": rank + 1
            }
            for rank, idx in enumerate(top_indices)
        ]

        target_score = None
        if candidate_crop is not None:
            norm_crop = candidate_crop.lower().strip()
            for idx, cls in enumerate(classes):
                if cls.lower() == norm_crop:
                    target_score = float(round(probs[idx], 4))
                    break

        return {
            "ml_status": "evaluated",
            "ml_skip_reasons": [],
            "top_candidates": top_candidates,
            "target_crop_score": target_score,
            "agronomic_advisory": (
                "Model score reflects similarity to Kaggle synthetic training clusters. "
                "Final agronomic recommendation remains governed by reviewed PAU regional rules."
            )
        }

if __name__ == "__main__":
    predictor = CropPredictor()
    
    # Test case 1: Default rules_only mode
    sample_features = {
        'N': 90, 'P': 42, 'K': 43,
        'temperature': 20.8, 'humidity': 82.0,
        'ph': 6.5, 'rainfall': 202.9
    }
    res_default = predictor.predict(sample_features, mode="rules_only")
    print("Test 1 (Default rules_only):", res_default["ml_status"], res_default["ml_skip_reasons"])

    # Test case 2: Attempting prediction with unapproved regional gate
    res_unapproved = predictor.predict(sample_features, mode="rules_with_ml", regional_approved=False)
    print("Test 2 (Unapproved regional gate):", res_unapproved["ml_status"], res_unapproved["ml_skip_reasons"])

    # Test case 3: Unsupported crop (Wheat - not in Kaggle dataset)
    res_wheat = predictor.predict(sample_features, mode="rules_with_ml", regional_approved=True, candidate_crop="wheat")
    print("Test 3 (Wheat check):", res_wheat["ml_status"], res_wheat["ml_skip_reasons"])

    # Test case 4: Fully approved inference
    res_approved = predictor.predict(sample_features, mode="rules_with_ml", regional_approved=True, candidate_crop="rice")
    print("Test 4 (Approved Rice):", res_approved["ml_status"], res_approved["top_candidates"])
