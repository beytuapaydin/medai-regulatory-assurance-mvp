"""Regression tests for research-only adapter; synthetic fixture, no real PTB-XL records."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import pytest

from medai_real_evidence_v04 import (
    EvidenceError, build, doc_sha, file_sha, json_file, metrics,
    oof_threshold, verify,
)


def write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def csvfile(path: Path, names: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def environment(tmp_path):
    root = tmp_path / 'dataset'
    pilot = root / 'benchmark_v1' / 'pilot_v1'
    model_dir = pilot / 'model_v1'
    oof_dir = pilot / 'oof_thresholds_v1'
    model_dir.mkdir(parents=True)
    oof_dir.mkdir(parents=True)
    train, val, checksums = [], [], []
    for eid in range(1, 21):
        fold = (eid + 1) // 2 if eid < 17 else 9
        # 2 records per dev fold; train has 8 MI + 8 non-MI.
        y = eid % 2
        age = '80' if eid % 3 == 0 else '54'
        rel = f'records100/{(eid // 1000):05d}/{eid:05d}_lr'
        base = root / rel
        base.parent.mkdir(parents=True, exist_ok=True)
        (base.with_suffix('.dat')).write_bytes(bytes([eid]) * 24000)
        (base.with_suffix('.hea')).write_text('synthetic fixture, not a WFDB test\n', encoding='utf-8')
        for suffix in ('.hea', '.dat'):
            path = base.with_suffix(suffix)
            checksums.append(f'{file_sha(path)}  {rel}{suffix}\n')
        row = {'ecg_id': str(eid), 'patient_id': f'p{eid}', 'strat_fold': fold,
               'y_true': y, 'age': age, 'filename_lr': rel}
        (train if eid <= 16 else val).append(row)
    (root / 'SHA256SUMS.txt').write_text(''.join(checksums), encoding='utf-8')
    write(pilot / 'pilot_train.json', train)
    write(pilot / 'pilot_validation.json', val)
    write(pilot / 'pilot_manifest.json', {
        'status': 'EXPLORATORY_PILOT', 'selection': 'Records available after interrupted download',
        'patient_overlap': 0, 'train': {'ecg': len(train)}, 'validation': {'ecg': len(val)},
    })
    write(model_dir / 'models.json', {
        name: {'type': 'l2_logistic_regression', 'decision_threshold': .5}
        for name in ('baseline', 'candidate')
    })
    val_probs = {
        'baseline': [0.8, 0.2, 0.4, 0.1],
        'candidate': [0.9, 0.3, 0.5, 0.2],
    }
    oof_probs = {
        'baseline': [0.6 if r['y_true'] else 0.25 for r in train],
        'candidate': [0.55 if r['y_true'] else 0.28 for r in train],
    }
    val_columns = ('ecg_id', 'patient_id', 'strat_fold', 'age', 'y_true',
                   'baseline_probability', 'baseline_pred', 'candidate_probability', 'candidate_pred')
    csvfile(model_dir / 'validation_predictions.csv', val_columns,
            [dict(ecg_id=r['ecg_id'], patient_id=r['patient_id'], strat_fold=9,
                  age=r['age'], y_true=r['y_true'],
                  baseline_probability=val_probs['baseline'][i],
                  baseline_pred=int(val_probs['baseline'][i] >= .5),
                  candidate_probability=val_probs['candidate'][i],
                  candidate_pred=int(val_probs['candidate'][i] >= .5))
             for i, r in enumerate(val)])
    oof_columns = ('ecg_id', 'strat_fold', 'y_true', 'baseline_probability', 'candidate_probability')
    csvfile(oof_dir / 'training_oof_predictions.csv', oof_columns,
            [dict(ecg_id=r['ecg_id'], strat_fold=r['strat_fold'], y_true=r['y_true'],
                  baseline_probability=oof_probs['baseline'][i],
                  candidate_probability=oof_probs['candidate'][i])
             for i, r in enumerate(train)])
    mreport = {
        'status': 'EXPLORATORY_VALIDATION_ONLY_NOT_A_CLINICAL_GATE',
        'fold_10_used': False, 'medai_gate_status': 'NOT_EVALUATED',
        'clinical_validity': 'NOT_ESTABLISHED', 'patient_overlap': 0,
        'raw_waveform_files_sha256_checked': 40, 'real_waveforms_used': True,
        'train_records': 16, 'validation_records': 4,
        'train_mi_positive': sum(r['y_true'] for r in train),
        'validation_mi_positive': sum(r['y_true'] for r in val),
        'validation_age75_plus_mi_positive': sum(r['y_true'] for r in val if float(r['age']) >= 75),
        'validation_metrics': {
            k: metrics([r['y_true'] for r in val], v, .5)
            for k, v in val_probs.items()
        },
    }
    for key, rel in (
        ('manifest_sha256', pilot / 'pilot_manifest.json'),
        ('train_list_sha256', pilot / 'pilot_train.json'),
        ('validation_list_sha256', pilot / 'pilot_validation.json'),
        ('models_sha256', model_dir / 'models.json'),
        ('validation_predictions_sha256', model_dir / 'validation_predictions.csv'),
        ('official_sums_file_sha256', root / 'SHA256SUMS.txt'),
    ):
        mreport[key] = file_sha(rel)
    write(model_dir / 'pilot_model_report.json', mreport)
    oof_models = {}
    for k in ('baseline', 'candidate'):
        selected = oof_threshold([r['y_true'] for r in train], oof_probs[k])
        dev = metrics([r['y_true'] for r in val], val_probs[k], selected['threshold'])
        oof_models[k] = {
            'threshold_from_training_oof_only': selected['threshold'],
            'train_oof_selection_metrics_development_only': selected,
            'fold9_previously_inspected_development_diagnostic': dev,
            'oof_fold_audit': [{'heldout_fold': i} for i in range(1, 9)],
        }
    write(oof_dir / 'oof_threshold_development_report.json', {
        'status': 'OOF_TRAIN_ONLY_THRESHOLD_DEVELOPMENT_NOT_CLINICAL_VALIDATION',
        'fold10_used': False, 'fold9_was_previously_inspected': True,
        'medai_clinical_gate': 'NOT_EVALUATED', 'clinical_validity': 'NOT_ESTABLISHED',
        'thresholds_not_clinically_qualified': True,
        'specificity_development_target': 0.90,
        'train_count': len(train), 'validation_count': len(val),
        'original_pilot_report_sha256': file_sha(model_dir / 'pilot_model_report.json'),
        'original_validation_predictions_sha256': file_sha(model_dir / 'validation_predictions.csv'),
        'training_manifest_sha256': file_sha(pilot / 'pilot_train.json'),
        'training_oof_predictions_sha256': file_sha(oof_dir / 'training_oof_predictions.csv'),
        'models': oof_models,
    })
    protocol = root.parent / 'trusted_protocol.json'
    write(protocol, {
        'schema_version': 'medai-protocol-v0.2', 'demonstration_only': True,
        'protocol_id': 'DEMO', 'protocol_version': '1',
        'clinical_claim_id': 'CLM', 'risk_control_id': 'RC',
        'dataset': {'required_test_fold': 10, 'reference_name': 'PTB-XL',
                    'reference_version': '1.0.3'},
        'required_subgroups': ['ALL', 'AGE75_PLUS'],
        'rules': {'min_positive_records': 3, 'min_negative_records': 3,
                  'min_positive_patients': 3, 'min_negative_patients': 3},
    })
    return root, protocol


def test_end_to_end_research_only(environment):
    root, protocol = environment
    package = build(root, protocol)
    verify(package, root, protocol)
    assert package['schema_version'] == 'medai-ptbxl-research-evidence-v0.4'
    assert package['clinical_gate'] == 'NOT_EVALUATED'
    assert package['release_decision'] == 'OUTSIDE_PLATFORM_SCOPE'
    assert package['evidence_adequacy'] == 'INSUFFICIENT_EVIDENCE'
    assert package['source_integrity']['waveform_files_checked'] == 40
    assert package['subgroups'][1]['cohort_id'] == 'AGE75_PLUS'
    assert package['subgroups'][1]['sample_adequacy_for_demonstration_rules'] == 'INSUFFICIENT_EVIDENCE'
    assert all('fold9_development_only' in package['models'][n] for n in ('baseline', 'candidate'))


def test_tampered_package_rejected(environment):
    root, protocol = environment
    package = build(root, protocol)
    package['clinical_gate'] = 'PASS'
    with pytest.raises(EvidenceError, match='hash'):
        verify(package, root, protocol)
    package['artifact_sha256'] = doc_sha({k: v for k, v in package.items() if k != 'artifact_sha256'})
    with pytest.raises(EvidenceError, match='no longer matches'):
        verify(package, root, protocol)


def test_modified_protocol_rejected(environment):
    root, protocol = environment
    package = build(root, protocol)
    payload = json_file(protocol)
    payload['rules']['min_positive_patients'] = 1
    write(protocol, payload)
    with pytest.raises(EvidenceError, match='no longer matches'):
        verify(package, root, protocol)


def test_missing_trusted_protocol_fails_closed(environment):
    root, protocol = environment
    with pytest.raises(EvidenceError, match='Trusted protocol unavailable'):
        build(root, protocol.with_name('does_not_exist.json'))


def test_waveform_tamper_rejected(environment):
    root, protocol = environment
    package = build(root, protocol)
    item = root / 'records100/00000/00001_lr.dat'
    item.write_bytes(bytes([42]) * 24000)
    with pytest.raises(EvidenceError, match='Waveform SHA-256 mismatch'):
        verify(package, root, protocol)


def test_threshold_tamper_rejected_even_if_oof_report_rehashed(environment):
    root, protocol = environment
    path = root / 'benchmark_v1/pilot_v1/oof_thresholds_v1/oof_threshold_development_report.json'
    report = json_file(path)
    report['models']['baseline']['threshold_from_training_oof_only'] = 0.99
    write(path, report)
    with pytest.raises(EvidenceError, match='OOF threshold changed'):
        build(root, protocol)


def test_csv_identity_tamper_rejected(environment):
    root, protocol = environment
    path = root / 'benchmark_v1/pilot_v1/model_v1/validation_predictions.csv'
    raw = path.read_text(encoding='utf-8')
    path.write_text(raw.replace('p17', 'p999', 1), encoding='utf-8')
    with pytest.raises(EvidenceError, match='SHA mismatch'):
        build(root, protocol)


def test_fold10_or_clinical_pass_in_source_rejected(environment):
    root, protocol = environment
    path = root / 'benchmark_v1/pilot_v1/model_v1/pilot_model_report.json'
    report = json_file(path)
    report['fold_10_used'] = True
    write(path, report)
    with pytest.raises(EvidenceError, match='not research-only'):
        build(root, protocol)


def test_patient_leakage_rejected(environment):
    root, protocol = environment
    path = root / 'benchmark_v1/pilot_v1/pilot_validation.json'
    val = json_file(path)
    val[0]['patient_id'] = 'p1'
    write(path, val)
    with pytest.raises(EvidenceError, match='PATIENT LEAKAGE'):
        build(root, protocol)


def test_no_fold10_data_required(environment):
    root, protocol = environment
    assert not (root / 'benchmark_v1/pilot_v1/test_fold_10.json').exists()
    package = build(root, protocol)
    assert package['dataset']['test_fold_10'] == 'NOT_ACCESSED_BY_THIS_ADAPTER'
