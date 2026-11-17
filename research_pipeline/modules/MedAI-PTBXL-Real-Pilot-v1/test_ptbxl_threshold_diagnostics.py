import csv
from pathlib import Path
import pytest
import ptbxl_threshold_diagnostics as d

def test_threshold_moves_sensitivity_and_specificity():
    y = [0,0,1,1]
    p = [0.1,0.2,0.4,0.9]
    a = d.score(y,p,0.5)
    b = d.score(y,p,0.3)
    assert a['tp'] == 1 and a['fn'] == 1 and a['tn'] == 2
    assert b['tp'] == 2 and b['fn'] == 0 and b['tn'] == 2

def test_posthoc_spec_constraint():
    y = [0,0,0,1,1]
    p = [0.1,0.2,0.3,0.25,0.9]
    best = d.best_at_specificity(d.threshold_sweep(y,p), 1.0)
    assert best['specificity'] == 1.0
    assert best['tp'] == 1

def test_refuse_fold10(tmp_path):
    p = tmp_path / 'v.csv'
    with p.open('w',newline='') as f:
        w = csv.writer(f)
        w.writerow(['ecg_id','patient_id','strat_fold','age','y_true',
                    'baseline_probability','baseline_pred',
                    'candidate_probability','candidate_pred'])
        w.writerow(['1','9','10','80','1','0.6','1','0.7','1'])
    with pytest.raises(ValueError, match='fold 9'):
        d.read_predictions(p)

def test_refuse_inconsistent_original_decision(tmp_path):
    p = tmp_path / 'v.csv'
    with p.open('w',newline='') as f:
        w = csv.writer(f)
        w.writerow(['ecg_id','patient_id','strat_fold','age','y_true',
                    'baseline_probability','baseline_pred',
                    'candidate_probability','candidate_pred'])
        w.writerow(['1','9','9','80','1','0.6','0','0.7','1'])
    with pytest.raises(ValueError, match='inconsistent'):
        d.read_predictions(p)

def test_coverage_all_unique_thresholds():
    sweep = d.threshold_sweep([0,1], [0.2,0.8])
    assert any(r['threshold'] == 0.5 for r in sweep)
    assert any(r['tp'] == 1 and r['tn'] == 1 for r in sweep)
