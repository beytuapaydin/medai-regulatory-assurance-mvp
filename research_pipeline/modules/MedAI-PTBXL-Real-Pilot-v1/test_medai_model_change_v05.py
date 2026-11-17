"""Adversarial and end-to-end regression tests using synthetic v0.4 fixture; no real PTB-XL."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import medai_real_evidence_v04 as upstream
from test_medai_real_evidence_v04 import environment, write
from medai_model_change_v05 import (
    ChangeError, FILE_HTML, FILE_JSON, FILE_MD, build,
    digest, doc_digest, original_paths, read_json, render_html,
    render_markdown, verify_inventory, verify_outputs, write_atomic,
)


@pytest.fixture
def ready(environment):
    root, protocol = environment
    pilot = root / 'benchmark_v1' / 'pilot_v1'
    pkg = pilot / 'real_evidence_v04' / 'research_evidence.json'
    write(pkg, upstream.build(root, protocol))
    inv = pilot / 'audit_snapshot_v04' / 'sha256_inventory.csv'
    inv.parent.mkdir(exist_ok=True)
    make_inventory(inv, root, protocol)
    return root, protocol, inv, pkg, pilot / 'model_change_v05'


def make_inventory(inv: Path, root: Path, protocol: Path):
    with inv.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Path', 'Hash'])
        writer.writeheader()
        for path in original_paths(root, protocol).values():
            writer.writerow({'Path': str(path.resolve()), 'Hash': digest(path)})


def make_reports(ready):
    root, protocol, inv, pkg, out = ready
    a = build(root, protocol, inv, pkg)
    write_atomic(out / FILE_JSON, json.dumps(a, indent=2) + '\n')
    write_atomic(out / FILE_MD, render_markdown(a))
    write_atomic(out / FILE_HTML, render_html(a))
    verify_outputs(out, root, protocol, inv, pkg)
    return a


def test_end_to_end_verify_all_formats(ready):
    a = make_reports(ready)
    assert a['schema_version'].endswith('v0.5')
    assert a['clinical_gate'] == 'NOT_EVALUATED'
    assert a['release_decision'] == 'OUTSIDE_PLATFORM_SCOPE'
    assert a['evaluation_conclusion'] == 'CLINICAL_MODEL_CHANGE_BENEFIT_NOT_ESTABLISHED'
    assert a['dataset']['fold10'] == 'NOT_ACCESSED_BY_THIS_ASSESSMENT'
    assert a['integrity']['audit_inventory']['files_verified'] == 10
    assert a['integrity']['waveform_files_sha256_checked_by_upstream'] == 40


def test_no_bogus_acceptance_even_candidate_improves(ready):
    a = make_reports(ready)
    dev = a['previously_inspected_fold9']
    assert dev['baseline']['tp'] == 1  # fixture val rows y=(1,0,1,0) with 0.8,0.2,0.4,0.1
    assert dev['candidate']['tp'] >= dev['baseline']['tp']
    assert a['clinical_gate'] != 'PASS'
    assert all(x['demo_count_adequacy'] != 'CLINICALLY_VALIDATED' for x in a['subgroups'])


def test_missing_inventory_fails_closed(ready):
    root, protocol, inv, pkg, out = ready
    inv.unlink()
    with pytest.raises(ChangeError, match='inventory not found'):
        build(root, protocol, inv, pkg)


def test_inventory_hash_mismatch_fails_closed(ready):
    root, protocol, inv, pkg, out = ready
    # modify first hash without changing source
    with inv.open('r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    rows[0]['Hash'] = '0' * 64
    with inv.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Path', 'Hash'])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ChangeError, match='Inventory hash mismatch'):
        build(root, protocol, inv, pkg)


def test_inventory_duplicate_fails_closed(ready):
    root, protocol, inv, pkg, out = ready
    with inv.open('r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    rows[1] = dict(rows[0])
    with inv.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Path', 'Hash'])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ChangeError, match='Duplicate inventory entry'):
        verify_inventory(inv, root, protocol)


def test_upstream_report_modified_fails_even_if_rehashed(ready):
    root, protocol, inv, pkg, out = ready
    upstream_pkg = read_json(pkg)
    upstream_pkg['clinical_gate'] = 'PASS'
    upstream_pkg['artifact_sha256'] = doc_digest({k: v for k, v in upstream_pkg.items()
                                                   if k != 'artifact_sha256'})
    write(pkg, upstream_pkg)
    # v04 independently re-verifies even if attacker recomputes package self-hash.
    with pytest.raises(upstream.EvidenceError):
        build(root, protocol, inv, pkg)


def test_protocol_change_rejected(ready):
    root, protocol, inv, pkg, out = ready
    p = read_json(protocol)
    p['rules']['min_positive_patients'] = 99
    write(protocol, p)
    with pytest.raises(upstream.EvidenceError):
        build(root, protocol, inv, pkg)


def test_prediction_change_rejected(ready):
    root, protocol, inv, pkg, out = ready
    predictions = root / 'benchmark_v1/pilot_v1/model_v1/validation_predictions.csv'
    predictions.write_text(predictions.read_text(encoding='utf-8').replace('0.8', '0.81', 1), encoding='utf-8')
    with pytest.raises(upstream.EvidenceError):
        build(root, protocol, inv, pkg)


def test_v05_json_tamper_detected_even_after_hash_recalculation(ready):
    root, protocol, inv, pkg, out = ready
    make_reports(ready)
    report = read_json(out / FILE_JSON)
    report['evaluation_conclusion'] = 'MODEL_APPROVED'
    report['assessment_sha256'] = doc_digest({k: v for k, v in report.items()
                                              if k != 'assessment_sha256'})
    write(out / FILE_JSON, report)
    with pytest.raises(ChangeError, match='does not match recalculated'):
        verify_outputs(out, root, protocol, inv, pkg)


def test_v05_html_tamper_detected(ready):
    root, protocol, inv, pkg, out = ready
    make_reports(ready)
    f = out / FILE_HTML
    f.write_text(f.read_text(encoding='utf-8') + '<p>APPROVED</p>', encoding='utf-8')
    with pytest.raises(ChangeError, match='HTML report changed'):
        verify_outputs(out, root, protocol, inv, pkg)


def test_v05_markdown_tamper_detected(ready):
    root, protocol, inv, pkg, out = ready
    make_reports(ready)
    f = out / FILE_MD
    f.write_text('Clinical PASS\n', encoding='utf-8')
    with pytest.raises(ChangeError, match='Markdown report changed'):
        verify_outputs(out, root, protocol, inv, pkg)


def test_snapshot_change_detected_after_report_created(ready):
    root, protocol, inv, pkg, out = ready
    make_reports(ready)
    with inv.open('a', encoding='utf-8') as f:
        f.write('\n')
    with pytest.raises(ChangeError, match='does not match recalculated'):
        verify_outputs(out, root, protocol, inv, pkg)


def test_wrong_v04_package_path_rejected(ready):
    root, protocol, inv, pkg, out = ready
    with pytest.raises(ChangeError, match='known pilot evidence path'):
        build(root, protocol, inv, pkg.parent / 'another.json')


def test_html_escapes_untrusted_protocol_content(ready):
    root, protocol, inv, pkg, out = ready
    # v04 validates non-empty protocol claim strings but does not HTML escape them.
    p = read_json(protocol)
    p['clinical_claim_id'] = '<script>alert(1)</script>'
    write(protocol, p)
    write(pkg, upstream.build(root, protocol))
    make_inventory(inv, root, protocol)
    a = build(root, protocol, inv, pkg)
    page = render_html(a)
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in page
    assert '<script>alert(1)</script>' not in page


def test_patient_level_identifier_not_exposed_in_public_report(ready):
    a = make_reports(ready)
    outputs = [(ready[-1] / f).read_text(encoding='utf-8')
               for f in (FILE_JSON, FILE_HTML, FILE_MD)]
    for content in outputs:
        assert 'p17' not in content
        assert 'records100/00000/' not in content
        assert 'NOT_EVALUATED' in content


def test_sources_do_not_need_fold10(ready):
    root, protocol, inv, pkg, out = ready
    assert not (root / 'benchmark_v1/pilot_v1/test_fold_10.json').exists()
    a = build(root, protocol, inv, pkg)
    assert a['dataset']['fold10'] == 'NOT_ACCESSED_BY_THIS_ASSESSMENT'


def test_full_model_configuration_is_reported_when_present(ready):
    root, protocol, inv, pkg, out = ready
    pilot = root / 'benchmark_v1/pilot_v1'
    models_path = pilot / 'model_v1/models.json'
    models = read_json(models_path)
    for name, penalty in (('baseline', 1.0), ('candidate', 0.1)):
        models[name]['l2_penalty'] = penalty
        models[name]['weights'] = [0.0] * 72
    write(models_path, models)
    report_path = pilot / 'model_v1/pilot_model_report.json'
    report = read_json(report_path)
    report['models_sha256'] = digest(models_path)
    write(report_path, report)
    oof_path = pilot / 'oof_thresholds_v1/oof_threshold_development_report.json'
    oof = read_json(oof_path)
    oof['original_pilot_report_sha256'] = digest(report_path)
    write(oof_path, oof)
    write(pkg, upstream.build(root, protocol))
    make_inventory(inv, root, protocol)
    assessment = build(root, protocol, inv, pkg)
    assert assessment['models']['baseline']['l2_penalty'] == 1.0
    assert assessment['models']['candidate']['l2_penalty'] == 0.1
    assert assessment['models']['baseline']['feature_count'] == 72
    assert assessment['models']['candidate']['configuration_completeness'] == 'REPORTED'
