"""Additional paired patient-cluster descriptive statistics for MedAI research.

NO change to clinical_eval_runner, evidence_package_writer or PASS/FAIL gates.
The caller remains responsible for provenance, subgroup derivation, train/test
isolation, clinical endpoint definition, and pre-locked operating thresholds.
Input predictions MUST be binary values derived using the applicable threshold.
This module never processes raw clinical waveforms and never approves release.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite
from random import Random
from typing import Any, Mapping, Sequence

from .clinical_eval_runner import _canonical_patient_id, _canonical_ecg_id, _invalid_identifier
from .ptbxl_age_policy import ptbxl_age75_membership


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _validate(rows: Sequence[Mapping[str, Any]], *, require_ecg_id: bool = False) -> list[tuple[str, int, int, int]]:
    if not isinstance(rows, (tuple, list)) or not rows:
        raise ValueError('At least one record is required')
    validated = []
    seen_ecgs: set[str] = set()
    for i, r in enumerate(rows):
        if not isinstance(r, Mapping):
            raise ValueError(f'Row {i}: must be an object')
        required = ('patient_id', 'y_true', 'y_pred_v1', 'y_pred_v2')
        if any(k not in r for k in required):
            raise ValueError(f'Row {i}: missing required fields')
        if (not isinstance(r['patient_id'], str)
                or _invalid_identifier(r['patient_id'])):
            raise ValueError(f'Row {i}: invalid patient_id')
        for field in ('y_true', 'y_pred_v1', 'y_pred_v2'):
            if type(r[field]) is not int or r[field] not in (0, 1):
                raise ValueError(f'Row {i}: {field} must be binary integer')
        if require_ecg_id and 'ecg_id' not in r:
            raise ValueError(f'Row {i}: missing required ecg_id')
        if 'ecg_id' in r:
            eid = r['ecg_id']
            if type(eid) not in (int, str) or _invalid_identifier(str(eid)):
                raise ValueError(f'Row {i}: invalid ecg_id')
            norm_eid = _canonical_ecg_id(eid)
            if norm_eid in seen_ecgs:
                raise ValueError('Duplicate ecg_id')
            seen_ecgs.add(norm_eid)
        if 'subgroups' in r:
            tags = r['subgroups']
            if (not isinstance(tags, (list, tuple)) or 'ALL' not in tags
                    or any(not isinstance(t, str) or _invalid_identifier(t) for t in tags)
                    or len(set(tags)) != len(tags)):
                raise ValueError(f'Row {i}: subgroups must contain distinct tags including ALL')
        if 'age' in r or ('subgroups' in r and 'AGE75_PLUS' in r['subgroups']):
            age75 = ptbxl_age75_membership(r.get('age'))
            if 'subgroups' in r and ('AGE75_PLUS' in r['subgroups']) != age75:
                raise ValueError(f'Row {i}: AGE75_PLUS membership disagrees with age')
        validated.append((_canonical_patient_id(r['patient_id']),
                          r['y_true'], r['y_pred_v1'], r['y_pred_v2']))
    return validated


def _endpoint(rows: list[tuple[str, int, int, int]], label: int, *,
              confidence_level: float, replicates: int, seed: int,
              min_patient_count: int) -> dict[str, Any]:
    # Two models are ALWAYS sampled together per patient; never resample
    # patient records for baseline and candidate independently.
    groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for pid, truth, baseline, candidate in rows:
        if truth == label:
            if label == 1:
                groups[pid].append((baseline, candidate))
            else:
                groups[pid].append((1 - baseline, 1 - candidate))
    n_pat = len(groups)
    if not n_pat:
        return {'status': 'NOT_ESTIMABLE', 'n_records': 0, 'n_patients': 0,
                'record_weighted': None, 'patient_weighted': None}
    groups_sorted = [groups[k] for k in sorted(groups)]
    n_rec = sum(len(g) for g in groups_sorted)
    b_rec = sum(b for g in groups_sorted for b, _ in g) / n_rec
    c_rec = sum(c for g in groups_sorted for _, c in g) / n_rec
    b_pat = sum(sum(b for b, _ in g) / len(g) for g in groups_sorted) / n_pat
    c_pat = sum(sum(c for _, c in g) / len(g) for g in groups_sorted) / n_pat

    # Aggregate within patient BEFORE resampling: works equally for a patient
    # with one ECG or 40 ECGs; resampled clusters carry their multiplicity.
    aggregates = [(len(g), sum(b for b, _ in g), sum(c for _, c in g))
                  for g in groups_sorted]
    rng = Random(seed)
    rec_deltas: list[float] = []
    pat_deltas: list[float] = []
    if n_pat >= 2:
        for _ in range(replicates):
            picks = [aggregates[rng.randrange(n_pat)] for _ in range(n_pat)]
            total_ecgs = sum(g[0] for g in picks)
            rec_deltas.append(sum(g[2] - g[1] for g in picks) / total_ecgs)
            pat_deltas.append(sum((g[2] - g[1]) / g[0] for g in picks) / n_pat)
    alpha = (1 - confidence_level) / 2

    def weighted(b: float, c: float, deltas: list[float]) -> dict[str, Any]:
        return {
            'baseline': b,
            'candidate': c,
            'delta_candidate_minus_baseline': c - b,
            'delta_ci_lower': _quantile(deltas, alpha) if deltas else None,
            'delta_ci_upper': _quantile(deltas, 1 - alpha) if deltas else None,
        }
    return {
        'status': ('DESCRIPTIVE_NO_CI' if n_pat < 2 else
                   'EXPLORATORY_LOW_N' if n_pat < min_patient_count else 'EXPLORATORY_ONLY'),
        'n_records': n_rec,
        'n_patients': n_pat,
        'max_ecgs_per_patient': max(len(g) for g in groups_sorted),
        'below_demo_min_patient_count': n_pat < min_patient_count,
        'record_weighted': weighted(b_rec, c_rec, rec_deltas),
        'patient_weighted': weighted(b_pat, c_pat, pat_deltas),
        'resampling_unit': 'PATIENT_CLUSTER',
        'paired_models': True,
        'bootstrap_interval': 'PERCENTILE_EXPLORATORY',
        'replicates_requested': replicates,
        'seed': seed,
    }


def paired_estimands_exploratory(
    rows: Sequence[Mapping[str, Any]], *, confidence_level: float = 0.95,
    replicates: int = 1500, seed: int = 1701, min_patient_count: int = 30,
    require_ecg_id: bool = False,
) -> dict[str, Any]:
    """Research-only paired sensitivity/specificity, each with two estimands.

    Record-weighted: every ECG has equal weight. Patient-weighted: every
    patient contributes the mean correctness over their same-class ECGs.
    Intervals are paired cluster-resampled PERCENTILE confidence intervals.
    The min_patient_count is a demo warning, NOT a prospective power analysis.
    """
    if (type(confidence_level) not in (int, float) or not isfinite(confidence_level)
            or not 0 < confidence_level < 1):
        raise ValueError('confidence_level must be finite and between 0 and 1')
    if type(replicates) is not int or not 200 <= replicates <= 100_000:
        raise ValueError('replicates must be integer in [200, 100000]')
    if type(seed) is not int:
        raise ValueError('seed must be integer')
    if type(min_patient_count) is not int or min_patient_count < 2:
        raise ValueError('min_patient_count must be >= 2')
    if type(require_ecg_id) is not bool:
        raise ValueError('require_ecg_id must be a boolean')
    cleaned = _validate(rows, require_ecg_id=require_ecg_id)
    return {
        'schema_version': 'medai-exploratory-estimands-v1',
        'evaluation_scope': 'RESEARCH_EXPLORATORY_ONLY',
        'clinical_gate': 'NOT_EVALUATED',
        'manufacturer_release_decision': 'OUTSIDE_PLATFORM_SCOPE',
        'model_input': 'PAIRED_BINARY_PREDICTIONS_FROM_LOCKED_THRESHOLD_REQUIRED',
        'confidence_level': confidence_level,
        'replicates': replicates,
        'min_patient_count_demo_only': min_patient_count,
        'sensitivity': _endpoint(cleaned, 1, confidence_level=confidence_level,
                                 replicates=replicates, seed=seed,
                                 min_patient_count=min_patient_count),
        'specificity': _endpoint(cleaned, 0, confidence_level=confidence_level,
                                 replicates=replicates, seed=seed + 1,
                                 min_patient_count=min_patient_count),
        'known_limitations': [
            'Standalone legacy calls may omit ECG IDs unless require_ecg_id=True; production-quality source validation requires IDs.',
            'Exploratory, unqualified percentile bootstrap, not a clinical PASS/FAIL gate.',
            'Predictions, labels, cohort selection, test fold, threshold and model provenance are not authenticated here.',
            'Patient-weighted and record-weighted estimands have DIFFERENT intervals.',
            'Bootstrap intervals on small or biased samples may have poor coverage.',
            '30 patients per class is an illustrative warning threshold, not a power calculation.',
            'Estimands and multiplicity require pre-specification for clinical use.',
        ],
    }
