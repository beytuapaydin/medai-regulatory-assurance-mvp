"""Synthetic adversarial regressions for P0-1. No real ECG data."""
from pathlib import Path
from copy import deepcopy
import pytest
from src.clinical_validation.demo_runner import synthetic_fixture
from src.clinical_validation.clinical_eval_runner import evaluate_model_regression
from src.clinical_validation.protocol_loader import load_protocol, ProtocolError
from src.clinical_validation.evidence_package_writer import build_evidence_package

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = load_protocol(ROOT / 'protocols' / 'ptbxl_mi_demo_protocol.json')


def _repeated_negative_patient_rows():
    rows, train = synthetic_fixture('pass')
    for row in rows:
        if row['y_true'] == 0:
            row['patient_id'] = 'SINGLE_NEGATIVE_PATIENT'
    return rows, train


def test_direct_engine_blocks_one_negative_patient():
    rows, train = _repeated_negative_patient_rows()
    report = evaluate_model_regression(
        rows, training_patient_ids=train,
        model_v1_id='BASELINE', model_v2_id='CANDIDATE',
        policy=PROTOCOL.engine_policy,
    )
    assert report['gate_status'] == 'INSUFFICIENT_EVIDENCE'
    assert report['subgroup_metrics']['ALL']['n_negative_patients'] == 1
    assert report['subgroup_metrics']['ALL']['measured'] is False


def test_protocol_to_evidence_blocks_one_negative_patient():
    rows, train = _repeated_negative_patient_rows()
    package = build_evidence_package(
        PROTOCOL, rows, training_patient_ids=train,
        model_v1_id='BASELINE', model_v2_id='CANDIDATE',
    )
    assert package['overall_gate_status'] == 'INSUFFICIENT_EVIDENCE'
    assert any('distinct negative patients' in x for x in package['technical_gate']['reasons'])


def test_one_positive_patient_is_insufficient():
    rows, train = synthetic_fixture('pass')
    for row in rows:
        if row['y_true'] == 1:
            row['patient_id'] = 'SINGLE_POSITIVE_PATIENT'
    report = evaluate_model_regression(
        rows, training_patient_ids=train,
        model_v1_id='BASELINE', model_v2_id='CANDIDATE',
        policy=PROTOCOL.engine_policy,
    )
    assert report['gate_status'] == 'INSUFFICIENT_EVIDENCE'


def test_protocol_rejects_missing_negative_patient_rule(tmp_path):
    import json
    data = deepcopy(PROTOCOL.data)
    del data['rules']['min_negative_patients']
    p = tmp_path / 'protocol.json'
    p.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ProtocolError, match='min_negative_patients'):
        load_protocol(p)


def test_confirmed_failure_not_masked_by_other_insufficiency():
    rows, train = synthetic_fixture('fail')
    for row in rows:
        if row['y_true'] == 0 and row['age'] >= 75:
            row['patient_id'] = 'SINGLE_NEGATIVE_PATIENT_AGE75'
    report = build_evidence_package(
        PROTOCOL, rows, training_patient_ids=train,
        model_v1_id='BASELINE', model_v2_id='CANDIDATE',
    )
    assert report['overall_gate_status'] == 'FAIL'
