import copy
import math
import sys
from pathlib import Path

import pytest

# Keep this test independent of collection order and developer PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gonogo_v1 as g

@pytest.fixture
def valid_replay():
    return {
        "model_parameters_max_abs_delta": {
            "intercept": 0.0,
            "weights": 0.0,
            "feature_mean": 0.0,
            "feature_std": 0.0,
        },
        "inference_max_abs_delta": 0.0,
        "classification_disagreements": 0,
    }

def test_valid_replay(valid_replay):
    g.validate_replay_deltas(valid_replay)

@pytest.mark.parametrize("mutation", [
    "missing_inference",
    "nonzero_inference",
    "nan_model_delta",
    "classification_mismatch",
    "missing_parameter",
    "boolean_delta",
])
def test_invalid_replay_fails_closed(valid_replay, mutation):
    data = copy.deepcopy(valid_replay)

    if mutation == "missing_inference":
        del data["inference_max_abs_delta"]
    elif mutation == "nonzero_inference":
        data["inference_max_abs_delta"] = 1e-6
    elif mutation == "nan_model_delta":
        data["model_parameters_max_abs_delta"]["weights"] = math.nan
    elif mutation == "classification_mismatch":
        data["classification_disagreements"] = 1
    elif mutation == "missing_parameter":
        del data["model_parameters_max_abs_delta"]["intercept"]
    elif mutation == "boolean_delta":
        data["inference_max_abs_delta"] = False

    with pytest.raises(g.AuditError):
        g.validate_replay_deltas(data)

def test_review_rejects_invalid_replay(tmp_path, monkeypatch):
    from types import SimpleNamespace

    payloads = {
        "protocol.json": {
            "status": "DEVELOPMENT_PROTOCOL_AND_EVIDENCE_FROZEN_HOLDOUT_NOT_AUTHORIZED"
        },
        "candidate_model.json": {
            "decision_threshold": g.THRESHOLD,
            "weights": [0.0] * 72
        },
        "final_model_manifest.json": {
            "status": "LOCAL_INTEGRITY_MANIFEST_NOT_HOLDOUT_AUTHORIZATION"
        },
        "MedAI-Final-Model-Reproduction-Audit-v1.json": {
            "status": "REPRODUCED_FINAL_MODEL_WITHIN_TOLERANCE_HOLDOUT_NOT_AUTHORIZED",
            "model_parameters_max_abs_delta": {
                "intercept": 0.0,
                "weights": 0.0,
                "feature_mean": 0.0,
                "feature_std": 0.0
            },
            "inference_max_abs_delta": 1e-6,
            "classification_disagreements": 0
        },
        "MedAI-Holdout-Readiness-Review-v1.json": {
            "status": "TECHNICAL_EVIDENCE_VERIFIED_HOLDOUT_NOT_AUTHORIZED",
            "holdout_authorized": False
        },
        "plan_validation_manifest.json": {
            "status": "PREHOLDOUT_PLAN_LOCKED_LOCALLY_PENDING_INDEPENDENT_REVIEW",
            "holdout_authorized": False
        },
        "MedAI-Holdout-Integration-Review-v1.json": {
            "status": "PASS_SYNTHETIC_WFDB_INTEGRATION_HOLDOUT_NOT_AUTHORIZED",
            "holdout_authorized": False
        }
    }

    monkeypatch.setattr(
        g,
        "verify_one",
        lambda path, expected: {"name": path.name, "sha256": expected}
    )
    monkeypatch.setattr(
        g,
        "read_json",
        lambda path: payloads[path.name]
    )

    args = SimpleNamespace(
        docs=tmp_path,
        freeze_dir=tmp_path,
        model_dir=tmp_path,
        plan_dir=tmp_path
    )

    with pytest.raises(g.AuditError, match="Replay delta"):
        g.review(args)
