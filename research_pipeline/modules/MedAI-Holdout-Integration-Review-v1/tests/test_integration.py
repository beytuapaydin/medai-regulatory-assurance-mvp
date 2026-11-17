import array, json, math, os, sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import integration_review as m

def sample_model():
    return {'type':'l2_logistic_regression','l2_penalty':.1,'epochs':200,'learning_rate':.25,'decision_threshold':m.THRESHOLD,'weights':[.1]*72,'feature_mean':[0.0]*72,'feature_std':[1.0]*72,'intercept':-.2}

def test_frozen_hashes():
    assert m.MODEL_HASH=='B0DBD0E84285F7F920545AEA8FA5C52E3812F399A8A1BE5F2C3EEDEB0CC231A0'
    assert m.PLAN_HASH=='84862632310C1634CDC39BE82A43C260E7331E4CC9DA51757A7420B6A4DBCF27'

def test_model_fails_threshold_change():
    x=sample_model();x['decision_threshold']=.5
    with pytest.raises(ValueError):m.validate_model(x)

def test_model_fails_nonfinite_weight():
    x=sample_model();x['weights'][0]=float('nan')
    with pytest.raises(ValueError):m.validate_model(x)

def test_model_fails_dimension():
    x=sample_model();x['weights']=x['weights'][:-1]
    with pytest.raises(ValueError):m.validate_model(x)

def test_model_fails_bad_scaler():
    x=sample_model();x['feature_std'][0]=0
    with pytest.raises(ValueError):m.validate_model(x)

def test_score_matches_known_sigmoid():
    assert abs(m.independent_score(sample_model(),[0]*72)-1/(1+math.exp(.2)))<1e-14

def test_write_wave(tmp_path):
    rel=m.write_wave(tmp_path,42,2)
    assert (tmp_path/(rel+'.dat')).stat().st_size==24000
    assert len((tmp_path/(rel+'.hea')).read_text().splitlines())==13

def test_write_wave_deterministic(tmp_path):
    rel=m.write_wave(tmp_path,42,2);first=m.digest(tmp_path/(rel+'.dat'))
    m.write_wave(tmp_path,42,2)
    assert m.digest(tmp_path/(rel+'.dat'))==first

def test_hash_rejects_tamper(tmp_path):
    p=tmp_path/'x';p.write_bytes(b'ok');h=m.digest(p);m.verify(p,h)
    p.write_bytes(b'evil')
    with pytest.raises(ValueError):m.verify(p,h)

def test_synthetic_waveform_to_metrics(tmp_path):
    # Uses the same locked original waveform reader as final model training.
    source=Path(os.environ['MEDAI_PILOT_SOURCE'])/'ptbxl_pilot_train.py'
    assert source.is_file()
    train=m.load_source(source)
    rows=m.synthetic_pipeline(train,sample_model(),tmp_path,12)
    assert len(rows)==15
    assert len({x['patient_id'] for x in rows})==12
    from holdout_math_v1 import patient_components,weighted_stats
    z=weighted_stats(patient_components(rows))
    assert z['n_sensitivity_patients']>0 and z['n_specificity_patients']>0

def test_no_real_data_cli():
    src=(ROOT/'integration_review.py').read_text()
    assert "'data-dir'" not in src and "'holdout-dir'" not in src

def test_no_authorization():
    assert m.THRESHOLD==.3795860831201651
    assert 'holdout_authorized\':False' in (ROOT/'integration_review.py').read_text()
