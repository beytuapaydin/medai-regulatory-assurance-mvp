"""Synthetic negative tests for invisible PTB-XL identifiers."""
import pytest
from src.clinical_validation.demo_runner import synthetic_fixture
from src.clinical_validation.clinical_eval_runner import evaluate_model_regression


@pytest.mark.parametrize("suffix", ["\u200b", "\u200c", "\u200d", "\ufeff", "\x00"])
def test_nonprintable_patient_id_cannot_bypass_train_test_overlap(suffix):
    rows, training = synthetic_fixture("pass")
    leaked = rows[0]["patient_id"]
    rows[0]["patient_id"] = leaked + suffix
    result = evaluate_model_regression(
        rows, training_patient_ids=[leaked],
        model_v1_id="BASE", model_v2_id="CAND",
    )
    assert result["gate_status"] != "PASS"
    assert any("patient_id" in reason or "leakage" in reason.lower() for reason in result["reasons"])


@pytest.mark.parametrize("suffix", ["\u200b", "\ufeff"])
def test_nonprintable_training_manifest_is_rejected(suffix):
    rows, _ = synthetic_fixture("pass")
    result = evaluate_model_regression(
        rows, training_patient_ids=[rows[0]["patient_id"] + suffix],
        model_v1_id="BASE", model_v2_id="CAND",
    )
    assert result["gate_status"] == "INSUFFICIENT_EVIDENCE"


def test_nonprintable_ecg_id_is_rejected():
    rows, _ = synthetic_fixture("pass")
    rows[0]["ecg_id"] += "\u200b"
    result = evaluate_model_regression(
        rows, training_patient_ids=[],
        model_v1_id="BASE", model_v2_id="CAND",
    )
    assert result["gate_status"] == "NOT_MEASURED"
