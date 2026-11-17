"""Independent audit's four adversarial tests, adapted to actual code."""
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
    p = load_protocol(root / 'clinical_benchmark_v0_2/protocols/ptbxl_mi_demo_protocol.json')
    evidence = build_evidence_package(p, rows, training_patient_ids=training, model_v1_id='BASE',model_v2_id='CAND')
    cp = tmp_path / 'clinical.json'
    cp.write_text(json.dumps(evidence), encoding='utf-8', newline='\n')
    return core.build_unified(tmp_path/'regulatory_assessment_SYNTHETIC.json', cp)


def _rehash(p):
    c=p['clinical_evidence']
    c['artifact_sha256']=core._sha_json({k:v for k,v in c.items() if k != 'artifact_sha256'})
    p['package_sha256']=core._sha_json({k:v for k,v in p.items() if k != 'package_sha256'})


def test_p0a_remove_all_required_cohort(tmp_path):
    p=_package(tmp_path,'pass')
    p['clinical_evidence']['cohort_evaluations']=[c for c in p['clinical_evidence']['cohort_evaluations'] if c['cohort_id'] != 'ALL']
    _rehash(p)
    with pytest.raises(ValueError,match='cohort|required_subgroups|ALL'):
        core.verify_unified(p)


def test_p0a_remove_failing_age75(tmp_path):
    p=_package(tmp_path,'fail')
    c=p['clinical_evidence']
    c['cohort_evaluations']=[x for x in c['cohort_evaluations'] if x['cohort_id']=='ALL']
    c['statistical_findings']['confirmed_demo_threshold_failures']=[]
    c['technical_gate']['reasons']=[]
    c['technical_gate']['status']='PASS'
    c['overall_gate_status']='PASS'
    _rehash(p)
    with pytest.raises(ValueError):
        core.verify_unified(p)


def test_p0b_derived_metrics_desync(tmp_path):
    p=_package(tmp_path,'pass')
    m=p['clinical_evidence']['cohort_evaluations'][0]['basic_metrics']
    m['sensitivity_v1']=1.0
    m['sensitivity_v2']=0.50
    m['sensitivity_drop']=0
    m['critical_fn_rate_v2']=0
    _rehash(p)
    with pytest.raises(ValueError,match='inconsisten|contradict|metric'):
        core.verify_unified(p)


def test_p0c_downgrade_fail(tmp_path):
    p=_package(tmp_path,'fail')
    c=p['clinical_evidence']
    c['technical_gate']['status']='INSUFFICIENT_EVIDENCE'
    c['overall_gate_status']='INSUFFICIENT_EVIDENCE'
    c['statistical_findings']['confirmed_demo_threshold_failures']=[]
    c['statistical_findings']['evidence_insufficiencies']=['Forged insufficiency']
    _rehash(p)
    with pytest.raises(ValueError,match='FAIL|contradict|metric'):
        core.verify_unified(p)


def test_p0d_regulatory_kind_tamper(tmp_path):
    p=_package(tmp_path,'pass')
    p['regulatory_document_triage']['kind']='MDR_CONFORMITY_APPROVED'
    p['regulatory_document_triage']['requirements']=[]
    _rehash(p)
    with pytest.raises(ValueError,match='regulatory_document_triage'):
        core.verify_unified(p)


def test_p0a_age75_only_confirmed_failure_cannot_be_removed(tmp_path):
    """ALL stays within point thresholds while required AGE75_PLUS fails."""
    core._legacy_modules()
    from src.clinical_validation.demo_runner import synthetic_fixture
    from src.clinical_validation.protocol_loader import load_protocol
    from src.clinical_validation.evidence_package_writer import build_evidence_package
    rows, training = synthetic_fixture('pass')
    changed = 0
    for r in rows:
        if r['y_true'] == 1 and r['age'] >= 75 and changed < 2:
            r['y_pred_v2'] = 0
            changed += 1
    assert changed == 2
    protocol = load_protocol(Path(__file__).resolve().parents[2] / 'clinical_benchmark_v0_2/protocols/ptbxl_mi_demo_protocol.json')
    clinical = build_evidence_package(protocol, rows, training_patient_ids=training,
                                      model_v1_id='BASE', model_v2_id='CAND')
    assert clinical['overall_gate_status'] == 'FAIL'
    assert clinical['cohort_evaluations'][0]['basic_metrics']['sensitivity_drop'] <= 0.02
    make_fixture(tmp_path)
    cp = tmp_path / 'clinical_age_fail.json'
    cp.write_text(json.dumps(clinical), encoding='utf-8', newline='\n')
    p = core.build_unified(tmp_path/'regulatory_assessment_SYNTHETIC.json', cp)
    c = p['clinical_evidence']
    c['cohort_evaluations'] = [v for v in c['cohort_evaluations'] if v['cohort_id'] != 'AGE75_PLUS']
    c['technical_gate']['status'] = 'PASS'
    c['technical_gate']['reasons'] = []
    c['statistical_findings']['confirmed_demo_threshold_failures'] = []
    c['statistical_findings']['evidence_insufficiencies'] = []
    c['overall_gate_status'] = 'PASS'
    _rehash(p)
    with pytest.raises(ValueError, match='required_subgroups'):
        core.verify_unified(p)
