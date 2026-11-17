#!/usr/bin/env python3
"""Research-only final Candidate artifact training, folds 1-8 only; holdout prohibited."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, shutil, tempfile
from pathlib import Path

FREEZE = {'protocol.json':'B19AB6DF758A1C98B43C233B209DC6EF6F891677EA8A4FBCA6E1DD62F1FF2DBE',
'evidence_index.json':'75F267B823B4A9FCF177C70C38725E8380541848C58960F8D43451FE3983E78D',
'freeze_manifest.json':'53FFD3AE20CC6347B2969DF5C334F17052A650F8CAD71779DC11445C86CEDD61'}
OOF={'training_oof_predictions.csv':'ED83A106581E43275803D2E343F513D5BFC2B80A50E33584651816AE88A71E38',
'full_oof_report.json':'E6F4C9AEB01ED3C8469181A36CE97BA22328BA2E09845BA909077B390FDC0E6D',
'manifest.json':'CE779FC76ECFC203FEF105761AAF64A619A1A534F185A86BFDEB26DDFDD237CE'}
TRAIN_HASH='9C0F6EEAE4A77FF77B361055C1D18CD21143DBF97828EFC56F7BA8CBB0CF4C0C'
OOF_V2_HASH='A2190AF2A41B1BBA01FCF3D37F9C19E47DCFB618DE74E5154D6ACE3E444FD06E'
RUNNER_HASH=''
THRESHOLD=0.3795860831201651

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''): h.update(block)
    return h.hexdigest().upper()

def check_hashes(directory, expected):
    for name,sha in expected.items():
        p=Path(directory)/name
        if not p.is_file() or digest(p)!=sha: raise ValueError(f'FAIL_CLOSED: locked evidence SHA256 mismatch: {name}')

def load_checked(name, path, expected):
    if digest(path)!=expected: raise ValueError(f'FAIL_CLOSED: source SHA256 mismatch: {path.name}')
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise ValueError('FAIL_CLOSED: module loading failed')
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def validate_model(model):
    if model.get('type')!='l2_logistic_regression' or model.get('l2_penalty')!=0.1 or model.get('epochs')!=200 or model.get('learning_rate')!=0.25: raise ValueError('FAIL_CLOSED: unexpected model config')
    if model.get('decision_threshold')!=THRESHOLD: raise ValueError('FAIL_CLOSED: threshold not locked')
    if any(not isinstance(model.get(k),list) or len(model[k])!=72 for k in ('weights','feature_mean','feature_std')): raise ValueError('FAIL_CLOSED: invalid model dimensions')
    if not all(isinstance(x,(int,float)) and math.isfinite(x) for k in ('weights','feature_mean','feature_std') for x in model[k]): raise ValueError('FAIL_CLOSED: nonfinite model')
    if any(x<=0 for x in model['feature_std']) or not math.isfinite(model.get('intercept',float('nan'))): raise ValueError('FAIL_CLOSED: invalid scaler or intercept')

def model_score(model, features):
    validate_model(model)
    if len(features)!=72 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in features): raise ValueError('FAIL_CLOSED: invalid features')
    z=model['intercept']+sum(w*(x-m)/s for w,x,m,s in zip(model['weights'],features,model['feature_mean'],model['feature_std']))
    return 1/(1+math.exp(-z)) if z>=0 else math.exp(z)/(1+math.exp(z))

def json_write(path,obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')

def run(data_dir, pilot_source, oof_v2_source, full_oof_dir, freeze_dir, output_dir):
    data_dir,pilot_source,oof_v2_source,full_oof_dir,freeze_dir,output_dir=map(lambda p:Path(p).resolve(),(data_dir,pilot_source,oof_v2_source,full_oof_dir,freeze_dir,output_dir))
    if output_dir.exists():raise ValueError('FAIL_CLOSED: output exists, refusing overwrite')
    if output_dir==data_dir or data_dir in output_dir.parents:raise ValueError('FAIL_CLOSED: output must be outside PTB-XL root')
    check_hashes(freeze_dir,FREEZE); check_hashes(full_oof_dir,OOF)
    frozen=json.loads((freeze_dir/'protocol.json').read_text(encoding='utf-8'))
    manifest=json.loads((freeze_dir/'freeze_manifest.json').read_text(encoding='utf-8'))
    if frozen.get('status')!='DEVELOPMENT_PROTOCOL_AND_EVIDENCE_FROZEN_HOLDOUT_NOT_AUTHORIZED':raise ValueError('FAIL_CLOSED: freeze status changed')
    for f in ('protocol.json','evidence_index.json'):
        if manifest.get('files_sha256',{}).get(f,'').upper()!=FREEZE[f]:raise ValueError('FAIL_CLOSED: inner freeze link mismatch')
    train=load_checked('_medai_final_train_locked',pilot_source/'ptbxl_pilot_train.py',TRAIN_HASH)
    v2=load_checked('_medai_final_oof_locked',oof_v2_source/'ptbxl_patient_oof_v2.py',OOF_V2_HASH)
    # Independent row loading: select folds 1-8 only, never use fold 9/10 outcome fields.
    dev,fold_counts,codes=v2.load_metadata(data_dir)
    if len(dev)!=17418 or len(codes)!=14 or sum(fold_counts[x] for x in range(1,9))!=17418: raise ValueError('FAIL_CLOSED: incorrect development inventory')
    import csv
    rows=[]
    with (data_dir/'ptbxl_database.csv').open(encoding='utf-8-sig',newline='') as f:
        for raw in csv.DictReader(f):
            fold=int(raw['strat_fold'])
            if fold not in range(1,9):continue
            ecg=v2.ecg_id(raw['ecg_id']); pid=v2.patient_id(raw['patient_id'])
            if ecg not in dev or dev[ecg] != (pid,fold,dev[ecg][2]): raise ValueError('FAIL_CLOSED: metadata disagreement')
            path=raw['filename_lr']
            if not v2.PATH.fullmatch(path):raise ValueError('FAIL_CLOSED: invalid waveform locator')
            rows.append((ecg,pid,fold,dev[ecg][2],path))
    if len(rows)!=17418 or len({r[0] for r in rows})!=17418 or len({r[1] for r in rows})!=15023:raise ValueError('FAIL_CLOSED: development count mismatch')
    patient_fold={}
    for _,p,f,_,_ in rows:
        if p in patient_fold and patient_fold[p]!=f:raise ValueError('FAIL_CLOSED: patient fold leakage')
        patient_fold[p]=f
    if train.MODEL_CONFIGS!=(('baseline',1.0),('candidate',0.1)) or train.MODEL_EPOCHS!=200 or train.MODEL_LEARNING_RATE!=0.25:raise ValueError('FAIL_CLOSED: training config mismatch')
    official=train.official_hashes(data_dir/'SHA256SUMS.txt')
    features=[]; labels=[]
    for i,(_,_,_,label,loc) in enumerate(rows,1):
        train.verify_record_files(data_dir,loc,official)
        x=train.read_features(data_dir,loc)
        if len(x)!=72 or not all(math.isfinite(t) for t in x):raise ValueError('FAIL_CLOSED: invalid extracted features')
        features.append(x);labels.append(label)
        if i%1000==0 or i==len(rows):print(f'FEATURES VERIFIED: {i}/17418',flush=True)
    if set(labels)!={0,1}:raise ValueError('FAIL_CLOSED: both classes required')
    print('TRAINING FINAL CANDIDATE ON FOLDS 1-8',flush=True)
    model=train.train_logistic(features,labels,0.1,epochs=200,lr=0.25)
    model['decision_threshold']=THRESHOLD
    validate_model(model)
    # Cross-check reference inference vs independent inference on 10 deterministic training rows.
    for x in features[:10]:
        if abs(model_score(model,x)-train.predict(model,x))>1e-12:raise ValueError('FAIL_CLOSED: inference divergence')
    output_dir.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.medai_final_model_staging_',dir=output_dir.parent))
    try:
        json_write(stage/'candidate_model.json',model)
        model2=json.loads((stage/'candidate_model.json').read_text(encoding='utf-8'))
        validate_model(model2)
        for x in features[:10]:
            if abs(model_score(model,x)-model_score(model2,x))>0:raise ValueError('FAIL_CLOSED: serialization changed predictions')
        report={'schema_version':'medai-final-model-freeze-v1','status':'FINAL_CANDIDATE_TRAINED_AND_LOCALLY_FROZEN_HOLDOUT_NOT_AUTHORIZED',
                'intended_use':'Research-only PTB-XL MI diagnostic superclass, NOT acute MI diagnosis',
                'training_records':len(rows),'training_patients':len(patient_fold),'training_folds':list(range(1,9)),
                'positive_records':sum(labels),'negative_records':len(labels)-sum(labels),
                'candidate_l2':0.1,'epochs':200,'learning_rate':0.25,'threshold':THRESHOLD,
                'model_selection':'Development-selected after viewing folds 1-8 OOF results',
                'model_sha256':digest(stage/'candidate_model.json'),
                'locked_freeze_sha256':FREEZE,'locked_oof_sha256':OOF,
                'source_sha256':{'training_module':TRAIN_HASH,'patient_oof_module':OOF_V2_HASH,'this_runner':digest(Path(__file__))},
                'fold9_fold10_labels_signals_read':False,
                'limitations':['No independent holdout results','No clinical safety or regulatory certification','Inference must validate exact feature pipeline and model artifact before predictions','Model training is reproducible under fixed software/data runtime, not proven cross-platform']}
        json_write(stage/'final_model_report.json',report)
        json_write(stage/'final_model_manifest.json',{'files_sha256':{'candidate_model.json':digest(stage/'candidate_model.json'), 'final_model_report.json':digest(stage/'final_model_report.json')},'status':'LOCAL_INTEGRITY_MANIFEST_NOT_HOLDOUT_AUTHORIZATION'})
        if output_dir.exists():raise ValueError('FAIL_CLOSED: target path appeared')
        stage.rename(output_dir)
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True);raise
    print('STATUS: FINAL_CANDIDATE_TRAINED_AND_LOCALLY_FROZEN_HOLDOUT_NOT_AUTHORIZED')
    print('MODEL SHA256:',digest(output_dir/'candidate_model.json'))
    print('MANIFEST SHA256:',digest(output_dir/'final_model_manifest.json'))
    print('FOLD 9/10 LABELS/SIGNALS: NOT READ')
    print('OUTPUT:',output_dir)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('data-dir','pilot-source','oof-v2-source','full-oof-dir','freeze-dir','output-dir'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    try:run(a.data_dir,a.pilot_source,a.oof_v2_source,a.full_oof_dir,a.freeze_dir,a.output_dir)
    except (ValueError,OSError,KeyError,TypeError,ImportError,json.JSONDecodeError) as e:p.exit(2,'FAIL_CLOSED: '+str(e)+'\n')

if __name__=='__main__':main()
