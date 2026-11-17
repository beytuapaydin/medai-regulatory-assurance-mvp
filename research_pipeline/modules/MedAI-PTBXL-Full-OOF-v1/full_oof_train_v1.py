#!/usr/bin/env python3
"""Research-only full PTB-XL folds 1-8 OOF, no fold 9/10 outcome access.

Requires unchanged original training module and patient-weighted OOF v2 module.
No clinical gate, regulatory release, or independent validation asserted.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
from collections import Counter, defaultdict

TRAIN_SOURCE_SHA256 = '9c0f6eeae4a77ff77b361055c1d18cd21143dbf97828efc56f7ba8cbb0cf4c0c'
OOF_V2_SOURCE_SHA256 = 'a2190af2a41b1bba01fcf3d37f9c19e47dcfb618de74e5154d6ace3e444fd06e'
METADATA_SHA256 = '7600de9c1b27d181d850b3c6038a35d7c3ddb6bb33b702e3a20252a6859d216b'
SCP_SHA256 = 'ad05b0b1fcae83bb1230755ad9cfc7c96f303feddc08a4a9ad5bdc9ca63bac8f'
SUMS_SHA256 = 'b7224b92b341511ec3ceb13dc6652079b2c36a06504bcb49506f157f51dc695d'
FULL_COUNT = 17418
FOLDS = set(range(1, 9))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_locked_modules(source: Path, oof_v2_source: Path):
    original = source / 'ptbxl_pilot_train.py'
    v2 = oof_v2_source / 'ptbxl_patient_oof_v2.py'
    if sha(original) != TRAIN_SOURCE_SHA256:
        raise ValueError('Original training code SHA-256 mismatch: refuse model execution')
    if sha(v2) != OOF_V2_SOURCE_SHA256:
        raise ValueError('Patient-weighted OOF v2 source SHA-256 mismatch')
    import importlib.util
    def load(name, file):
        spec = importlib.util.spec_from_file_location(name, file)
        if spec is None or spec.loader is None:
            raise ValueError('Cannot load validated module')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    train = load('_medai_full_oof_train_locked', original)
    v2mod = load('_medai_full_oof_v2_locked', v2)
    if train.MODEL_CONFIGS != (('baseline', 1.0), ('candidate', 0.1)) or train.MODEL_EPOCHS != 200 or train.MODEL_LEARNING_RATE != 0.25:
        raise ValueError('Unexpected training parameters')
    return train, v2mod


def development_rows(root: Path, v2):
    # v2 verifies metadata digests and every patient-fold assignment globally.
    # It only reads labels for folds 1-8; fold 9/10: identifiers/fold/path only.
    dev, fold_counts, codes = v2.load_metadata(root)
    if len(dev) != FULL_COUNT or len(codes) != 14:
        raise ValueError(f'Unexpected development inventory: {len(dev)}')
    if sum(fold_counts[f] for f in FOLDS) != FULL_COUNT:
        raise ValueError('Unexpected development fold counts')
    # Re-open metadata, but access only structural fields for all records.
    # For fold 1-8, pull filename_lr and compare to validated v2 inventory.
    rows = []
    with (root / 'ptbxl_database.csv').open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for raw in reader:
            fold = int(raw['strat_fold'])
            if fold not in FOLDS:
                continue  # fold 9/10 labels/ages/waveforms NEVER read
            eid = v2.ecg_id(raw['ecg_id'])
            pid = v2.patient_id(raw['patient_id'])
            if eid not in dev:
                raise ValueError(f'Missing development ECG: {eid}')
            known_pid, known_fold, known_label = dev[eid]
            if (pid, fold) != (known_pid, known_fold):
                raise ValueError('Metadata comparison mismatch')
            rel = raw['filename_lr']
            if not v2.PATH.fullmatch(rel):
                raise ValueError('Unsafe ECG signal path')
            rows.append({'ecg_id': eid, 'patient_id': pid, 'fold': fold,
                         'y_true': known_label, 'filename_lr': rel})
    if len(rows) != FULL_COUNT or len({r['ecg_id'] for r in rows}) != FULL_COUNT:
        raise ValueError('Missing or duplicated development rows')
    by_pid = {}
    for r in rows:
        if r['patient_id'] in by_pid and by_pid[r['patient_id']] != r['fold']:
            raise ValueError('Patient across development folds')
        by_pid[r['patient_id']] = r['fold']
    return rows


def produce_oof(rows, X, train, *, progress=print):
    if len(rows) != len(X):
        raise ValueError('Incorrect feature inventory')
    if not rows or any(r['fold'] not in FOLDS or r['y_true'] not in (0, 1) for r in rows):
        raise ValueError('Not an exclusively fold 1-8 labeled dataset')
    if {r['fold'] for r in rows} != FOLDS:
        raise ValueError('All eight folds are mandatory')
    patient_fold = {}
    for r in rows:
        pid, fold = r['patient_id'], r['fold']
        if pid in patient_fold and patient_fold[pid] != fold:
            raise ValueError('Patient leakage across OOF folds')
        patient_fold[pid] = fold
    scores = {name: [None] * len(rows) for name, _ in train.MODEL_CONFIGS}
    audits = {}
    for name, l2 in train.MODEL_CONFIGS:
        for holdout in sorted(FOLDS):
            tr = [i for i, row in enumerate(rows) if row['fold'] != holdout]
            va = [i for i, row in enumerate(rows) if row['fold'] == holdout]
            if not tr or not va or {rows[i]['patient_id'] for i in tr} & {rows[i]['patient_id'] for i in va}:
                raise ValueError('Fold overlap or empty split')
            model = train.train_logistic([X[i] for i in tr], [rows[i]['y_true'] for i in tr], l2)
            for i in va:
                if scores[name][i] is not None:
                    raise ValueError('OOF score assigned twice')
                value = train.predict(model, X[i])
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError('Invalid model score')
                scores[name][i] = value
            audits[f'{name}_fold{holdout}'] = {
                'train_records': len(tr), 'holdout_records': len(va),
                'train_patients': len({rows[i]['patient_id'] for i in tr}),
                'holdout_patients': len({rows[i]['patient_id'] for i in va}),
                'patient_overlap': 0,
            }
            progress(f'OOF MODEL={name.upper()} HOLDOUT={holdout}/8 COMPLETED')
        if any(value is None for value in scores[name]):
            raise ValueError('Incomplete OOF predictions')
    return scores, audits


def fast_threshold(rows, scores, minimum_specificity=0.90):
    """O(n log n) patient-weighted sweep, with ALL same-score ties grouped.

    At threshold greater than 1, every record is predicted negative. Descend
    through unique prediction scores, flipping the corresponding records to
    predicted positive. Every patient receives equal within-class weight.
    """
    if len(rows) != len(scores) or not rows or not 0 < minimum_specificity <= 1:
        raise ValueError('Invalid threshold inputs')
    by_class = {0: defaultdict(int), 1: defaultdict(int)}
    for r, score in zip(rows, scores):
        if r['y_true'] not in (0, 1) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Invalid label/score')
        by_class[r['y_true']][r['patient_id']] += 1
    if not by_class[0] or not by_class[1]:
        raise ValueError('Missing class')
    npos, nneg = len(by_class[1]), len(by_class[0])
    grouped = defaultdict(lambda: [0.0, 0.0])
    for r, score in zip(rows, scores):
        weight = 1.0 / (len(by_class[r['y_true']]) * by_class[r['y_true']][r['patient_id']])
        grouped[score][r['y_true']] += weight
    sens, spec = 0.0, 1.0
    best_key, best = None, None
    options = sorted(set(grouped) | {0.0, .5, 1.0, math.nextafter(1.0, 2.0)}, reverse=True)
    for t in options:
        changes = grouped.get(t)
        if changes is not None:
            spec -= changes[0]
            sens += changes[1]
        sens, spec = max(0.0, min(1.0, sens)), max(0.0, min(1.0, spec))
        if spec + 1e-12 < minimum_specificity:
            continue
        key = (round(sens, 12), round(spec, 12), t)
        if best_key is None or key > best_key:
            best_key, best = key, {'threshold': t, 'sensitivity': sens, 'specificity': spec,
                                  'n_sensitivity_patients': npos, 'n_specificity_patients': nneg}
    if best is None:
        raise ValueError('No feasible threshold')
    return best


def write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def execute(root: Path, pilot_source: Path, oof_v2_source: Path, output_dir: Path):
    root, pilot_source, oof_v2_source, output_dir = [Path(x).resolve() for x in (root, pilot_source, oof_v2_source, output_dir)]
    if output_dir.exists():
        raise FileExistsError('Output directory already exists: refusing overwrite')
    if (root / 'benchmark_v1') in output_dir.parents or root == output_dir or root in output_dir.parents:
        raise ValueError('Output cannot reside inside PTB-XL dataset directory')
    train, v2 = load_locked_modules(pilot_source, oof_v2_source)
    for name, expected in [('ptbxl_database.csv', METADATA_SHA256),
                           ('scp_statements.csv', SCP_SHA256), ('SHA256SUMS.txt', SUMS_SHA256)]:
        if sha(root / name) != expected:
            raise ValueError(f'Input snapshot SHA-256 mismatch: {name}')
    print('METADATA/SOURCE SHA256: VERIFIED', flush=True)
    rows = development_rows(root, v2)
    print(f'DEVELOPMENT: {len(rows)} ECG / {len(set(r["patient_id"] for r in rows))} patients / folds 1-8', flush=True)
    hashes = train.official_hashes(root / 'SHA256SUMS.txt')
    X = []
    for i, r in enumerate(rows, 1):
        train.verify_record_files(root, r['filename_lr'], hashes)
        feats = train.read_features(root, r['filename_lr'])
        if len(feats) != 72 or any(not math.isfinite(v) for v in feats):
            raise ValueError('Non-finite/missing features')
        X.append(feats)
        if i % 1000 == 0 or i == len(rows):
            print(f'FEATURES VERIFIED: {i}/{len(rows)}', flush=True)
    scores, audit = produce_oof(rows, X, train)
    thresholds = {name: fast_threshold(rows, scores[name]) for name in ('baseline', 'candidate')}
    for name in thresholds:
        print(f'{name.upper()}: patient threshold {thresholds[name]["threshold"]:.12g}, '
              f'sensitivity {thresholds[name]["sensitivity"]:.6f}, '
              f'specificity {thresholds[name]["specificity"]:.6f}', flush=True)
    # Compare derived values to existing slow v2 metrics ONLY at selected thresholds.
    # Do NOT run v2's O(n^2) full threshold search at 17k records.
    for name in thresholds:
        for r, prob in zip(rows, scores[name]):
            r[name] = prob
        rates = v2.patient_rates(rows, name, thresholds[name]['threshold'])
        for key in ('sensitivity', 'specificity'):
            if abs(rates[key] - thresholds[name][key]) > 1e-9:
                raise ValueError(f'Threshold method disagreement for {name}/{key}')
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    # Output files are first assembled in an isolated temporary folder, then
    # committed by rename. Dataset and original pilot outputs are untouched.
    temp = Path(tempfile.mkdtemp(prefix='.medai_full_oof_staging_', dir=output_dir.parent))
    try:
        pred_path = temp / 'training_oof_predictions.csv'
        with pred_path.open('w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, lineterminator='\n')
            writer.writerow(('ecg_id', 'strat_fold', 'y_true', 'baseline_probability', 'candidate_probability'))
            for i, r in enumerate(rows):
                writer.writerow((r['ecg_id'], r['fold'], r['y_true'],
                                 format(scores['baseline'][i], '.17g'),
                                 format(scores['candidate'][i], '.17g')))
        report = {
            'schema_version': 'medai-full-ptbxl-oof-research-v1',
            'status': 'FULL_DEVELOPMENT_OOF_NOT_INDEPENDENT_VALIDATION',
            'clinical_gate': 'NOT_EVALUATED',
            'manufacturer_release_decision': 'OUTSIDE_PLATFORM_SCOPE',
            'label_policy': 'PTB-XL diagnostic superclass MI: any of 14 MI diagnostic SCP codes present; no confidence cutoff',
            'folds_used_for_training': list(sorted(FOLDS)),
            'fold9_labels_or_waveforms_examined': False,
            'fold10_labels_or_waveforms_examined': False,
            'metadata_fold9_10_structural_fields_checked': True,
            'records': len(rows), 'patients': len({r['patient_id'] for r in rows}),
            'positive_records': sum(r['y_true'] for r in rows),
            'negative_records': sum(1 - r['y_true'] for r in rows),
            'patient_weighted_threshold_policy': 'Maximize patient-weighted sensitivity subject to patient-weighted specificity >= 0.90; tie-break specificity, then higher threshold',
            'models': thresholds,
            'source_sha256': {'training_module': TRAIN_SOURCE_SHA256, 'patient_oof_v2_module': OOF_V2_SOURCE_SHA256,
                              'ptbxl_database': METADATA_SHA256, 'scp_statements': SCP_SHA256,
                              'official_sha256sums': SUMS_SHA256, 'this_runner': sha(Path(__file__).resolve())},
            'training': {'model_configs': [list(x) for x in train.MODEL_CONFIGS],
                         'epochs': train.MODEL_EPOCHS, 'learning_rate': train.MODEL_LEARNING_RATE,
                         'features_per_ecg': 72, 'scaler': 'fit within each training fold only'},
            'fold_audit': audit,
            'oof_predictions_sha256': sha(pred_path),
            'limitations': [
                'Training OOF is development-only; thresholds optimized on same OOF labels.',
                'No independent fold-9 or fold-10 evaluation carried out.',
                'Hash digests establish local file consistency, not source authenticity.',
                'Models re-trained per heldout fold; deployable full-train model NOT produced.',
                'No significance, generalizability, clinical approval or release claims.'
            ],
        }
        report_file = temp / 'full_oof_report.json'
        write_json(report_file, report)
        manifest = {'schema_version': 'medai-oof-v1-manifest',
                    'files_sha256': {'training_oof_predictions.csv': sha(pred_path),
                                     'full_oof_report.json': sha(report_file)},
                    'status': 'LOCAL_FILE_INTEGRITY_ONLY'}
        write_json(temp / 'manifest.json', manifest)
        if output_dir.exists():
            raise FileExistsError('Output unexpectedly appeared')
        temp.rename(output_dir)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    print('STATUS: FULL_DEVELOPMENT_OOF_NOT_INDEPENDENT_VALIDATION', flush=True)
    print('FOLD 9/10: LABELS/SIGNALS NOT EXAMINED', flush=True)
    print('OUTPUT:', output_dir, flush=True)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-dir', type=Path, required=True)
    ap.add_argument('--pilot-source', type=Path, required=True)
    ap.add_argument('--oof-v2-source', type=Path, required=True)
    ap.add_argument('--output-dir', type=Path, required=True)
    args = ap.parse_args()
    try:
        execute(args.data_dir, args.pilot_source, args.oof_v2_source, args.output_dir)
    except (ValueError, OSError, RuntimeError) as exc:
        ap.exit(2, f'FAIL_CLOSED: {exc}\n')


if __name__ == '__main__':
    main()
