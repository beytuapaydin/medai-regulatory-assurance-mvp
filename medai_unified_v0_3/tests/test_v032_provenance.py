"""Source-binding & semantic-scope checks on synthetic evidence packages."""
import json
import pytest
from .test_redteam_v032 import _package, _rehash
from medai_unified_v0_3 import core


def test_source_binding_detects_different_clinical_file(tmp_path):
    p = _package(tmp_path, 'pass')
    assessment_path = tmp_path / 'regulatory_assessment_SYNTHETIC.json'
    clinical_path = tmp_path / 'clinical.json'
    core.verify_unified(p, assessment_path=assessment_path, clinical_path=clinical_path)
    clinical_path.write_text(clinical_path.read_text() + ' ', encoding='utf-8')
    with pytest.raises(ValueError, match='Source clinical raw SHA-256 mismatch'):
        core.verify_unified(p, assessment_path=assessment_path, clinical_path=clinical_path)


def test_source_binding_detects_modified_assessment(tmp_path):
    p = _package(tmp_path, 'pass')
    assessment_path = tmp_path / 'regulatory_assessment_SYNTHETIC.json'
    clinical_path = tmp_path / 'clinical.json'
    data=json.loads(assessment_path.read_text())
    data['requirements'][0]['requirement'] += ' TAMPERED'
    assessment_path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='Source assessment raw SHA-256 mismatch'):
        core.verify_unified(p, assessment_path=assessment_path, clinical_path=clinical_path)


def test_nonpass_downgrade_not_measured_detected(tmp_path):
    p = _package(tmp_path, 'fail')
    c = p['clinical_evidence']
    c['overall_gate_status'] = 'NOT_MEASURED'
    c['technical_gate']['status'] = 'NOT_MEASURED'
    c['statistical_findings']['confirmed_demo_threshold_failures'] = []
    _rehash(p)
    with pytest.raises(ValueError, match='FAIL'):
        core.verify_unified(p)


def test_manifest_required_subgroup_cannot_be_suppressed_by_status_downgrade(tmp_path):
    p = _package(tmp_path, 'insufficient')
    p['clinical_evidence']['cohort_evaluations'].pop()
    _rehash(p)
    with pytest.raises(ValueError, match='required_subgroups'):
        core.verify_unified(p)
