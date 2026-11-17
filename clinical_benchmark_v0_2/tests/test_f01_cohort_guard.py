"""F-01: direct evaluator must never silently exclude test records from ALL.

Synthetic, de-identified data only. This is a NON-CLINICAL regression test.
"""
from copy import deepcopy
import math

import pytest

from src.clinical_validation import EvaluationPolicy, evaluate_model_regression
from src.clinical_validation.evidence_package_writer import build_evidence_package
from src.clinical_validation.protocol_loader import load_protocol
from pathlib import Path


def rows_90():
    rows = []
    for i in range(30):
        rows.append(dict(ecg_id=f"POS_{i}", patient_id=f"P_{i}", strat_fold=10,
                         age=82, subgroups=["ALL", "AGE75_PLUS"],
                         y_true=1, y_pred_v1=1, y_pred_v2=1))
    for i in range(30):
        rows.append(dict(ecg_id=f"NEG_{i}", patient_id=f"N_{i}", strat_fold=10,
                         age=82, subgroups=["ALL", "AGE75_PLUS"],
                         y_true=0, y_pred_v1=0, y_pred_v2=0))
    for i in range(30):
        rows.append(dict(ecg_id=f"MISS_{i}", patient_id=f"M_{i}", strat_fold=10,
                         age=82, subgroups=["OTHER"],
                         y_true=1, y_pred_v1=1, y_pred_v2=0))
    return rows


def evaluate(rows, required=("ALL", "AGE75_PLUS")):
    return evaluate_model_regression(rows,
        training_patient_ids=["UNRELATED_TRAIN"], model_v1_id="baseline",
        model_v2_id="candidate", policy=EvaluationPolicy(required_subgroups=required))


def test_f01_90_rows_with_missing_all_cannot_pass():
    rows = rows_90()
    result = evaluate(rows, ("ALL",))
    assert result["gate_status"] == "NOT_MEASURED"
    assert result["subgroup_metrics"] == {}
    assert any("ALL" in r for r in result["reasons"])


def test_valid_rows_still_pass():
    rows = rows_90()[:60]
    result = evaluate(rows)
    assert result["gate_status"] == "PASS"
    assert result["subgroup_metrics"]["ALL"]["n_total"] == 60
    assert result["subgroup_metrics"]["AGE75_PLUS"]["n_total"] == 60


def test_missing_age_is_rejected_when_75_plus_is_required():
    rows = rows_90()[:60]
    rows[0].pop("age")
    result = evaluate(rows)
    assert result["gate_status"] == "NOT_MEASURED"
    assert result["subgroup_metrics"] == {}


def test_age_82_missing_age75_label_is_rejected():
    rows = rows_90()[:60]
    rows[0]["subgroups"] = ["ALL"]
    result = evaluate(rows)
    assert result["gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["subgroup_metrics"] == {}


def test_age_32_wrongly_in_age75_label_is_rejected():
    rows = rows_90()[:60]
    rows[0]["age"] = 32
    result = evaluate(rows)
    assert result["gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert result["subgroup_metrics"] == {}


def test_duplicate_all_tags_are_rejected():
    rows = rows_90()[:60]
    rows[0]["subgroups"].append("ALL")
    result = evaluate(rows)
    assert result["gate_status"] == "NOT_MEASURED"


@pytest.mark.parametrize("bad_age", [True, "82", -1, 121, float("nan"), float("inf")])
def test_invalid_ages_are_rejected(bad_age):
    rows = rows_90()[:60]
    rows[0]["age"] = bad_age
    result = evaluate(rows)
    assert result["gate_status"] == "NOT_MEASURED"
    assert result["subgroup_metrics"] == {}


def test_legacy_non_age_based_subgroup_still_works_without_age():
    rows = rows_90()[:60]
    for row in rows:
        row.pop("age")
        row["subgroups"] = ["ALL", "F_65_PLUS"]
    result = evaluate(rows, ("ALL", "F_65_PLUS"))
    assert result["gate_status"] == "PASS"


def test_upper_layer_still_rejects_bad_age_membership():
    rows = rows_90()
    path = Path(__file__).resolve().parent.parent / "protocols" / "ptbxl_mi_demo_protocol.json"
    protocol = load_protocol(path)
    package = build_evidence_package(protocol, rows, training_patient_ids=["UNRELATED_TRAIN"],
                                     model_v1_id="baseline", model_v2_id="candidate")
    assert package["overall_gate_status"] != "PASS"
