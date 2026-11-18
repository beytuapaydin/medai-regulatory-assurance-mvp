"""AUD-05: synthetic-only contract tests for two distinct research APIs.

No PTB-XL files, real ECGs, external holdout data, or waveforms.
'PASS' below means the *synthetic engine test* met demo criteria, not clinical validity.
"""
from pathlib import Path

from src.clinical_validation import EvaluationPolicy, evaluate_model_regression
from src.clinical_validation.evidence_package_writer import build_evidence_package
from src.clinical_validation.protocol_loader import load_protocol


PROTOCOL = load_protocol(
    Path(__file__).resolve().parents[1] / "protocols" / "ptbxl_mi_demo_protocol.json"
)


def synthetic_records(*, tags, include_age=False, age=80):
    records = []
    for i in range(80):
        label = int(i < 40)
        record = {
            "ecg_id": f"AUD05_ECG_{i}",
            "patient_id": f"AUD05_PAT_{i}",
            "strat_fold": 10,  # Synthetic fixture ONLY; never accesses real Fold 10.
            "subgroups": list(tags),
            "y_true": label,
            "y_pred_v1": label,
            "y_pred_v2": label,
        }
        if include_age:
            record["age"] = age
        records.append(record)
    return records


def generic(records, *, required=("ALL", "F_65_PLUS")):
    policy = EvaluationPolicy(required_subgroups=required)
    return evaluate_model_regression(
        records,
        training_patient_ids=["AUD05_TRAIN_NOT_IN_TEST"],
        model_v1_id="base-synthetic",
        model_v2_id="candidate-synthetic",
        policy=policy,
        is_synthetic_run=True,
    )


def ptbxl_package(records):
    return build_evidence_package(
        PROTOCOL,
        records,
        training_patient_ids=["AUD05_TRAIN_NOT_IN_TEST"],
        model_v1_id="base-synthetic",
        model_v2_id="candidate-synthetic",
        source_type="SYNTHETIC_ENGINE_TEST",
    )


def test_legacy_tag_without_age_can_pass_generic_but_not_ptbxl_package():
    records = synthetic_records(tags=("ALL", "F_65_PLUS"))
    core = generic(records)
    packaged = ptbxl_package(records)
    assert core["gate_status"] == "PASS"
    assert core["evidence_scope"] == "ENGINE_TEST_ONLY"
    assert packaged["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert packaged["technical_gate"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert any("age" in reason.lower() for reason in packaged["technical_gate"]["reasons"])
    assert packaged["real_ptbxl_validation_completed"] is False


def test_extra_legacy_tag_with_valid_age_still_cannot_be_promoted():
    records = synthetic_records(tags=("ALL", "F_65_PLUS"), include_age=True, age=40)
    core = generic(records)
    packaged = ptbxl_package(records)
    assert core["gate_status"] == "PASS"
    assert packaged["overall_gate_status"] == "INSUFFICIENT_EVIDENCE"
    assert any("subgroup tags disagree with age" in reason
               for reason in packaged["technical_gate"]["reasons"])


def test_ptbxl_allowed_age_derived_tags_produce_consistent_demo_pass():
    records = synthetic_records(tags=("ALL", "AGE75_PLUS"), include_age=True, age=80)
    core = generic(records, required=("ALL", "AGE75_PLUS"))
    packaged = ptbxl_package(records)
    assert core["gate_status"] == "PASS"
    assert packaged["technical_gate"]["status"] == "PASS"
    assert packaged["overall_gate_status"] == "PASS"
    assert packaged["source_type"] == "SYNTHETIC_ENGINE_TEST"
    assert packaged["real_ptbxl_validation_completed"] is False
    assert packaged["manufacturer_release_decision"] == "OUTSIDE_PLATFORM_SCOPE"
