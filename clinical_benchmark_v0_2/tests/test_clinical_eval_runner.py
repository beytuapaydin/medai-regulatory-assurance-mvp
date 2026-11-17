"""Acceptance and safety-regression tests; all predictions are synthetic."""
from copy import deepcopy
import pytest
from src.clinical_validation import EvaluationPolicy, compute_sha256, evaluate_model_regression

POLICY = EvaluationPolicy(required_subgroups=("ALL", "F_65_PLUS"))


def make_records(n_pos=40, n_neg=40):
    rows = []
    for i in range(n_pos + n_neg):
        y = int(i < n_pos)
        rows.append({
            "ecg_id": f"ECG_{i}", "patient_id": f"TEST_PATIENT_{i}",
            "strat_fold": 10, "subgroups": ["ALL", "F_65_PLUS"],
            "y_true": y, "y_pred_v1": y, "y_pred_v2": y,
        })
    return rows


def gate(records, **kwargs):
    opts = dict(training_patient_ids=["TRAIN_PATIENT_A", "TRAIN_PATIENT_B"],
                model_v1_id="demo-v1", model_v2_id="demo-v2", policy=POLICY,
                is_synthetic_run=True)
    opts.update(kwargs)
    return evaluate_model_regression(records, **opts)


# Four mandatory acceptance statuses

def test_accept_pass():
    result = gate(make_records())
    assert result["gate_status"] == "PASS"
    assert result["evidence_scope"] == "ENGINE_TEST_ONLY"
    assert result["subgroup_metrics"]["ALL"]["sensitivity_v2"] == 1.0
    assert len(result["report_sha256"]) == 64


def test_accept_fail():
    rows = make_records()
    for i in range(6):
        rows[i]["y_pred_v2"] = 0
    result = gate(rows)
    assert result["gate_status"] == "FAIL"
    assert any("false-negative rate" in reason for reason in result["reasons"])


def test_accept_insufficient_evidence():
    rows = make_records()
    result = gate(rows, training_patient_ids=[rows[0]["patient_id"]])
    assert result["gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert any("Patient leakage" in reason for reason in result["reasons"])


def test_accept_not_measured():
    rows = make_records()
    rows[0]["y_pred_v2"] = None
    result = gate(rows)
    assert result["gate_status"] == "NOT_MEASURED"
    assert result["subgroup_metrics"] == {}


# Additional negative tests to prevent false PASS

def test_no_training_manifest_never_passes():
    assert gate(make_records(), training_patient_ids=None)["gate_status"] == "INSUFFICIENT_EVIDENCE"


def test_unrepresented_mandatory_subgroup_never_passes():
    rows = make_records()
    for row in rows:
        row["subgroups"] = ["ALL"]
    assert gate(rows)["gate_status"] == "INSUFFICIENT_EVIDENCE"


def test_few_positives_never_passes():
    assert gate(make_records(n_pos=5))["gate_status"] == "INSUFFICIENT_EVIDENCE"


def test_few_negatives_never_passes():
    assert gate(make_records(n_neg=5))["gate_status"] == "INSUFFICIENT_EVIDENCE"


def test_mixed_failing_and_insufficient_groups_still_fail():
    rows = make_records()
    for row in rows:
        row["subgroups"] = ["ALL"]  # F_65_PLUS is insufficient
    for i in range(6):
        rows[i]["y_pred_v2"] = 0  # ALL is a confirmed failure
    result = gate(rows)
    assert result["gate_status"] == "FAIL"
    assert any("requires >= " in reason for reason in result["reasons"])


def test_duplicate_ecg_is_insufficient():
    rows = make_records()
    rows[1]["ecg_id"] = rows[0]["ecg_id"]
    assert gate(rows)["gate_status"] == "INSUFFICIENT_EVIDENCE"


def test_non_test_fold_is_insufficient():
    rows = make_records()
    rows[0]["strat_fold"] = 9
    assert gate(rows)["gate_status"] == "INSUFFICIENT_EVIDENCE"


def test_invalid_binary_prediction_is_not_measured():
    rows = make_records()
    rows[0]["y_pred_v1"] = 2
    assert gate(rows)["gate_status"] == "NOT_MEASURED"


def test_report_hash_detects_post_hoc_tampering():
    result = gate(make_records())
    original_hash = result.pop("report_sha256")
    assert compute_sha256(result) == original_hash
    result["gate_status"] = "FAIL"
    assert compute_sha256(result) != original_hash


def test_input_hash_changes_when_training_manifest_changes():
    a = gate(make_records(), training_patient_ids=["TRAIN_PATIENT_A"])
    b = gate(make_records(), training_patient_ids=["TRAIN_PATIENT_B"])
    assert a["input_sha256"] != b["input_sha256"]


def test_empty_records_not_measured():
    assert gate([])["gate_status"] == "NOT_MEASURED"
