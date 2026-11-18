"""Development-only OOF verifier. No waveforms, no holdout, no clinical claims.

Independent implementation; NOT the historical unbundled generator.
"""
import argparse
import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path

LOCKS = {
    'oof': 'ED83A106581E43275803D2E343F513D5BFC2B80A50E33584651816AE88A71E38',
    'metadata': '7600DE9C1B27D181D850B3C6038A35D7C3DDB6BB33B702E3A20252A6859D216B',
    'audit': '52C9197D1E827E0367A15871AA6F4500456B8126D34144CEB12A29BA7F081141',
}
THRESHOLDS = (0.3090648316207752, 0.3795860831201651)
EXPECTED = {'ecgs': 17418, 'patients': 15023, 'mixed': 315}

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest().upper()

def canonical_id(raw):
    s = str(raw).strip()
    if not s or s.startswith('-') or not s.replace('.', '', 1).isdigit():
        raise ValueError('Invalid identifier')
    if '.' in s:
        a, b = s.split('.', 1)
        if not b or set(b) != {'0'}:
            raise ValueError('Nonintegral identifier')
        s = a
    n = int(s)
    if n <= 0:
        raise ValueError('Invalid identifier')
    return str(n)

def percentile(values, q):
    if not values or not 0 <= q <= 1:
        raise ValueError('Invalid percentile')
    s = sorted(values)
    pos = (len(s) - 1) * q
    i = int(pos)
    return s[i] + (s[min(i+1, len(s)-1)] - s[i]) * (pos-i)

def load_development(metadata, oof):
    """Metadata folds 9/10 excluded before patient identity join."""
    mapping, patient_folds = {}, {}
    with Path(metadata).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not {'ecg_id', 'patient_id', 'strat_fold'} <= set(reader.fieldnames or []):
            raise ValueError('Metadata schema')
        for row in reader:
            fold = int(row['strat_fold'])
            if fold not in range(1, 9):
                continue
            eid, pid = canonical_id(row['ecg_id']), canonical_id(row['patient_id'])
            if eid in mapping or (pid in patient_folds and patient_folds[pid] != fold):
                raise ValueError('Duplicate ECG or cross-fold patient')
            mapping[eid] = (pid, fold)
            patient_folds[pid] = fold
    counts = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    seen = set()
    with Path(oof).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        required = ['ecg_id', 'strat_fold', 'y_true', 'baseline_probability', 'candidate_probability']
        if reader.fieldnames != required:
            raise ValueError('OOF schema')
        for row in reader:
            eid = canonical_id(row['ecg_id'])
            if eid in seen or eid not in mapping:
                raise ValueError('Duplicate/unknown OOF ECG')
            seen.add(eid)
            pid, fold = mapping[eid]
            if int(row['strat_fold']) != fold or row['y_true'] not in ('0', '1'):
                raise ValueError('Fold or label mismatch')
            probs = (float(row['baseline_probability']), float(row['candidate_probability']))
            if not all(math.isfinite(v) and 0 <= v <= 1 for v in probs):
                raise ValueError('Invalid probability')
            b, c = (int(v >= t) for v, t in zip(probs, THRESHOLDS))
            s = counts[pid]
            if row['y_true'] == '1':
                s[0] += 1
                s[1] += b
                s[2] += c
            else:
                s[3] += 1
                s[4] += 1-b
                s[5] += 1-c
    if seen != set(mapping):
        raise ValueError('Missing OOF predictions')
    return [counts[p] for p in sorted(counts, key=int)], len(seen)

def compute(ordered, *, replicates=2000, seed=20261117):
    if not ordered or type(replicates) is not int or replicates < 1:
        raise ValueError('Invalid patient population / replicates')
    pos = [x for x in ordered if x[0]]
    neg = [x for x in ordered if x[3]]
    if not pos or not neg:
        raise ValueError('Missing endpoint class')
    metrics = {
        'n_positive_patients': len(pos),
        'n_negative_patients': len(neg),
        'baseline_sensitivity': math.fsum(x[1]/x[0] for x in pos)/len(pos),
        'candidate_sensitivity': math.fsum(x[2]/x[0] for x in pos)/len(pos),
        'baseline_specificity': math.fsum(x[4]/x[3] for x in neg)/len(neg),
        'candidate_specificity': math.fsum(x[5]/x[3] for x in neg)/len(neg),
    }
    rng = random.Random(seed)
    d_sens, d_spec = [], []
    n = len(ordered)
    for _ in range(replicates):
        a = b = 0.0
        npos = nneg = 0
        for _ in range(n):
            x = ordered[rng.randrange(n)]
            if x[0]:
                a += (x[2]-x[1])/x[0]
                npos += 1
            if x[3]:
                b += (x[5]-x[4])/x[3]
                nneg += 1
        if not npos or not nneg:
            raise ValueError('Degenerate whole-patient bootstrap draw')
        d_sens.append(a/npos)
        d_spec.append(b/nneg)
    return metrics, {
        'sensitivity': [percentile(d_sens, .025), percentile(d_sens, .975)],
        'specificity': [percentile(d_spec, .025), percentile(d_spec, .975)],
    }

def verify(oof, metadata, audit, output=None):
    paths = {'oof': Path(oof), 'metadata': Path(metadata), 'audit': Path(audit)}
    actual = {name: sha256(path) for name, path in paths.items()}
    for name, expected in LOCKS.items():
        if actual[name] != expected:
            raise ValueError(f'Locked {name} SHA256 mismatch')
    historical = json.loads(paths['audit'].read_text(encoding='utf-8-sig'))
    ordered, n_ecgs = load_development(metadata, oof)
    mixed = sum(x[0] > 0 and x[3] > 0 for x in ordered)
    if (n_ecgs, len(ordered), mixed) != (EXPECTED['ecgs'], EXPECTED['patients'], EXPECTED['mixed']):
        raise ValueError('Locked development cohort mismatch')
    if historical.get('thresholds') != dict(zip(('baseline', 'candidate'), THRESHOLDS)):
        raise ValueError('Historical thresholds mismatch')
    metrics, intervals = compute(ordered)
    for k, observed in metrics.items():
        ref = historical['recomputed_metrics'][k]
        if abs(observed - ref) > (0 if k.startswith('n_') else 1e-10):
            raise ValueError(f'Historical metric mismatch: {k}')
    report = {
        'status': 'PASS_FIXED_THRESHOLD_METRICS_CI_NOT_IDENTICAL',
        'scope': 'DEVELOPMENT_FOLDS_1_8_ONLY_FOLD10_NO_GO',
        'source_sha256': actual,
        'ecgs': n_ecgs,
        'patients': len(ordered),
        'mixed_label_patients': mixed,
        'metrics': metrics,
        'independent_percentile_ci95': intervals,
        'historical_percentile_ci95': historical['bootstrap'],
        'bootstrap': {'replicates': 2000, 'seed': 20261117, 'unit': 'WHOLE_PATIENT_PAIRED'},
        'limitations': [
            'Original historical generator not recovered',
            'Thresholds optimized on development OOF; conditional intervals only',
            'No waveform access, no independent holdout and no clinical validity claim',
        ],
    }
    if output is not None:
        dest = Path(output)
        if dest.exists():
            raise ValueError('Output exists; refusing overwrite')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+'\n', encoding='utf-8')
    return report

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--oof', type=Path, required=True)
    p.add_argument('--metadata', type=Path, required=True)
    p.add_argument('--audit-json', type=Path, required=True)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    result = verify(a.oof, a.metadata, a.audit_json, a.output)
    print(result['status'])
    print('SENSITIVITY CI:', result['independent_percentile_ci95']['sensitivity'])
    print('SPECIFICITY CI:', result['independent_percentile_ci95']['specificity'])
    print('FOLD 10: NO_GO')

if __name__ == '__main__':
    main()
