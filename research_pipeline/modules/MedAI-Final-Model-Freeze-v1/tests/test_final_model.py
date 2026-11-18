import importlib.util, json, math, os, sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import final_model_freeze_v1 as f
import score_candidate_v1 as s

def model():
    return {'type':'l2_logistic_regression','l2_penalty':0.1,'epochs':200,'learning_rate':0.25,'decision_threshold':f.THRESHOLD,'weights':[0.1]*72,'feature_mean':[0.0]*72,'feature_std':[1.0]*72,'intercept':-0.2,'features_per_lead':['mean','std','p05_centered','p95_centered','mean_abs_diff','peak_to_peak'],'lead_order':['I','II','III','AVR','AVL','AVF','V1','V2','V3','V4','V5','V6']}

def test_frozen_hash_strings():
    assert f.FREEZE['freeze_manifest.json']=='53FFD3AE20CC6347B2969DF5C334F17052A650F8CAD71779DC11445C86CEDD61'
    assert f.FREEZE['protocol.json']=='B19AB6DF758A1C98B43C233B209DC6EF6F891677EA8A4FBCA6E1DD62F1FF2DBE'
    assert f.FREEZE['evidence_index.json']=='75F267B823B4A9FCF177C70C38725E8380541848C58960F8D43451FE3983E78D'

def test_pilot_train_hash_is_locked():
    assert f.TRAIN_HASH=='9C0F6EEAE4A77FF77B361055C1D18CD21143DBF97828EFC56F7BA8CBB0CF4C0C'

def test_check_hashes_accept_and_reject(tmp_path):
    (tmp_path/'a').write_bytes(b'abc')
    f.check_hashes(tmp_path,{'a':f.digest(tmp_path/'a')})
    (tmp_path/'a').write_bytes(b'abd')
    with pytest.raises(ValueError,match='SHA256'):f.check_hashes(tmp_path,{'a':'BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD'})

def test_score_zero_feature_vector():
    got=f.model_score(model(),[0.0]*72)
    assert abs(got-1/(1+math.exp(0.2)))<1e-15

def test_bad_model_rejected():
    for changed in (dict(model(),decision_threshold=.5),dict(model(),weights=[0.1]*71),dict(model(),feature_std=[0.0]*72)):
        with pytest.raises(ValueError):f.validate_model(changed)

def test_feature_and_lead_schema_required_and_ordered():
    for field in ('features_per_lead', 'lead_order'):
        without = model()
        del without[field]
        with pytest.raises(ValueError, match='feature order|lead order'):
            f.validate_model(without)
    permuted_leads = model()
    permuted_leads['lead_order'] = list(reversed(permuted_leads['lead_order']))
    with pytest.raises(ValueError, match='lead order'):
        f.validate_model(permuted_leads)
    permuted_features = model()
    permuted_features['features_per_lead'] = list(reversed(permuted_features['features_per_lead']))
    with pytest.raises(ValueError, match='feature order'):
        f.validate_model(permuted_features)


def test_bad_features_rejected():
    for x in ([0.0]*71,[0.0]*71+[float('nan')]):
        with pytest.raises(ValueError):f.model_score(model(),x)

def test_serialization_preserves_score(tmp_path):
    x=[float(i)/72 for i in range(72)]
    a=f.model_score(model(),x)
    f.json_write(tmp_path/'model.json',model())
    b=f.model_score(json.loads((tmp_path/'model.json').read_text()),x)
    assert a==b

def test_scoring_verifies_manifest(tmp_path):
    f.json_write(tmp_path/'candidate_model.json',model())
    f.json_write(tmp_path/'final_model_report.json',{'status':'RESEARCH_ONLY'})
    f.json_write(tmp_path/'final_model_manifest.json',{'files_sha256':{'candidate_model.json':f.digest(tmp_path/'candidate_model.json'),'final_model_report.json':f.digest(tmp_path/'final_model_report.json')},'status':'LOCAL_INTEGRITY_MANIFEST_NOT_HOLDOUT_AUTHORIZATION'})
    f.json_write(tmp_path/'features.json',[0.0]*72)
    assert s.score(tmp_path,tmp_path/'features.json')['status']=='RESEARCH_ONLY_NOT_CLINICAL'
    (tmp_path/'candidate_model.json').write_text('tampered')
    with pytest.raises(ValueError,match='hash mismatch'):s.score(tmp_path,tmp_path/'features.json')

def test_training_interface_matches_original():
    pilot_dir = (Path(os.environ['MEDAI_PILOT_SOURCE'])
                 if os.environ.get('MEDAI_PILOT_SOURCE')
                 else Path(__file__).resolve().parents[2] / 'MedAI-PTBXL-Real-Pilot-v1')
    p = pilot_dir / 'ptbxl_pilot_train.py'
    assert p.is_file(), f'Missing expected pilot training source: {p}'
    spec=importlib.util.spec_from_file_location('train_orig',p)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    X=[[float(i+j)/100 for j in range(72)] for i in range(8)]
    y=[0,1,0,1,0,1,0,1]
    m=mod.train_logistic(X,y,0.1,epochs=200,lr=.25)
    m['decision_threshold']=f.THRESHOLD
    assert abs(f.model_score(m,X[0])-mod.predict(m,X[0]))<1e-14
