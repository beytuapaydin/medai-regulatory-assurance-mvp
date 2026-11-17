"""Integration tests built against the user-uploaded MedAI_Integrated_v1 source files."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from medai_unified_v0_3 import core
from medai_unified_v0_3.make_fixture import make_fixture


@pytest.fixture
def assessment(tmp_path):
    make_fixture(tmp_path)
    return tmp_path / 'regulatory_assessment_SYNTHETIC.json'


@pytest.fixture
def clinical_factory(tmp_path):
    def build(scenario):
        core._legacy_modules()
        from src.clinical_validation.demo_runner import synthetic_fixture
        from src.clinical_validation.protocol_loader import load_protocol
        from src.clinical_validation.evidence_package_writer import build_evidence_package
        protocol_path = Path(__file__).resolve().parents[2] / 'clinical_benchmark_v0_2' / 'protocols' / 'ptbxl_mi_demo_protocol.json'
        p = load_protocol(protocol_path)
        rows, training = synthetic_fixture(scenario)
        package = build_evidence_package(p, rows, training_patient_ids=training,
                                         model_v1_id='SYNTHETIC-BASE', model_v2_id='SYNTHETIC-CAND',
                                         source_type='SYNTHETIC_ENGINE_TEST')
        target = tmp_path / f'clinical_{scenario}.json'
        target.write_text(json.dumps(package), encoding='utf8')
        return target
    return build


@pytest.mark.parametrize('scenario,expected', [('pass','PASS'), ('fail','FAIL'),
                                              ('insufficient','INSUFFICIENT_EVIDENCE'),
                                              ('not_measured','NOT_MEASURED')])
def test_four_states_no_regulatory_conformity(assessment, clinical_factory, scenario, expected):
    unified = core.build_unified(assessment, clinical_factory(scenario))
    assert unified['clinical_evidence']['overall_gate_status'] == expected
    assert unified['regulatory_document_triage']['requirement_count'] == 13
    assert unified['manufacturer_release_decision'] == 'OUTSIDE_PLATFORM_SCOPE'
    assert unified['retrieval_quality_benchmark']['state'] == 'NOT_PROVIDED'
    core.verify_unified(unified)


def test_deterministic_same_inputs_same_digest(assessment, clinical_factory):
    path = clinical_factory('pass')
    a, b = core.build_unified(assessment, path), core.build_unified(assessment, path)
    assert a == b
    assert a['package_sha256'] == b['package_sha256']


def test_reject_modified_clinical_digest(assessment, clinical_factory):
    p = clinical_factory('pass')
    data = json.loads(p.read_text())
    data['overall_gate_status'] = 'FAIL'
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Clinical artifact SHA-256 mismatch'):
        core.build_unified(assessment,p)


def test_reject_tampered_regulatory_source(assessment, clinical_factory):
    data = json.loads(assessment.read_text())
    data['requirements'][0]['requirement'] = 'modified'
    assessment.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Requirement text integrity invalid'):
        core.build_unified(assessment, clinical_factory('pass'))


def test_reject_missing_requirement(assessment, clinical_factory):
    data = json.loads(assessment.read_text())
    data['requirements'].pop()
    assessment.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='13 requirement'):
        core.build_unified(assessment, clinical_factory('pass'))


def test_review_record_does_not_override_fail(assessment, clinical_factory, tmp_path):
    unified = core.build_unified(assessment, clinical_factory('fail'))
    package_path = core.write_package(unified, tmp_path / 'package.json')
    log = tmp_path / 'human_reviews.jsonl'
    first = core.append_unified_review(package_path,log,'demo-reviewer',
                        'EVIDENCE_ACCEPTED_FOR_FURTHER_QMS_REVIEW',
                        'Reviewed source evidence for further QMS assessment only.')
    assert first['observed_clinical_gate'] == 'FAIL'
    assert len(core.read_unified_reviews(log, unified)) == 1
    second = core.append_unified_review(package_path, log, 'demo-reviewer',
                       'FOLLOW_UP_REQUIRED', 'Additional validation work is needed before release consideration.')
    assert second['previous_sha256'] == first['event_sha256']
    assert len(core.read_unified_reviews(log, unified)) == 2
    assert json.loads(package_path.read_text())['clinical_evidence']['overall_gate_status'] == 'FAIL'


def test_review_log_tampering_detected(assessment, clinical_factory, tmp_path):
    unified = core.build_unified(assessment, clinical_factory('fail'))
    p = core.write_package(unified, tmp_path / 'u.json')
    log = tmp_path / 'reviews.jsonl'
    core.append_unified_review(p, log, 'human-reviewer', 'REVIEWED_WITH_FINDINGS',
                               'The synthetic gate failed a predefined test threshold.')
    line = json.loads(log.read_text())
    line['disposition'] = 'EVIDENCE_ACCEPTED_FOR_FURTHER_QMS_REVIEW'
    log.write_text(json.dumps(line) + '\n')
    with pytest.raises(ValueError, match='integrity/scope'):
        core.read_unified_reviews(log, unified)


def test_unified_artifact_tampering_detected(assessment, clinical_factory):
    p = core.build_unified(assessment, clinical_factory('pass'))
    p['regulatory_document_triage']['current_human_reviews'] = 12
    with pytest.raises(ValueError, match='Unified package SHA-256'):
        core.verify_unified(p)


def test_regulatory_reviewer_status_not_compliance(assessment, clinical_factory, tmp_path):
    _, legacy, _ = core._legacy_modules()
    data = json.loads(assessment.read_text())
    source_sha = legacy.sha(assessment.read_text())
    event = legacy.make_event(data, source_sha, [], {
        'requirement_id':'DEMO-REQ-01', 'candidate_id':'SYNTHETIC-DOC-01',
        'relevance':'RELEVANT', 'sufficiency':'REVIEWER_CONSIDERS_SUFFICIENT',
        'reviewer':'synthetic-reviewer',
        'rationale':'SYNTHETIC REVIEW ONLY - illustrative quality assessment.',
        'gap':'Additional actual controlled records still required.'})
    log = tmp_path / 'reg_events.jsonl'
    log.write_text(legacy.canonical(event)+'\n')
    unified=core.build_unified(assessment,clinical_factory('pass'), log)
    assert unified['regulatory_document_triage']['current_human_reviews'] == 1
    row = unified['regulatory_document_triage']['requirements'][0]
    assert row['evidence_review_state'] == 'REVIEWER_CONSIDERS_SUFFICIENT_NOT_APPROVED'
    assert unified['manufacturer_release_decision'] == 'OUTSIDE_PLATFORM_SCOPE'


def test_regulatory_hash_chain_tampered(assessment, clinical_factory, tmp_path):
    _, legacy, _ = core._legacy_modules()
    data = json.loads(assessment.read_text())
    event = legacy.make_event(data,legacy.sha(assessment.read_text()),[],{
        'requirement_id':'DEMO-REQ-01', 'candidate_id':'SYNTHETIC-DOC-01',
        'relevance':'RELEVANT','sufficiency':'PARTIAL','reviewer':'synthetic-reviewer',
        'rationale':'SYNTHETIC REVIEW - no compliance inference.', 'gap':''})
    event['rationale'] = 'changed after review'
    path = tmp_path / 'reviews.jsonl'
    path.write_text(json.dumps(event)+'\n')
    with pytest.raises(ValueError,match='hash-chain mismatch'):
        core.build_unified(assessment,clinical_factory('pass'),path)


def test_reject_review_override_request(assessment,clinical_factory,tmp_path):
    pkg = core.build_unified(assessment, clinical_factory('fail'))
    p = core.write_package(pkg,tmp_path/'evidence.json')
    with pytest.raises(ValueError,match='Unsupported reviewer disposition'):
        core.append_unified_review(p,tmp_path/'review.jsonl','demo', 'OVERRIDE_FAIL_TO_PASS',
                                   'Not permitted to overwrite technical gate outcomes.')


def test_no_package_overwrite(assessment,clinical_factory,tmp_path):
    pkg = core.build_unified(assessment,clinical_factory('pass'))
    p = tmp_path / 'evidence.json'
    core.write_package(pkg,p)
    with pytest.raises(FileExistsError):core.write_package(pkg,p)
