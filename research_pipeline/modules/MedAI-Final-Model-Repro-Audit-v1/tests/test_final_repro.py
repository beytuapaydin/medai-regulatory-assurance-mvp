import importlib.util
import json
import math
from pathlib import Path
import pytest

SOURCE=Path(__file__).resolve().parents[1]/'audit_final_model_v1.py'
spec=importlib.util.spec_from_file_location('final_repro_audit',SOURCE)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

def model():
    return {'type':'l2_logistic_regression','l2_penalty':.1,'epochs':200,'learning_rate':.25,'decision_threshold':a.THRESHOLD,'intercept':-.3,
            'weights':[.1]*72,'feature_mean':[0.0]*72,'feature_std':[1.0]*72,
            'features_per_lead':['mean','std','p05_centered','p95_centered','mean_abs_diff','peak_to_peak'],
            'lead_order':['I','II','III','AVR','AVL','AVF','V1','V2','V3','V4','V5','V6']}

def test_known_model_hash_pin():
    assert a.EXPECTED['candidate_model.json']=='B0DBD0E84285F7F920545AEA8FA5C52E3812F399A8A1BE5F2C3EEDEB0CC231A0'

def test_known_manifest_hash_pin():
    assert a.EXPECTED['final_model_manifest.json']=='C344B33BED7613420A854868BD849BCA0A7B89AC98D5EE101EE79CB8E402A50A'

def test_model_self_replay():
    assert max(a.compare_models(model(),model()).values())==0

def test_tamper_weights_rejected():
    changed=model();changed['weights'][0]+=1e-6
    with pytest.raises(ValueError,match='replay mismatch'):
        a.compare_models(changed,model(),1e-12)

def test_tamper_scaler_rejected():
    changed=model();changed['feature_std'][12]*=2
    with pytest.raises(ValueError,match='replay mismatch'):
        a.compare_models(changed,model(),1e-12)

def test_tamper_threshold_rejected():
    changed=model();changed['decision_threshold']=.5
    with pytest.raises(ValueError,match='hyperparameter'):
        a.compare_models(changed,model())

def test_nonfinite_rejected():
    changed=model();changed['intercept']=math.nan
    with pytest.raises(ValueError,match='intercept'):
        a.check_model(changed)

def test_invalid_features_rejected():
    with pytest.raises(ValueError,match='feature'):
        a.independent_score(model(),[0.0]*71)

def test_score_probability():
    expect=1/(1+math.exp(.3))
    assert abs(a.independent_score(model(),[0.0]*72)-expect)<1e-15

def test_hash_tamper_rejected(tmp_path):
    (tmp_path/'x').write_bytes(b'original')
    pinned=a.sha(tmp_path/'x')
    a.check_pins(tmp_path,{'x':pinned})
    (tmp_path/'x').write_bytes(b'modified')
    with pytest.raises(ValueError,match='SHA256 mismatch'):
        a.check_pins(tmp_path,{'x':pinned})

def test_id_normalizer():
    assert a.normalize_id('15709.0')=='15709'
    assert a.normalize_id('15709')=='15709'
    with pytest.raises(ValueError):a.normalize_id('15709.5')

def test_tolerance_fail_closed():
    with pytest.raises(ValueError,match='Tolerance'):
        a.compare_models(model(),model(),1e-4)

def test_fold_9_10_are_excluded_by_code():
    import inspect
    code=inspect.getsource(a.development_rows)
    assert "if fold not in range(1,9):" in code
