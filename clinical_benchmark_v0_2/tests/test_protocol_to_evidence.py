"""New acceptance tests. All data are fabricated. No ECG is included."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from src.clinical_validation.protocol_loader import ProtocolError, load_protocol
from src.clinical_validation.demo_runner import synthetic_fixture
from src.clinical_validation.evidence_package_writer import build_evidence_package, write_evidence_files
from src.clinical_validation.clinical_eval_runner import compute_sha256

PROTOCOL = load_protocol(Path(__file__).parents[1] / "protocols" / "ptbxl_mi_demo_protocol.json")


def assess(scenario):
    records, train = synthetic_fixture(scenario)
    return build_evidence_package(PROTOCOL, records, training_patient_ids=train,
                                  model_v1_id="v1", model_v2_id="v2")


def test_stable_meets_demo_criteria():
    package = assess("pass")
    assert package["overall_gate_status"] == "PASS"
    assert all(c["paired_sensitivity_delta_ci"]["ci_lower"] == 0 for c in package["cohort_evaluations"])
    assert package["source_type"] == "SYNTHETIC_ENGINE_TEST"
    assert package["real_ptbxl_validation_completed"] is False


def test_declared_subgroup_regression_fails():
    package = assess("fail")
    assert package["overall_gate_status"] == "FAIL"
    assert any("AGE75_PLUS" in reason for reason in package["technical_gate"]["reasons"])
    assert package["change_classification"]["clinical_consequence_tier"] == "TBD_BY_MANUFACTURER"


def test_insufficient_age_group_does_not_pass():
    package = assess("insufficient")
    assert package["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert any("AGE75_PLUS" in reason for reason in package["technical_gate"]["reasons"])


def test_missing_prediction_not_measured():
    assert assess("not_measured")["overall_gate_status"] == "NOT_MEASURED"


def test_leakage_never_passes():
    rows, train = synthetic_fixture("pass")
    train.append(rows[0]["patient_id"])
    package = build_evidence_package(PROTOCOL, rows, training_patient_ids=train,
                                     model_v1_id="v1", model_v2_id="v2")
    assert package["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert "Patient leakage" in str(package["technical_gate"]["reasons"])


def test_false_subgroup_tag_never_passes():
    rows, train = synthetic_fixture("pass")
    rows[0]["subgroups"] = ["ALL"]
    package = build_evidence_package(PROTOCOL, rows, training_patient_ids=train,
                                     model_v1_id="v1", model_v2_id="v2")
    assert package["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert "disagree with age" in str(package["technical_gate"]["reasons"])


def test_missing_training_manifest_never_passes():
    rows, _ = synthetic_fixture("pass")
    package = build_evidence_package(PROTOCOL, rows, training_patient_ids=None,
                                     model_v1_id="v1", model_v2_id="v2")
    assert package["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"


def test_empty_training_manifest_never_passes():
    rows, _ = synthetic_fixture("pass")
    package = build_evidence_package(PROTOCOL, rows, training_patient_ids=[],
                                     model_v1_id="v1", model_v2_id="v2")
    assert package["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"


def test_hash_is_stable_and_detects_mutation():
    a = assess("pass")
    b = assess("pass")
    assert a == b
    original = a.pop("artifact_sha256")
    assert compute_sha256(a) == original
    a["overall_gate_status"] = "FAIL"
    assert compute_sha256(a) != original


def test_protocol_prevents_unbounded_filter_expression(tmp_path):
    raw = deepcopy(PROTOCOL.data)
    raw["required_subgroups"] = ["ALL", "age > 75 and eval('payload')"]
    p = tmp_path / "evil.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProtocolError):
        load_protocol(p)


def test_report_html_does_not_claim_real_validation(tmp_path):
    json_path, html_path = write_evidence_files(assess("pass"), tmp_path)
    report = html_path.read_text(encoding="utf-8")
    assert "Research-only demonstration" in report
    assert "No real PTB-XL model performance" in report
    assert json.loads(json_path.read_text(encoding="utf-8"))["overall_gate_status"] == "PASS"


def test_review_does_not_modify_gate():
    result = assess("fail")
    assert result["human_review"]["status"] == "PENDING_REVIEW"
    assert result["human_review"]["technical_result_can_be_overridden"] is False
    assert result["manufacturer_release_decision"] == "OUTSIDE_PLATFORM_SCOPE"


def test_corrupted_nonhashable_subgroup_tags_returns_insufficient():
    rows, train = synthetic_fixture("pass")
    rows[0]["subgroups"] = [["AGE75_PLUS"], "ALL"]
    package = build_evidence_package(PROTOCOL, rows, training_patient_ids=train,
                                     model_v1_id="v1", model_v2_id="v2")
    assert package["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"


def test_nonfinite_values_never_pass():
    rows, train = synthetic_fixture("pass")
    rows[0]["age"] = float("nan")
    package = build_evidence_package(PROTOCOL, rows, training_patient_ids=train,
                                     model_v1_id="v1", model_v2_id="v2")
    assert package["overall_gate_status"] == "NOT_MEASURED"
