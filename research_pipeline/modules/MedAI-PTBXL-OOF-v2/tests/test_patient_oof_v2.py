import csv
import importlib.util
from pathlib import Path
import sys
import pytest

MODULE = Path(__file__).resolve().parents[1] / 'ptbxl_patient_oof_v2.py'
spec = importlib.util.spec_from_file_location('ptbxl_patient_oof_v2', MODULE)
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


def example_rows():
    rows = []
    for fold in range(1, 9):
        rows.append(dict(ecg_id=str(fold*10+1), patient_id=str(fold), fold=fold, y_true=0,
                         baseline=.10, candidate=.20))
        rows.append(dict(ecg_id=str(fold*10+2), patient_id=str(fold+100), fold=fold, y_true=1,
                         baseline=.80, candidate=.85))
    return rows


def file_oof(tmp_path, data):
    p = tmp_path / 'oof.csv'
    with p.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=v2.COLUMNS)
        writer.writeheader()
        writer.writerows(data)
    return p


def manifest():
    return {r['ecg_id']: (r['patient_id'], r['fold'], r['y_true']) for r in example_rows()}


def csv_rows():
    return [dict(ecg_id=r['ecg_id'], strat_fold=str(r['fold']), y_true=str(r['y_true']),
                 baseline_probability=str(r['baseline']), candidate_probability=str(r['candidate'])) for r in example_rows()]


def test_patient_identifier_normalization():
    assert v2.patient_id('15709.0') == '15709'
    assert v2.patient_id('15709.00') == '15709'
    assert v2.patient_id('15709') == '15709'


@pytest.mark.parametrize('bad', ['15709.5', '0', '1e2', ' 1', '1\u200b', '', '１', None])
def test_rejects_ambiguous_patient_identifier(bad):
    with pytest.raises(ValueError):
        v2.patient_id(bad)


def test_mi_presence_policy():
    codes = frozenset({'AMI', 'INJAL'})
    assert v2.mi_truth("{'AMI': 0.0, 'NORM': 100.0}", codes) == 1
    assert v2.mi_truth("{'NORM': 100.0}", codes) == 0


def test_rejects_invalid_scp_entry():
    with pytest.raises(ValueError):
        v2.mi_truth("{'AMI': float('nan')}", frozenset({'AMI'}))


def test_patient_weight_differs_from_ecg_weight():
    rows = [dict(patient_id='A', y_true=0, baseline=.9),
            dict(patient_id='A', y_true=0, baseline=.9),
            dict(patient_id='A', y_true=0, baseline=.9),
            dict(patient_id='B', y_true=0, baseline=.1),
            dict(patient_id='C', y_true=1, baseline=.9)]
    rates = v2.patient_rates(rows, 'baseline', .5)
    assert rates['specificity'] == pytest.approx(.5)
    assert rates['sensitivity'] == 1
    assert rates['n_specificity_patients'] == 2


def test_patient_weighted_threshold_selection():
    rows = example_rows()
    a = v2.select_threshold(rows, 'baseline')
    b = v2.select_threshold(rows, 'baseline')
    assert a == b
    assert a['specificity'] >= .90
    assert a['sensitivity'] == 1
    assert a['threshold'] == .8


def test_requires_full_development_oof_by_default(tmp_path):
    dev = manifest() | {'999': ('999', 1, 1)}
    with pytest.raises(ValueError, match='Incomplete OOF'):
        v2.load_oof(file_oof(tmp_path, csv_rows()), dev)
    assert len(v2.load_oof(file_oof(tmp_path, csv_rows()), dev, pilot_subset=True)) == 16


def test_rejects_fold10_even_pilot_mode(tmp_path):
    rows = csv_rows()
    rows[0]['ecg_id'] = '999'
    rows[0]['strat_fold'] = '10'
    with pytest.raises(ValueError, match='non-development'):
        v2.load_oof(file_oof(tmp_path, rows), manifest(), pilot_subset=True)


def test_rejects_fold9_even_pilot_mode(tmp_path):
    rows = csv_rows()
    rows[0]['ecg_id'] = '999'
    rows[0]['strat_fold'] = '9'
    with pytest.raises(ValueError, match='non-development'):
        v2.load_oof(file_oof(tmp_path, rows), manifest(), pilot_subset=True)


def test_rejects_duplicate_ecg(tmp_path):
    rows = csv_rows()
    rows.append(rows[0].copy())
    with pytest.raises(ValueError, match='Duplicate'):
        v2.load_oof(file_oof(tmp_path, rows), manifest())


def test_rejects_label_mismatch(tmp_path):
    rows = csv_rows()
    rows[0]['y_true'] = '1'
    with pytest.raises(ValueError, match='label mismatch'):
        v2.load_oof(file_oof(tmp_path, rows), manifest())


def test_rejects_fold_mismatch(tmp_path):
    rows = csv_rows()
    rows[0]['strat_fold'] = '2'
    with pytest.raises(ValueError, match='fold/MI label mismatch'):
        v2.load_oof(file_oof(tmp_path, rows), manifest())


def test_rejects_nonfinite_scores(tmp_path):
    rows = csv_rows()
    rows[0]['baseline_probability'] = 'nan'
    with pytest.raises(ValueError, match='Nonfinite'):
        v2.load_oof(file_oof(tmp_path, rows), manifest())


def test_no_patients_in_output_of_threshold_selector():
    result = v2.select_threshold(example_rows(), 'candidate')
    assert 'patient_id' not in repr(result)


def test_metadata_full_inventory_fold10_scp_unread(tmp_path):
    """21,799 synthetic metadata rows: fold-10 label is malformed but never parsed."""
    codes = ['ALMI', 'AMI', 'ASMI', 'ILMI', 'IMI', 'INJAL', 'INJAS',
             'INJIL', 'INJIN', 'INJLA', 'IPLMI', 'IPMI', 'LMI', 'PMI']
    scp = tmp_path / 'scp_statements.csv'
    with scp.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['', 'diagnostic', 'diagnostic_class'])
        w.writeheader()
        for code in codes:
            w.writerow({'': code, 'diagnostic': '1.0', 'diagnostic_class': 'MI'})
    database = tmp_path / 'ptbxl_database.csv'
    with database.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['ecg_id', 'patient_id', 'strat_fold', 'filename_lr', 'scp_codes'])
        w.writeheader()
        for i in range(1, 21800):
            patient = (i - 1) % 18869 + 1
            fold = (patient - 1) % 10 + 1
            w.writerow({'ecg_id': str(i), 'patient_id': f'{patient}.0', 'strat_fold': str(fold),
                        'filename_lr': f'records100/{i // 1000 * 1000:05d}/{i:05d}_lr',
                        'scp_codes': 'deliberately INVALID, never inspect' if fold in (9, 10)
                                     else "{'AMI': 0.0}" if patient % 2 else "{'NORM': 100.0}"})
    dev, fold_counts, found = v2.load_metadata(tmp_path, expected_hashes={
        'ptbxl_database.csv': v2.sha(database), 'scp_statements.csv': v2.sha(scp)})
    assert sum(fold_counts.values()) == 21799
    assert len(dev) == sum(fold_counts[i] for i in range(1, 9))
    assert found == frozenset(codes)
