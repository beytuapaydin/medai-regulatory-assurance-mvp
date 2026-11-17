#!/usr/bin/env python3
"""Read-only locked model + synthetic waveform integration validation. NO real holdout API."""
from __future__ import annotations
import argparse, array, hashlib, importlib.util, json, math, shutil, sys, tempfile
from pathlib import Path

TRAIN_HASH='9C0F6EEAE4A77FF77B361055C1D18CD21143DBF97828EFC56F7BA8CBB0CF4C0C'
MODEL_HASH='B0DBD0E84285F7F920545AEA8FA5C52E3812F399A8A1BE5F2C3EEDEB0CC231A0'
MANIFEST_HASH='C344B33BED7613420A854868BD849BCA0A7B89AC98D5EE101EE79CB8E402A50A'
PLAN_HASH='84862632310C1634CDC39BE82A43C260E7331E4CC9DA51757A7420B6A4DBCF27'
THRESHOLD=0.3795860831201651
LEADS=('I','II','III','AVR','AVL','AVF','V1','V2','V3','V4','V5','V6')

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest().upper()

def verify(path,expected):
    if not Path(path).is_file() or digest(path)!=expected:raise ValueError('FAIL_CLOSED: locked SHA256 mismatch: '+Path(path).name)

def load_source(path):
    verify(path,TRAIN_HASH)
    spec=importlib.util.spec_from_file_location('_medai_holdout_synthetic_train',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def validate_model(model):
    if model.get('type')!='l2_logistic_regression' or model.get('l2_penalty')!=0.1 or model.get('epochs')!=200 or model.get('learning_rate')!=.25:raise ValueError('FAIL_CLOSED: unexpected model config')
    if model.get('decision_threshold')!=THRESHOLD:raise ValueError('FAIL_CLOSED: threshold changed')
    for key in ('weights','feature_mean','feature_std'):
        if not isinstance(model.get(key),list) or len(model[key])!=72 or any(type(v) not in (int,float) or not math.isfinite(v) for v in model[key]):raise ValueError('FAIL_CLOSED: invalid '+key)
    if any(v<=0 for v in model['feature_std']) or type(model.get('intercept')) not in (int,float) or not math.isfinite(model['intercept']):raise ValueError('FAIL_CLOSED: invalid scaler/intercept')

def independent_score(m,x):
    validate_model(m)
    if len(x)!=72 or any(not math.isfinite(float(v)) for v in x):raise ValueError('FAIL_CLOSED: invalid features')
    z=m['intercept']+sum(w*(v-mu)/sd for w,v,mu,sd in zip(m['weights'],x,m['feature_mean'],m['feature_std']))
    if z>=0:return 1/(1+math.exp(-z))
    e=math.exp(z);return e/(1+e)

def write_wave(root,ecg_id,variant):
    """Create an artificial WFDB 16bit 100Hz 12 lead waveform, never a patient ECG."""
    basename=f'{ecg_id:05d}_lr'; rel=f'records100/00000/{basename}'
    folder=root/'records100'/'00000';folder.mkdir(parents=True,exist_ok=True)
    header=[f'{basename} 12 100 1000']
    header.extend(f'{basename}.dat 16 1000(10)/mV 16 10 0 0 0 {lead}' for lead in LEADS)
    (folder/(basename+'.hea')).write_text('\n'.join(header)+'\n',encoding='ascii')
    vals=array.array('h')
    for t in range(1000):
        for ch in range(12):
            vals.append(10 + (((t*3+ch*5+variant*13)%127)-63)*variant + 2*ch)
    if sys.byteorder!='little': vals.byteswap()
    (folder/(basename+'.dat')).write_bytes(vals.tobytes())
    return rel

def synthetic_pipeline(train,model,workdir,npatients=24):
    if npatients<4:raise ValueError('FAIL_CLOSED: insufficient synthetic patients')
    rows=[]
    hashes={}
    for pid in range(1,npatients+1):
        for j in range(2 if pid%4==0 else 1):
            ecg=pid*10+j;rel=write_wave(workdir,ecg,1+(pid+j)%4)
            for extension in ('.hea','.dat'):hashes[rel+extension]=digest(workdir/(rel+extension)).lower()
            rows.append((ecg,pid,int((pid+j)%3==0),rel))
    if len(rows)!=npatients+npatients//4:raise ValueError('FAIL_CLOSED: synthetic inventory invalid')
    results=[]
    for ecg,pid,y,rel in rows:
        train.verify_record_files(workdir,rel,hashes)
        features=train.read_features(workdir,rel)
        if len(features)!=72:raise ValueError('FAIL_CLOSED: wrong feature dimension')
        score_a=independent_score(model,features)
        score_b=train.predict(model,features)
        if abs(score_a-score_b)>1e-12:raise ValueError('FAIL_CLOSED: inference mismatch')
        results.append({'ecg_id':ecg,'patient_id':pid,'fold':10,'y_true':y,'probability':score_a,'age':300 if pid%7==0 else 30+pid,'sex':pid%2})
    return results

def audit_plan_and_model(model_dir,plan_dir):
    model_dir,plan_dir=Path(model_dir),Path(plan_dir)
    verify(model_dir/'candidate_model.json',MODEL_HASH)
    verify(model_dir/'final_model_manifest.json',MANIFEST_HASH)
    verify(plan_dir/'plan_validation_manifest.json',PLAN_HASH)
    manifest=json.loads((model_dir/'final_model_manifest.json').read_text(encoding='utf8'))
    if manifest.get('status')!='LOCAL_INTEGRITY_MANIFEST_NOT_HOLDOUT_AUTHORIZATION':raise ValueError('FAIL_CLOSED: model manifest status')
    for filename,expect in manifest.get('files_sha256',{}).items():
        if filename not in ('candidate_model.json','final_model_report.json'):raise ValueError('FAIL_CLOSED: unexpected model manifest member')
        verify(model_dir/filename,expect.upper())
    if set(manifest.get('files_sha256',{}))!={'candidate_model.json','final_model_report.json'}:raise ValueError('FAIL_CLOSED: incomplete manifest')
    locked=json.loads((plan_dir/'plan_validation_manifest.json').read_text(encoding='utf8'))
    if locked.get('status')!='PREHOLDOUT_PLAN_LOCKED_LOCALLY_PENDING_INDEPENDENT_REVIEW' or locked.get('holdout_authorized') is not False:raise ValueError('FAIL_CLOSED: plan state')
    for f,sha in locked.get('files_sha256',{}).items():verify(plan_dir/f,sha.upper())
    if set(locked.get('files_sha256',{}))!={'statistical_analysis_plan.json','synthetic_executor_validation.json'}:raise ValueError('FAIL_CLOSED: plan files incomplete')
    plan=json.loads((plan_dir/'statistical_analysis_plan.json').read_text(encoding='utf8'))
    if plan.get('holdout_authorized') is not False or plan.get('fixed_threshold')!=THRESHOLD or plan.get('holdout_fold')!=10:raise ValueError('FAIL_CLOSED: plan config')
    model=json.loads((model_dir/'candidate_model.json').read_text(encoding='utf8'))
    validate_model(model)
    return model,plan

def run(args):
    output=Path(args.output).resolve()
    if output.exists():raise ValueError('FAIL_CLOSED: evidence output exists')
    model,plan=audit_plan_and_model(args.model_dir,args.plan_dir)
    train=load_source(Path(args.pilot_source)/'ptbxl_pilot_train.py')
    # Only artificial WFDB waveforms are read. This tool has no --data-dir argument.
    from holdout_math_v1 import THRESHOLD as METRIC_THRESHOLD,patient_components,weighted_stats,record_stats,bootstrap_ci,subgroup_summary
    if METRIC_THRESHOLD!=THRESHOLD:raise ValueError('FAIL_CLOSED: statistics threshold drift')
    with tempfile.TemporaryDirectory(prefix='medai_synthetic_wfdb_') as tmp:
        rows=synthetic_pipeline(train,model,Path(tmp))
        weighted=weighted_stats(patient_components(rows))
        record=record_stats(rows)
        bootstrap=bootstrap_ci(patient_components(rows),replicates=200,seed=20261117)
        groups=subgroup_summary(rows)
        # Negative mutation: verify checksum detects a corrupt waveform and does not score it.
        rel=write_wave(Path(tmp),999,2)
        hashes={rel+'.hea':digest(Path(tmp)/(rel+'.hea')).lower(),rel+'.dat':digest(Path(tmp)/(rel+'.dat')).lower()}
        dat=Path(tmp)/(rel+'.dat');dat.write_bytes(dat.read_bytes()+b'X')
        rejected=False
        try:train.verify_record_files(Path(tmp),rel,hashes)
        except (ValueError,OSError):rejected=True
        if not rejected:raise ValueError('FAIL_CLOSED: tampered waveform not rejected')
    report={'schema_version':'medai-holdout-integration-review-v1','status':'PASS_SYNTHETIC_WFDB_INTEGRATION_HOLDOUT_NOT_AUTHORIZED',
            'dataset':'SYNTHETIC_WFDB_ONLY_NOT_REAL_PTBXL','records':len(rows),'patients':len({r['patient_id'] for r in rows}),
            'patient_weighted':weighted,'record_weighted':record,'bootstrap_ci95':bootstrap,
            'subgroups':groups,'model_sha256':MODEL_HASH,'plan_manifest_sha256':PLAN_HASH,'training_source_sha256':TRAIN_HASH,
            'runner_sha256':digest(Path(__file__)),'metric_source_sha256':digest(Path(__file__).parent/'holdout_math_v1.py'),
            'synthetic_tamper_test':'PASS','inference_crosscheck':'PASS_TOLERANCE_1E-12',
            'fold9_10_real_labels_signals_accessed':False,'holdout_authorized':False,
            'independent_human_review_completed':False,
            'blockers':['Independent statistical SAP review','Independent real-waveform runner and source security review','Explicit documented single-use research holdout access authorization'],
            'limitations':['Synthetic WFDB signals do not establish correct PTB-XL real-world integration or model diagnostic performance',
                           'Same source waveform reader as training, not a separately implemented reader',
                           'No independent human sign-off; cannot authorize real fold10 access']}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    print('STATUS:',report['status'])
    print('SYNTHETIC WFDB RECORDS/PATIENTS:',len(rows),'/',report['patients'])
    print('SYNTHETIC INFERENCE: PASS')
    print('SYNTHETIC TAMPER CHECK: PASS')
    print('HOLDOUT AUTHORIZED: NO')
    print('BLOCKERS:',len(report['blockers']))
    print('FOLD 9/10 REAL SIGNALS/LABELS: NOT READ')
    print('REPORT:',output)
    print('SHA256:',digest(output))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('pilot-source','model-dir','plan-dir','output'):ap.add_argument('--'+key,type=Path,required=True)
    a=ap.parse_args()
    try:run(a)
    except (ValueError,OSError,KeyError,TypeError,ImportError,json.JSONDecodeError) as e:ap.exit(2,'FAIL_CLOSED: '+str(e)+'\n')
if __name__=='__main__':main()
