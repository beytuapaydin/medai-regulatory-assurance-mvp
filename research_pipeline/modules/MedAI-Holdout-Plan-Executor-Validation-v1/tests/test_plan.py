import json,sys,pytest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from holdout_math_v1 import THRESHOLD,validate_rows,patient_components,weighted_stats,record_stats,bootstrap_ci,subgroup_summary,age_bucket
from validate_plan_v1 import plan,synthetic_rows,check,digest,LOCKED

def case(id,p,y,score,fold=1,age=40,sex=0):
    return {'ecg_id':id,'patient_id':p,'fold':fold,'y_true':y,'probability':score,'age':age,'sex':sex}

def test_synthetic():
    r=synthetic_rows(); assert len(r)>160 and validate_rows(r)==160

def test_threshold_equality_positive():
    r=[case(1,1,1,THRESHOLD),case(2,2,0,0.01)]
    assert weighted_stats(patient_components(r))['sensitivity']==1
    assert record_stats(r)['specificity']==1

def test_mixed_label_whole_patient():
    r=[case(1,1,1,.8),case(2,1,0,.8),case(3,2,0,.02)]
    c=patient_components(r)
    assert len(c)==2
    x=weighted_stats(c)
    assert x['mixed_label_patients']==1 and x['sensitivity']==1 and x['specificity']==.5

def test_patient_not_record_weighted():
    r=[case(1,1,1,.9),case(2,1,1,.9),case(3,2,1,.01),case(4,3,0,.01)]
    assert weighted_stats(patient_components(r))['sensitivity']==.5
    assert record_stats(r)['sensitivity']==2/3

def test_duplicate_fails():
    with pytest.raises(ValueError): validate_rows([case(1,1,1,.8),case(1,2,0,.1)])

def test_fold_leak_fails():
    with pytest.raises(ValueError):validate_rows([case(1,1,1,.8),case(2,1,0,.1,fold=2)])

def test_bad_probability_fails():
    with pytest.raises(ValueError):validate_rows([case(1,1,1,float('nan'))])
    with pytest.raises(ValueError):validate_rows([case(1,1,1,1.1)])

def test_age_policy():
    assert age_bucket(300)=='AGE_300_SENTINEL'
    assert age_bucket(None)=='AGE_MISSING'
    assert age_bucket(75)=='AGE_75_PLUS'

def test_subgroup_insufficient():
    r=[case(1,1,1,.8),case(2,2,0,.1)]
    out=subgroup_summary(r)
    assert out['age:AGE_LT_65']['status']=='INSUFFICIENT_EVIDENCE'
    assert out['age:AGE_LT_65']['sensitivity'] is None

def test_bootstrap_seed_and_bounded():
    c=patient_components(synthetic_rows());a=bootstrap_ci(c,100,7);b=bootstrap_ci(c,100,7)
    assert a==b
    assert 0<=a['sensitivity_ci95'][0]<=a['sensitivity_ci95'][1]<=1

def test_invalid_threshold_fails():
    with pytest.raises(ValueError):patient_components(synthetic_rows(),.5)

def test_plan_no_authorization():
    p=plan()
    assert p['holdout_authorized'] is False
    assert p['fixed_threshold']==THRESHOLD
    assert len(p['required_independent_signoffs'])==3
    assert 'NOT_DEFINED' in p['clinical_success']

def test_hash_tamper_rejected(tmp_path):
    dirs={name:tmp_path for name in LOCKED}
    for name in LOCKED:(tmp_path/name).write_text('tampered')
    with pytest.raises(ValueError,match='locked evidence mismatch'):check(dirs)

def test_synthetic_runner_creates_evidence(monkeypatch,tmp_path):
    import validate_plan_v1 as v
    monkeypatch.setattr(v,'check',lambda mapping:None)
    args=type('Args',(),{'output_dir':tmp_path/'new','docs':tmp_path/'docs',
          'freeze_dir':tmp_path/'frozen','model_dir':tmp_path/'model'})()
    v.run(args)
    report=json.loads((args.output_dir/'synthetic_executor_validation.json').read_text())
    mani=json.loads((args.output_dir/'plan_validation_manifest.json').read_text())
    assert report['status']=='PASS_SYNTHETIC_EXECUTOR_VALIDATION_ONLY'
    assert mani['holdout_authorized'] is False
    for name,hash_value in mani['files_sha256'].items():
        assert digest(args.output_dir/name)==hash_value
    with pytest.raises(ValueError,match='output already exists'):
        v.run(args)

def test_missing_required_group_reports_insufficient():
    r=[case(1,1,1,THRESHOLD,age=300),case(2,2,0,0.01,age=None)]
    groups=subgroup_summary(r)
    assert groups['age:AGE_300_SENTINEL']['status']=='INSUFFICIENT_EVIDENCE'
    assert groups['age:AGE_MISSING']['status']=='INSUFFICIENT_EVIDENCE'
