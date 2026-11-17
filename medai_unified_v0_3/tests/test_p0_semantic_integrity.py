"""Adversarial semantic verification checks for recomputed unkeyed hashes."""
import json
from pathlib import Path
import pytest
from medai_unified_v0_3 import core
from medai_unified_v0_3.make_fixture import make_fixture


def _package(tmp_path, scenario):
    core._legacy_modules()
    from src.clinical_validation.demo_runner import synthetic_fixture
    from src.clinical_validation.protocol_loader import load_protocol
    from src.clinical_validation.evidence_package_writer import build_evidence_package
    root = Path(__file__).resolve().parents[2]
    make_fixture(tmp_path)
    rows, training = synthetic_fixture(scenario)
    protocol = load_protocol(root / 'clinical_benchmark_v0_2' / 'protocols' / 'ptbxl_mi_demo_protocol.json')
    evidence = build_evidence_package(
        protocol, rows, training_patient_ids=training,
        model_v1_id='BASELINE', model_v2_id='CANDIDATE',
    )
    clinical_path = tmp_path / 'clinical.json'
    clinical_path.write_text(json.dumps(evidence), encoding='utf-8')
    return core.build_unified(tmp_path / 'regulatory_assessment_SYNTHETIC.json', clinical_path)


def _recompute_hashes(unified):
    clinical = unified['clinical_evidence']
    clinical['artifact_sha256'] = core._sha_json({k: v for k, v in clinical.items() if k != 'artifact_sha256'})
    unified['package_sha256'] = core._sha_json({k: v for k, v in unified.items() if k != 'package_sha256'})


def test_rehashed_fail_to_pass_is_rejected(tmp_path):
    p = _package(tmp_path, 'fail')
    p['clinical_evidence']['overall_gate_status'] = 'PASS'
    _recompute_hashes(p)
    with pytest.raises(ValueError, match='contradicts underlying gate'):
        core.verify_unified(p)


def test_rehashed_pass_with_insufficient_patient_clusters_is_rejected(tmp_path):
    p = _package(tmp_path, 'pass')
    p['clinical_evidence']['cohort_evaluations'][0]['basic_metrics']['n_negative_patients'] = 1
    _recompute_hashes(p)
    with pytest.raises(ValueError, match='insufficient cohort patient'):
        core.verify_unified(p)


def test_rehashed_pass_with_failing_metric_is_rejected(tmp_path):
    p = _package(tmp_path, 'pass')
    p['clinical_evidence']['cohort_evaluations'][0]['basic_metrics']['specificity_drop'] = 0.6
    _recompute_hashes(p)
    with pytest.raises(ValueError, match='contradicts observed metric'):
        core.verify_unified(p)


def test_rehashed_pass_without_ci_is_rejected(tmp_path):
    p = _package(tmp_path, 'pass')
    p['clinical_evidence']['cohort_evaluations'][0]['paired_sensitivity_delta_ci'] = None
    _recompute_hashes(p)
    with pytest.raises(ValueError, match='lacks paired sensitivity'):
        core.verify_unified(p)


def test_clean_package_still_verifies(tmp_path):
    for status in ('pass', 'fail', 'insufficient', 'not_measured'):
        target = tmp_path / status
        target.mkdir()
        core.verify_unified(_package(target, status))
