"""Synthetic-only RC1.3 verifier regression tests; never read real PTB-XL."""
import csv
import json
import importlib.util
from pathlib import Path
import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'independent_oof_v1.py'
spec = importlib.util.spec_from_file_location('rc13_independent_oof_v1', SOURCE)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)

def fixture(tmp_path, monkeypatch):
    metadata = tmp_path / 'ptbxl_database.csv'
    oof = tmp_path / 'training_oof_predictions.csv'
    audit = tmp_path / 'audit.json'
    write_csv(metadata, ['ecg_id','patient_id','strat_fold'], [
        {'ecg_id':1,'patient_id':10,'strat_fold':1},
        {'ecg_id':2,'patient_id':10,'strat_fold':1},
        {'ecg_id':3,'patient_id':20,'strat_fold':2},
        {'ecg_id':4,'patient_id':30,'strat_fold':3},
        {'ecg_id':5,'patient_id':40,'strat_fold':10},
    ])
    write_csv(oof, ['ecg_id','strat_fold','y_true','baseline_probability','candidate_probability'], [
        {'ecg_id':1,'strat_fold':1,'y_true':1,'baseline_probability':'.3','candidate_probability':'.7'},
        {'ecg_id':2,'strat_fold':1,'y_true':0,'baseline_probability':'.6','candidate_probability':'.4'},
        {'ecg_id':3,'strat_fold':2,'y_true':1,'baseline_probability':'.8','candidate_probability':'.9'},
        {'ecg_id':4,'strat_fold':3,'y_true':0,'baseline_probability':'.2','candidate_probability':'.1'},
    ])
    monkeypatch.setattr(v, 'THRESHOLDS', (.5,.5))
    monkeypatch.setattr(v, 'EXPECTED', {'ecgs':4,'patients':3,'mixed':1})
    ordered, count = v.load_development(metadata, oof)
    assert count == 4
    metrics, _ = v.compute(ordered, replicates=20, seed=8)
    audit.write_text(json.dumps({'thresholds':{'baseline':.5,'candidate':.5},
                                  'recomputed_metrics':metrics, 'bootstrap':{}}), encoding='utf-8')
    monkeypatch.setattr(v, 'LOCKS', {x:v.sha256(y) for x,y in
                        {'oof':oof,'metadata':metadata,'audit':audit}.items()})
    return oof,metadata,audit

def test_locked_input_synthetic_e2e(tmp_path, monkeypatch):
    oof,meta,audit = fixture(tmp_path, monkeypatch)
    original = v.compute
    monkeypatch.setattr(v, 'compute', lambda rows: original(rows, replicates=20, seed=8))
    out = tmp_path / 'aggregate.json'
    result = v.verify(oof,meta,audit,out)
    assert result['status'] == 'PASS_FIXED_THRESHOLD_METRICS_CI_NOT_IDENTICAL'
    assert result['mixed_label_patients'] == 1
    assert result['scope'].endswith('FOLD10_NO_GO')
    assert out.is_file()
    with pytest.raises(ValueError, match='Output exists'):
        v.verify(oof,meta,audit,out)

def test_hash_tampering_is_rejected(tmp_path, monkeypatch):
    oof,meta,audit = fixture(tmp_path, monkeypatch)
    with oof.open('a',encoding='utf-8') as f:
        f.write('tamper\n')
    with pytest.raises(ValueError, match='SHA256'):
        v.verify(oof,meta,audit)

def test_duplicate_ecg_and_mismatched_fold_rejected(tmp_path, monkeypatch):
    oof,meta,audit = fixture(tmp_path, monkeypatch)
    with oof.open('a',encoding='utf-8') as f:
        f.write('1,1,1,.3,.7\n')
    with pytest.raises(ValueError,match='Duplicate/unknown'):
        v.load_development(meta,oof)

def test_patient_fold_leakage_is_rejected(tmp_path, monkeypatch):
    oof,meta,audit = fixture(tmp_path, monkeypatch)
    with meta.open('a',encoding='utf-8') as f:
        f.write('9,10,4\n')
    with pytest.raises(ValueError,match='cross-fold'):
        v.load_development(meta,oof)

def test_whole_patient_resampling_is_deterministic():
    rows = [[1,0,1,1,1,0], [1,1,1,0,0,0], [0,0,0,1,1,1]]
    assert v.compute(rows,replicates=50,seed=17) == v.compute(rows,replicates=50,seed=17)
    metrics, intervals = v.compute(rows,replicates=50,seed=17)
    assert metrics['n_positive_patients'] == 2
    assert metrics['n_negative_patients'] == 2
    assert intervals['sensitivity'][0] <= intervals['sensitivity'][1]

def test_reject_degenerate_bootstrap_sample():
    with pytest.raises(ValueError,match='Degenerate'):
        v.compute([[1,1,1,0,0,0],[0,0,0,1,1,1]],replicates=100,seed=1)

@pytest.mark.parametrize('bad', ['0','-1','1.2','','unknown'])
def test_bad_ecg_ids_rejected(bad):
    with pytest.raises(ValueError):
        v.canonical_id(bad)
