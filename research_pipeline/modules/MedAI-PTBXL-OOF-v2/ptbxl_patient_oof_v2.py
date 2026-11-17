#!/usr/bin/env python3
"""MedAI PTB-XL patient-weighted OOF threshold audit v2. Research only.

READ ONLY: PTB-XL metadata and an EXISTING OOF prediction CSV (does not train).
Fold 10: only ECG/patient/fold/path fields processed for structural integrity;
no fold 10 age/labels/waveforms/scores evaluated.
"""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

SNAPSHOT = {
    'ptbxl_database.csv': '7600de9c1b27d181d850b3c6038a35d7c3ddb6bb33b702e3a20252a6859d216b',
    'scp_statements.csv': 'ad05b0b1fcae83bb1230755ad9cfc7c96f303feddc08a4a9ad5bdc9ca63bac8f',
}
ID = re.compile(r'[1-9][0-9]*\Z', re.ASCII)
PATIENT = re.compile(r'([1-9][0-9]*)(?:\.0+)?\Z', re.ASCII)
PATH = re.compile(r'records100/\d{5}/\d{5}_lr\Z', re.ASCII)
FOLDS = frozenset(range(1, 9))
COLUMNS = ('ecg_id', 'strat_fold', 'y_true', 'baseline_probability', 'candidate_probability')


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def patient_id(value: str) -> str:
    match = PATIENT.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError('Invalid PTB-XL patient ID')
    return match.group(1)


def ecg_id(value: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('Invalid ECG ID')
    return value


def binary_label(value: str) -> int:
    if value not in ('0', '1'):
        raise ValueError('Invalid binary label')
    return int(value)


def score(value: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid probability') from exc
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError('Nonfinite/out-of-range probability')
    return number


def mi_codes(path: Path) -> frozenset[str]:
    found = set()
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not {'', 'diagnostic', 'diagnostic_class'}.issubset(reader.fieldnames or []):
            raise ValueError('Unexpected SCP schema')
        for row in reader:
            if row['diagnostic_class'].strip() == 'MI':
                if row['diagnostic'].strip() not in ('1', '1.0') or not row['']:
                    raise ValueError('Invalid MI-class SCP description')
                found.add(row[''])
    if len(found) != 14:
        raise ValueError('Unexpected PTB-XL MI-code count')
    return frozenset(found)


def mi_truth(value: str, codes: frozenset[str]) -> int:
    try:
        raw = ast.literal_eval(value)
    except (ValueError, SyntaxError) as exc:
        raise ValueError('Malformed scp_codes') from exc
    if not isinstance(raw, dict) or not raw:
        raise ValueError('Missing SCP codes')
    if any(not isinstance(k, str) or type(v) not in (int, float) or
           not math.isfinite(v) or not 0 <= v <= 100 for k, v in raw.items()):
        raise ValueError('Invalid SCP entry')
    # Explicit presence-only MI diagnostic superclass rule, NOT acute MI.
    return int(bool(set(raw) & codes))


def load_metadata(root: Path, *, expected_hashes: dict[str, str] = SNAPSHOT):
    for name, expected in expected_hashes.items():
        if sha(root / name) != expected:
            raise ValueError(f'Metadata snapshot mismatch: {name}')
    codes = mi_codes(root / 'scp_statements.csv')
    development = {}
    seen_ecgs, patient_folds, seen_paths = set(), {}, set()
    fold_counts = Counter()
    with (root / 'ptbxl_database.csv').open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        required = {'ecg_id', 'patient_id', 'strat_fold', 'filename_lr', 'scp_codes'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Incomplete PTB-XL metadata schema')
        for row in reader:
            eid = ecg_id(row['ecg_id'])
            pid = patient_id(row['patient_id'])
            if eid in seen_ecgs:
                raise ValueError('Duplicate ECG ID')
            seen_ecgs.add(eid)
            fvalue = row['strat_fold']
            if fvalue not in tuple(str(i) for i in range(1, 11)):
                raise ValueError('Unexpected fold')
            fold = int(fvalue)
            if pid in patient_folds and patient_folds[pid] != fold:
                raise ValueError('Patient leakage across folds')
            patient_folds[pid] = fold
            path = row['filename_lr']
            if not PATH.fullmatch(path) or path in seen_paths:
                raise ValueError('Unsafe/duplicate signal path')
            seen_paths.add(path)
            fold_counts[fold] += 1
            if fold in FOLDS:
                development[eid] = (pid, fold, mi_truth(row['scp_codes'], codes))
            # For fold 9/10: do not examine labels, age or signals.
    if len(seen_ecgs) != 21799 or len(patient_folds) != 18869 or set(fold_counts) != set(range(1, 11)):
        raise ValueError('Unexpected PTB-XL inventory/fold coverage')
    return development, fold_counts, codes


def load_oof(path: Path, development: dict[str, tuple[str, int, int]], *, pilot_subset=False):
    rows = []
    seen = set()
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError('Unexpected OOF columns')
        for raw in reader:
            if None in raw or any(raw.get(k) is None for k in COLUMNS):
                raise ValueError('Malformed OOF row')
            eid = ecg_id(raw['ecg_id'])
            if eid in seen or eid not in development:
                raise ValueError('Duplicate, non-development or unknown OOF ECG')
            seen.add(eid)
            pid, fold, truth = development[eid]
            if raw['strat_fold'] != str(fold) or binary_label(raw['y_true']) != truth:
                raise ValueError('OOF fold/MI label mismatch with locked metadata')
            rows.append({'ecg_id': eid, 'patient_id': pid, 'fold': fold, 'y_true': truth,
                         'baseline': score(raw['baseline_probability']),
                         'candidate': score(raw['candidate_probability'])})
    if not rows or {r['fold'] for r in rows} != FOLDS:
        raise ValueError('OOF requires at least one record from each development fold 1-8')
    if not pilot_subset and set(development) != seen:
        raise ValueError(f'Incomplete OOF: {len(seen)}/{len(development)} development ECGs')
    if {r['y_true'] for r in rows} != {0, 1}:
        raise ValueError('Both classes required')
    return rows


def patient_rates(rows: list[dict], model: str, threshold: float):
    """Within-class per-patient correctness, averaged equally across patients."""
    by_class = {0: defaultdict(list), 1: defaultdict(list)}
    for r in rows:
        predicted = int(r[model] >= threshold)
        by_class[r['y_true']][r['patient_id']].append(int(predicted == r['y_true']))
    result = {}
    for label, name in ((0, 'specificity'), (1, 'sensitivity')):
        groups = by_class[label]
        if not groups:
            raise ValueError('Patient-weighted metric requires both classes')
        result[name] = math.fsum(math.fsum(v)/len(v) for _, v in sorted(groups.items())) / len(groups)
        result['n_' + name + '_patients'] = len(groups)
    return result


def select_threshold(rows: list[dict], model: str, min_specificity: float = .90) -> dict:
    if model not in ('baseline', 'candidate'):
        raise ValueError('Unknown model')
    if type(min_specificity) not in (float, int) or not math.isfinite(min_specificity) or not 0 < min_specificity <= 1:
        raise ValueError('Invalid target specificity')
    options = sorted({0.0, .5, 1.0, math.nextafter(1.0, 2.0), *(r[model] for r in rows)})
    best = None
    # deterministic: maximize patient sensitivity, then specificity, then threshold
    for threshold in options:
        rates = patient_rates(rows, model, threshold)
        if rates['specificity'] + 1e-12 < min_specificity:
            continue
        key = (rates['sensitivity'], rates['specificity'], threshold)
        if best is None or key > best[0]:
            best = (key, {'threshold': threshold, **rates})
    if best is None:
        raise ValueError('No feasible patient-weighted threshold')
    return best[1]


def build_report(root: Path, oof_file: Path, *, pilot_subset: bool = False):
    development, fold_counts, codes = load_metadata(root)
    rows = load_oof(oof_file, development, pilot_subset=pilot_subset)
    results = {name: select_threshold(rows, name) for name in ('baseline', 'candidate')}
    return {
        'schema_version': 'medai-ptbxl-patient-weighted-oof-v2',
        'status': 'RESEARCH_DEVELOPMENT_ONLY_NOT_INDEPENDENT_VALIDATION',
        'mode': 'LEGACY_CONVENIENCE_PILOT_SUBSET' if pilot_subset else 'FULL_FOLDS_1_8_OOF_SCORES',
        'source_authentication': 'NOT_ESTABLISHED',
        'oof_origin_reproduction': 'NOT_VERIFIED',
        'clinical_gate': 'NOT_EVALUATED',
        'fold9_used_for_selection': False,
        'fold10_used_for_selection': False,
        'fold10_labels_or_waveforms_read': False,
        'metadata_full_inventory_ecgs': sum(fold_counts.values()),
        'oof_records': len(rows),
        'oof_patients': len({r['patient_id'] for r in rows}),
        'oof_fold_counts': dict(sorted(Counter(r['fold'] for r in rows).items())),
        'label_policy': 'MI superclass; any of 14 MI diagnostic SCP codes present, independent of confidence',
        'mi_codes': sorted(codes),
        'threshold_policy': 'maximize PATIENT-weighted sensitivity subject to PATIENT-weighted specificity >= 0.90; ties: specificity then threshold',
        'target_specificity_research_only': .90,
        'models': results,
        'files_sha256': {name: sha(root / name) for name in SNAPSHOT} | {'oof_csv': sha(oof_file)},
        'limitations': [
            'OOF probabilities are supplied, not independently reproduced from waveforms/models.',
            'Pilot-subset mode is convenience-sampled, not representative.',
            'Model selection and the operating target are exploratory; not a clinical acceptance criterion.',
            'No fold-9 or fold-10 performance estimated.',
            'File integrity hashes do not authenticate origin.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--oof-csv', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pilot-subset', action='store_true', help='Explicitly permit incomplete legacy OOF subset')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite existing report')
    try:
        report = build_report(args.data_dir, args.oof_csv, pilot_subset=args.pilot_subset)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8', newline='\n') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.write('\n')
    except (ValueError, OSError) as exc:
        parser.exit(2, f'FAIL_CLOSED: {exc}\n')
    print('STATUS:', report['status'])
    print('MODE:', report['mode'])
    print('OOF RECORDS:', report['oof_records'])
    print('OOF PATIENTS:', report['oof_patients'])
    for name, detail in report['models'].items():
        print(f'{name.upper()} patient-weighted: threshold={detail["threshold"]:.12g}; sensitivity={detail["sensitivity"]:.6f}; specificity={detail["specificity"]:.6f}')
    print('FOLD 10: LABELS/SIGNALS NOT EXAMINED')
    print('REPORT:', args.output)

if __name__ == '__main__':
    main()
