"""Synthetic-only independent source recomputation and tamper checks."""
import copy
from pathlib import Path
import pytest
from medai_unified_v0_3 import core


def _data(scenario='pass'):
    core._legacy_modules()
    from src.clinical_validation.demo_runner import synthetic_fixture
    from src.clinical_validation.protocol_loader import load_protocol
    from src.clinical_validation.evidence_package_writer import build_evidence_package
    proto = load_protocol(Path(__file__).resolve().parents[2] / 'clinical_benchmark_v0_2/protocols/ptbxl_mi_demo_protocol.json')
    rows, train = synthetic_fixture(scenario)
    pack = build_evidence_package(proto, rows, training_patient_ids=train, model_v1_id='base', model_v2_id='candidate')
    return pack, rows, train, proto


def test_research_metrics_generated_and_source_recomputes():
    p, rows, train, _ = _data()
    assert p['exploratory_estimands']['cohorts']['ALL']['sensitivity']['patient_weighted'] is not None
    assert core.verify_exploratory_against_records(p, rows, train) == 'EXPLORATORY_SOURCE_RECOMPUTED_NOT_AUTHENTICATED'


def test_no_gate_change_on_research_addendum():
    p, _, _, _ = _data('fail')
    assert p['overall_gate_status'] == 'FAIL'
    assert p['manufacturer_release_decision'] == 'OUTSIDE_PLATFORM_SCOPE'
    assert p['exploratory_estimands']['scope'] == 'RESEARCH_ONLY_NOT_A_CLINICAL_GATE'
    core._verify_clinical(p, core._legacy_modules()[2])


def test_rehashed_manipulated_patient_estimate_rejected_if_source_provided():
    p, rows, train, _ = _data()
    p['exploratory_estimands']['cohorts']['ALL']['sensitivity']['patient_weighted']['candidate'] += .05
    from src.clinical_validation.clinical_eval_runner import compute_sha256
    p['artifact_sha256'] = compute_sha256({k: v for k, v in p.items() if k != 'artifact_sha256'})
    with pytest.raises(ValueError, match='failed source recomputation'):
        core.verify_exploratory_against_records(p, rows, train)


def test_source_manifest_change_rejected():
    p, rows, train, _ = _data()
    train = train + ['new_training_patient']
    with pytest.raises(ValueError, match='do not match'):
        core.verify_exploratory_against_records(p, rows, train)


def test_no_raw_patient_ids_in_aggregate_json():
    p, rows, _, _ = _data()
    import json
    body = json.dumps(p['exploratory_estimands'])
    assert rows[0]['patient_id'] not in body


def test_original_missing_prediction_does_not_crash():
    p, _, _, _ = _data('not_measured')
    assert p['overall_gate_status'] == 'NOT_MEASURED'
    assert p['exploratory_estimands'] is None
