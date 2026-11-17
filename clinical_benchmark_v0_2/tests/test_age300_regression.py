"""AGE-300: fail-closed handling for PTB-XL sentinel and unknown age.
Synthetic data only; no clinical validation or test-fold access.
"""
from copy import deepcopy
from pathlib import Path
import pytest
from src.clinical_validation import EvaluationPolicy, evaluate_model_regression
from src.clinical_validation.evidence_package_writer import build_evidence_package
from src.clinical_validation.protocol_loader import load_protocol
from src.clinical_validation.ptbxl_age_policy import ptbxl_age75_membership


def rows():
    out=[]
    for i in range(70):
        y=int(i<35)
        out.append(dict(ecg_id=f"AGE_ECG_{i}",patient_id=f"AGE_P_{i}",strat_fold=10,
                        age=80,subgroups=["ALL","AGE75_PLUS"],y_true=y,
                        y_pred_v1=y,y_pred_v2=y))
    return out


def core(records):
    return evaluate_model_regression(records,training_patient_ids=["NO_OVERLAP"],
        model_v1_id="baseline",model_v2_id="candidate",
        policy=EvaluationPolicy(required_subgroups=("ALL","AGE75_PLUS")))


def package(records):
    protocol=load_protocol(Path(__file__).resolve().parents[1] / "protocols" / "ptbxl_mi_demo_protocol.json")
    return build_evidence_package(protocol,records,training_patient_ids=["NO_OVERLAP"],
                                  model_v1_id="baseline",model_v2_id="candidate")


def test_age_300_sentinel_is_75_plus_not_literal_age():
    assert ptbxl_age75_membership(300) is True
    assert ptbxl_age75_membership(300.0) is True
    assert ptbxl_age75_membership(75) is True
    assert ptbxl_age75_membership(74) is False


def test_core_accepts_sentinel_300_if_correctly_tagged():
    a=rows();a[0]["age"]=300
    assert core(a)["gate_status"] == "PASS"


def test_writer_accepts_sentinel_300_if_correctly_tagged():
    a=rows();a[0]["age"]=300
    result=package(a)
    assert result["technical_gate"]["status"]=="PASS"
    assert result["overall_gate_status"]=="PASS"


def test_sentinel_missing_75_plus_is_rejected():
    a=rows();a[0]["age"]=300;a[0]["subgroups"]=["ALL"]
    assert core(a)["gate_status"]=="INSUFFICIENT_EVIDENCE"
    assert package(a)["overall_gate_status"]!="PASS"


@pytest.mark.parametrize("invalid",[None,float("nan"),float("inf"),-1,121,250,301,True,"300",""])
def test_unknown_invalid_age_never_passes(invalid):
    a=rows();a[0]["age"]=invalid
    assert core(a)["gate_status"]=="NOT_MEASURED"
    assert package(a)["overall_gate_status"]!="PASS"


def test_missing_age_never_silently_assigned_to_young_cohort():
    a=rows();a[0].pop("age")
    assert core(a)["gate_status"]=="NOT_MEASURED"
    assert package(a)["overall_gate_status"]!="PASS"


def test_non_sentinel_age_below_75_requires_no_elderly_tag():
    a=rows();a[0]["age"]=35;a[0]["subgroups"]=["ALL"]
    assert core(a)["gate_status"]=="PASS"
    assert package(a)["overall_gate_status"]=="PASS"
