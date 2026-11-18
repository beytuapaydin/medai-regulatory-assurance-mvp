"""Adversarial, deterministic tests of OPTIONAL research statistics, never a clinical gate."""
from __future__ import annotations

from math import isclose
import pytest

from src.clinical_validation.paired_estimands_v1 import paired_estimands_exploratory


def row(pid, y, b, c, eid=None):
    r = {'patient_id': pid, 'y_true': y, 'y_pred_v1': b, 'y_pred_v2': c}
    if eid is not None:
        r['ecg_id'] = eid
    return r


def test_t01_imbalanced_cluster_estimands_are_distinct():
    rows = [row(f'P{i}', 1, 1, 1) for i in range(29)] + [row('H', 1, 1, 0) for _ in range(40)]
    result = paired_estimands_exploratory(rows, replicates=300)
    s = result['sensitivity']
    assert s['n_records'] == 69 and s['n_patients'] == 30
    assert isclose(s['record_weighted']['candidate'], 29/69)
    assert isclose(s['patient_weighted']['candidate'], 29/30)
    assert isclose(s['record_weighted']['delta_candidate_minus_baseline'], -40/69)
    assert isclose(s['patient_weighted']['delta_candidate_minus_baseline'], -1/30)


def test_t02_equal_cluster_sizes_yield_identical_estimands():
    rows = [row('A', 1, 1, 0), row('A', 1, 1, 0), row('B', 1, 1, 1), row('B', 1, 1, 1)]
    s = paired_estimands_exploratory(rows, replicates=300)['sensitivity']
    for key in ('baseline', 'candidate', 'delta_candidate_minus_baseline'):
        assert s['record_weighted'][key] == s['patient_weighted'][key]
    assert s['record_weighted']['delta_ci_lower'] == s['patient_weighted']['delta_ci_lower']
    assert s['record_weighted']['delta_ci_upper'] == s['patient_weighted']['delta_ci_upper']


def test_t03_identical_predictions_give_zero_deltas_and_intervals():
    rows = [row(f'P{i}', 1, i % 2, i % 2) for i in range(35)]
    rows += [row(f'N{i}', 0, i % 2, i % 2) for i in range(35)]
    result = paired_estimands_exploratory(rows, replicates=300)
    for endpoint in ('sensitivity', 'specificity'):
        for weight in ('record_weighted', 'patient_weighted'):
            m = result[endpoint][weight]
            assert m['delta_candidate_minus_baseline'] == 0
            assert m['delta_ci_lower'] == m['delta_ci_upper'] == 0


def test_t04_candidate_extra_false_positives_make_specificity_delta_negative():
    rows = [row(f'N{i}', 0, 0, 1 if i < 4 else 0) for i in range(35)]
    s = paired_estimands_exploratory(rows, replicates=300)['specificity']
    assert isclose(s['record_weighted']['delta_candidate_minus_baseline'], -4/35)
    assert isclose(s['patient_weighted']['delta_candidate_minus_baseline'], -4/35)


def test_t05_patient_clusters_preserve_pairing_and_do_not_fake_n():
    rows = [row('ONE', 1, 1, 0) for _ in range(30)] + [row('TWO', 1, 0, 1)]
    r = paired_estimands_exploratory(rows, replicates=300)['sensitivity']
    assert r['n_patients'] == 2 and r['n_records'] == 31 and r['max_ecgs_per_patient'] == 30
    assert r['record_weighted']['delta_candidate_minus_baseline'] < 0
    assert r['patient_weighted']['delta_candidate_minus_baseline'] == 0


def test_t06_bitwise_determinism_with_fixed_seed():
    rows = [row(f'P{i}', 1, 1, int(i % 3 != 0)) for i in range(40)]
    args = {'replicates': 350, 'seed': 1701}
    assert paired_estimands_exploratory(rows, **args) == paired_estimands_exploratory(rows, **args)


def test_t07_small_subgroup_never_claims_clinical_gate():
    rows = [row(f'P{i}', 1, 1, 1) for i in range(9)]
    r = paired_estimands_exploratory(rows, replicates=300)
    assert r['sensitivity']['below_demo_min_patient_count']
    assert r['sensitivity']['status'] == 'EXPLORATORY_LOW_N'
    assert r['evaluation_scope'] == 'RESEARCH_EXPLORATORY_ONLY'
    assert r['clinical_gate'] == 'NOT_EVALUATED'


def test_t08_empty_class_explicit_not_estimable():
    r = paired_estimands_exploratory([row('P1', 1, 1, 1)], replicates=300)
    assert r['specificity']['status'] == 'NOT_ESTIMABLE'
    assert r['specificity']['n_patients'] == 0


@pytest.mark.parametrize('invalid', [
    row('P1', 1, 2, 1), row('P1', True, 1, 1),
    row('', 1, 1, 1), row('P 1', 1, 1, 1),
    {'patient_id': 'P1', 'y_true': 1, 'y_pred_v1': 1},
])
def test_t08_invalid_input_fails_closed(invalid):
    with pytest.raises(ValueError):
        paired_estimands_exploratory([invalid], replicates=300)


def test_t09_no_fabricated_heldout_or_release_claim():
    r = paired_estimands_exploratory([row('P1', 1, 1, 1)], replicates=300)
    assert r['clinical_gate'] == 'NOT_EVALUATED'
    assert r['manufacturer_release_decision'] == 'OUTSIDE_PLATFORM_SCOPE'


def test_t10_patient_id_canonicalization_avoids_phantom_cluster():
    rows = [row('15709.0', 1, 1, 0), row('15709', 1, 1, 0), row('15710', 1, 1, 1)]
    s = paired_estimands_exploratory(rows, replicates=300)['sensitivity']
    assert s['n_patients'] == 2 and s['max_ecgs_per_patient'] == 2


def test_t11_each_weighting_has_own_interval_distribution():
    rows = [row('LARGE', 1, 1, 0) for _ in range(40)] + [row(f'P{i}', 1, 1, 1) for i in range(29)]
    s = paired_estimands_exploratory(rows, replicates=1000)['sensitivity']
    assert s['record_weighted']['delta_ci_lower'] < s['patient_weighted']['delta_ci_lower']
    assert (s['record_weighted']['delta_ci_lower'], s['record_weighted']['delta_ci_upper']) != (s['patient_weighted']['delta_ci_lower'], s['patient_weighted']['delta_ci_upper'])


def test_t12_reject_duplicate_ecg_id_when_provided():
    with pytest.raises(ValueError, match='Duplicate ecg_id'):
        paired_estimands_exploratory([row('P1', 1, 1, 1, '1'), row('P2', 1, 1, 1, '1.0')], replicates=300)


def test_invalid_bootstrap_settings_rejected():
    rows = [row('P1', 1, 1, 1)]
    for kw in ({'replicates': 5}, {'seed': True}, {'confidence_level': float('nan')}, {'confidence_level': 1.0}):
        with pytest.raises(ValueError):
            paired_estimands_exploratory(rows, **kw)


def test_tags_without_all_must_not_disappear_from_exploratory_estimate():
    with pytest.raises(ValueError, match='ALL'):
        paired_estimands_exploratory([{**row('P1', 1, 1, 0), 'subgroups': ['EXCLUDED']}], replicates=300)


def test_strict_identity_mode_rejects_missing_ecg_and_duplicate_canonical_ids():
    no_id = [row('P1', 1, 1, 0)]
    with pytest.raises(ValueError, match='required ecg_id'):
        paired_estimands_exploratory(no_id, replicates=300, require_ecg_id=True)
    duplicates = [row('P1', 1, 1, 0, '15709'), row('P2', 0, 0, 0, '15709.0')]
    with pytest.raises(ValueError, match='Duplicate ecg_id'):
        paired_estimands_exploratory(duplicates, replicates=300, require_ecg_id=True)


def test_exploratory_age_tags_validate_sentinel_and_membership():
    valid = {**row('P1', 1, 1, 0, 'ECG-1'), 'age': 300,
             'subgroups': ['ALL', 'AGE75_PLUS']}
    assert paired_estimands_exploratory([valid], replicates=300,
                                       require_ecg_id=True)['sensitivity']['n_records'] == 1
    invalid_tag = {**valid, 'subgroups': ['ALL']}
    with pytest.raises(ValueError, match='AGE75_PLUS'):
        paired_estimands_exploratory([invalid_tag], replicates=300, require_ecg_id=True)
    missing_age = {**valid}
    del missing_age['age']
    with pytest.raises(ValueError):
        paired_estimands_exploratory([missing_age], replicates=300,
                                    require_ecg_id=True)
    bad_age = {**valid, 'age': 250}
    with pytest.raises(ValueError):
        paired_estimands_exploratory([bad_age], replicates=300,
                                    require_ecg_id=True)
