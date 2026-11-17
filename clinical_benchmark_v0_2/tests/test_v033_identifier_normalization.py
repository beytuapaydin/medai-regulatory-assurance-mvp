"""Adversarial regression tests for P0-2 identifier normalization (synthetic data only)."""
from pathlib import Path
import pytest
from src.clinical_validation.clinical_eval_runner import evaluate_model_regression
from src.clinical_validation.demo_runner import synthetic_fixture
from src.clinical_validation.evidence_package_writer import build_evidence_package
from src.clinical_validation.protocol_loader import load_protocol
from src.clinical_validation.paired_statistics import patient_cluster_paired_sensitivity_ci

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = load_protocol(ROOT / "protocols" / "ptbxl_mi_demo_protocol.json")


def test_whitespace_padded_patient_id_rejected_as_not_measured():
    rows, train = synthetic_fixture("pass")
    rows[0]["patient_id"] = rows[0]["patient_id"] + " "
    report = evaluate_model_regression(
        rows, training_patient_ids=train,
        model_v1_id="BASE", model_v2_id="CAND",
        policy=PROTOCOL.engine_policy,
    )
    assert report["gate_status"] == "NOT_MEASURED"
    assert any("patient_id" in r for r in report["reasons"])


def test_whitespace_padded_single_patient_cannot_inflate_clusters():
    rows, train = synthetic_fixture("pass")
    for idx, row in enumerate(rows):
        if row["y_true"] == 0:
            row["patient_id"] = "SINGLE_NEG_PAT" + (" " * (idx + 1))
    pkg = build_evidence_package(
        PROTOCOL, rows, training_patient_ids=train,
        model_v1_id="BASE", model_v2_id="CAND",
    )
    assert pkg["overall_gate_status"] == "NOT_MEASURED"


def test_whitespace_padded_training_manifest_id_rejected():
    rows, _ = synthetic_fixture("pass")
    leaked_padded = rows[0]["patient_id"] + " "
    pkg = build_evidence_package(
        PROTOCOL, rows, training_patient_ids=[leaked_padded],
        model_v1_id="BASE", model_v2_id="CAND",
    )
    assert pkg["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert any("Training patient manifest contains invalid" in r for r in pkg["technical_gate"]["reasons"])


def test_case_variant_train_test_patient_leakage_detected():
    rows, _ = synthetic_fixture("pass")
    leaked_lower = rows[0]["patient_id"].lower()
    pkg = build_evidence_package(
        PROTOCOL, rows, training_patient_ids=[leaked_lower],
        model_v1_id="BASE", model_v2_id="CAND",
    )
    assert pkg["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert any("Patient leakage" in r for r in pkg["technical_gate"]["reasons"])


def test_case_variant_patient_ids_do_not_inflate_clusters():
    rows, train = synthetic_fixture("pass")
    for idx, row in enumerate(rows):
        if row["y_true"] == 0:
            row["patient_id"] = "same_neg_pat" if idx % 2 == 0 else "SAME_NEG_PAT"
    pkg = build_evidence_package(
        PROTOCOL, rows, training_patient_ids=train,
        model_v1_id="BASE", model_v2_id="CAND",
    )
    assert pkg["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert pkg["cohort_evaluations"][0]["basic_metrics"]["n_negative_patients"] == 1


def test_float_string_patient_id_leakage_detected():
    rows, train = synthetic_fixture("pass")
    rows[0]["patient_id"] = "15709.0"
    pkg = build_evidence_package(
        PROTOCOL, rows, training_patient_ids=[*train, "15709"],
        model_v1_id="BASE", model_v2_id="CAND",
    )
    assert pkg["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert any("Patient leakage" in r for r in pkg["technical_gate"]["reasons"])


def test_duplicate_ecg_id_case_or_whitespace_rejected():
    rows, train = synthetic_fixture("pass")
    rows[1]["ecg_id"] = rows[0]["ecg_id"].lower()
    pkg = build_evidence_package(
        PROTOCOL, rows, training_patient_ids=train,
        model_v1_id="BASE", model_v2_id="CAND",
    )
    assert pkg["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert any("Duplicate ecg_id" in r for r in pkg["technical_gate"]["reasons"])


def test_bootstrap_canonicalizes_case_variant_positive_clusters():
    rows = [
        {"patient_id": "pos_pat_1" if i % 2 == 0 else "POS_PAT_1", "y_true": 1, "y_pred_v1": 1, "y_pred_v2": 0}
        for i in range(40)
    ]
    stat = patient_cluster_paired_sensitivity_ci(rows, confidence_level=0.95, replicates=250, seed=1701)
    assert stat["unique_positive_patient_clusters"] == 1

