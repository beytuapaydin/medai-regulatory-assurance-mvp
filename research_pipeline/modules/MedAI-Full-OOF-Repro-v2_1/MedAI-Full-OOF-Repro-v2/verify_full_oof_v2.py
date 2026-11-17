#!/usr/bin/env python3
"""Independent replay of PTB-XL folds 1–8 OOF training; research only.

No fold 9/10 outcomes or signals are read. Does not import the full OOF runner.
No existing artifact is overwritten. All records reconstructed from source data.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import os
from collections import defaultdict

TRAIN_SHA = '9c0f6eeae4a77ff77b361055c1d18cd21143dbf97828efc56f7ba8cbb0cf4c0c'
METADATA_SHA = '7600de9c1b27d181d850b3c6038a35d7c3ddb6bb33b702e3a20252a6859d216b'
SCP_SHA = 'ad05b0b1fcae83bb1230755ad9cfc7c96f303feddc08a4a9ad5bdc9ca63bac8f'
SUMS_SHA = 'b7224b92b341511ec3ceb13dc6652079b2c36a06504bcb49506f157f51dc695d'
EXPECTED_OOF_SHA = 'ed83a106581e43275803d2e343f513d5bfc2b80a50e33584651816ae88a71e38'
EXPECTED_REPORT_SHA = 'e6f4c9aeb01ed3c8469181a36ce97ba22328ba2e09845ba909077b390fdc0e6d'
EXPECTED_MANIFEST_SHA = 'ce779fc76ecfc203fef105761aaf64a619a1a534f185a86bfdeb26ddfdd237ce'
EXPECTED_AUDIT_SHA = '52c9197d1e827e0367a15871aa6f4500456b8126d34144ceb12a29ba7f081141'
EXPECTED_ROWS = 17418
EXPECTED_PATIENTS = 15023
ALLOWED = set(range(1,9))

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def fail(message):
    raise ValueError(message)

def canonical_id(value):
    s=str(value).strip()
    if s.endswith('.0'):
        s=s[:-2]
    if not s.isdigit() or int(s)<1:
        fail('Invalid patient or ECG identifier')
    return str(int(s))

def load_training(pilot):
    source=pilot/'ptbxl_pilot_train.py'
    if sha(source)!=TRAIN_SHA:
        fail('Training source SHA-256 mismatch')
    spec=importlib.util.spec_from_file_location('_repro_locked_train', source)
    if not spec or not spec.loader:
        fail('Cannot load original training source')
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if (m.MODEL_CONFIGS != (('baseline',1.0),('candidate',.1)) or
        m.MODEL_EPOCHS!=200 or m.MODEL_LEARNING_RATE!=.25):
        fail('Training hyperparameters changed')
    return m

def read_expected(oofdir, expected_oof_hash=EXPECTED_OOF_SHA):
    names={'training_oof_predictions.csv':expected_oof_hash,
           'full_oof_report.json':EXPECTED_REPORT_SHA,
           'manifest.json':EXPECTED_MANIFEST_SHA}
    for name,expected in names.items():
        if sha(oofdir/name)!=expected:
            fail('Locked evidence SHA-256 mismatch: '+name)
    manifest=json.loads((oofdir/'manifest.json').read_text(encoding='utf-8'))
    report=json.loads((oofdir/'full_oof_report.json').read_text(encoding='utf-8'))
    if report.get('status')!='FULL_DEVELOPMENT_OOF_NOT_INDEPENDENT_VALIDATION':
        fail('Unexpected study status')
    if report.get('records')!=EXPECTED_ROWS or report.get('patients')!=EXPECTED_PATIENTS:
        fail('Unexpected study inventory')
    if str(report.get('oof_predictions_sha256','')).lower()!=expected_oof_hash:
        fail('Report points to different OOF predictions')
    if manifest.get('files_sha256',{}).get('training_oof_predictions.csv','').lower()!=expected_oof_hash:
        fail('Manifest points to different OOF predictions')
    if manifest.get('files_sha256',{}).get('full_oof_report.json','').lower()!=EXPECTED_REPORT_SHA:
        fail('Manifest report SHA mismatch')
    expected={}
    with (oofdir/'training_oof_predictions.csv').open(encoding='utf-8-sig',newline='') as f:
        rdr=csv.DictReader(f)
        if rdr.fieldnames!=['ecg_id','strat_fold','y_true','baseline_probability','candidate_probability']:
            fail('Unexpected prediction CSV schema')
        for row in rdr:
            eid=canonical_id(row['ecg_id'])
            if eid in expected:
                fail('Repeated OOF ECG ID')
            fold=int(row['strat_fold']); label=int(row['y_true'])
            if fold not in ALLOWED or label not in (0,1):
                fail('Non-development fold or invalid OOF label')
            baseline=float(row['baseline_probability']); candidate=float(row['candidate_probability'])
            if not all(math.isfinite(x) and 0<=x<=1 for x in [baseline,candidate]):
                fail('Invalid OOF score')
            expected[eid]=(fold,label,baseline,candidate)
    if len(expected)!=EXPECTED_ROWS:
        fail('Incomplete OOF CSV')
    return expected

def read_development(root, expected):
    for filename,digest in [('ptbxl_database.csv',METADATA_SHA),('scp_statements.csv',SCP_SHA),('SHA256SUMS.txt',SUMS_SHA)]:
        if sha(root/filename)!=digest:
            fail('Dataset metadata SHA mismatch: '+filename)
    mi_codes=set()
    with (root/'scp_statements.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['diagnostic_class']=='MI' and str(row['diagnostic']).strip() in ('1','1.0'):
                mi_codes.add(row[''])
    if len(mi_codes)!=14:
        fail('MI class has changed')
    import ast
    rows=[]; patients={}; used=set()
    with (root/'ptbxl_database.csv').open(encoding='utf-8-sig',newline='') as f:
        for raw in csv.DictReader(f):
            fold=int(raw['strat_fold'])
            if fold not in ALLOWED:
                # Do not read labels, age or waveform paths from folds 9/10.
                continue
            eid=canonical_id(raw['ecg_id']); pid=canonical_id(raw['patient_id'])
            if eid in used or eid not in expected:
                fail('Metadata contains duplicate or unexpected development ECG')
            used.add(eid)
            if patients.setdefault(pid,fold)!=fold:
                fail('Patient leakage across OOF folds')
            codes=ast.literal_eval(raw['scp_codes'])
            if not isinstance(codes,dict):
                fail('Invalid SCP codes')
            label=int(bool(mi_codes.intersection(codes)))
            if (fold,label)!=expected[eid][:2]:
                fail('Metadata fold/MI label differs from OOF predictions')
            rel=raw['filename_lr']
            # All valid PTB-XL LR relative paths look like records100/00000/00001_lr.
            import re
            if not re.fullmatch(r'records100/[0-9]{5}/[0-9]{5}_lr',rel):
                fail('Unsafe or unexpected LR waveform path')
            rows.append({'ecg_id':eid,'patient_id':pid,'fold':fold,'y_true':label,'filename_lr':rel})
    if len(rows)!=EXPECTED_ROWS or len(patients)!=EXPECTED_PATIENTS or set(expected)!=used:
        fail('Incomplete fold 1-8 inventory')
    return rows

def score_replay(rows, features, expected, train, tolerance=1e-12, logger=print):
    if len(rows)!=len(features):
        fail('Record-feature mismatch')
    worst={'baseline':0.0,'candidate':0.0}
    compared={'baseline':0,'candidate':0}
    audits={}
    for name,l2 in train.MODEL_CONFIGS:
        for fold in sorted(ALLOWED):
            training=[i for i,r in enumerate(rows) if r['fold']!=fold]
            holdout=[i for i,r in enumerate(rows) if r['fold']==fold]
            a={rows[i]['patient_id'] for i in training}
            b={rows[i]['patient_id'] for i in holdout}
            if not training or not holdout or (a&b):
                fail('Invalid patient-disjoint split')
            model=train.train_logistic([features[i] for i in training],
                                       [rows[i]['y_true'] for i in training],l2)
            for i in holdout:
                eid=rows[i]['ecg_id']
                value=train.predict(model,features[i])
                reference=expected[eid][2 if name=='baseline' else 3]
                if not math.isfinite(value):
                    fail('Non-finite replay prediction')
                delta=abs(value-reference)
                worst[name]=max(worst[name],delta)
                compared[name]+=1
                if delta>tolerance:
                    fail(f'Prediction mismatch model={name} fold={fold} ecg={eid} delta={delta:.17g} tolerance={tolerance}')
            audits[f'{name}_fold{fold}']={'training_records':len(training),'holdout_records':len(holdout),
                                        'patient_overlap':0}
            logger(f'REPLAY MODEL={name.upper()} FOLD={fold}/8 VERIFIED: {len(holdout)} predictions')
    if compared!={'baseline':EXPECTED_ROWS,'candidate':EXPECTED_ROWS}:
        fail('Replay incomplete')
    return worst,compared,audits

def execute(data_dir,pilot_source,oof_dir,output,tolerance=1e-12):
    data_dir,pilot_source,oof_dir,output=map(lambda p:Path(p).resolve(),(data_dir,pilot_source,oof_dir,output))
    if output.exists():
        fail('Refusing overwrite of existing evidence')
    if output.parent!=oof_dir and (data_dir in output.parents or pilot_source in output.parents or oof_dir in output.parents):
        fail('Do not put output inside dataset, training or existing evidence trees')
    if tolerance<=0 or tolerance>1e-8 or not math.isfinite(tolerance):
        fail('Invalid comparison tolerance')
    expected=read_expected(oof_dir)
    train=load_training(pilot_source)
    rows=read_development(data_dir,expected)
    print(f'LOCKED INPUT: {len(rows)} ECG / {len({r["patient_id"] for r in rows})} patients',flush=True)
    official=train.official_hashes(data_dir/'SHA256SUMS.txt')
    features=[]
    for i,r in enumerate(rows,1):
        train.verify_record_files(data_dir,r['filename_lr'],official)
        v=train.read_features(data_dir,r['filename_lr'])
        if len(v)!=72 or not all(math.isfinite(x) for x in v):
            fail('Invalid extracted features')
        features.append(v)
        if i%2000==0 or i==len(rows):
            print(f'REPLAY FEATURES VERIFIED: {i}/{len(rows)}',flush=True)
    worst,compared,audits=score_replay(rows,features,expected,train,tolerance)
    payload={'schema_version':'medai-full-oof-reproduction-v2','status':'REPRODUCED_WITHIN_TOLERANCE',
             'scope':'Fold 1-8 research development OOF, not independent clinical validation',
             'records':EXPECTED_ROWS,'patients':EXPECTED_PATIENTS,
             'compared_predictions':compared,'max_absolute_delta':worst,
             'comparison_tolerance':tolerance,
             'source_sha256':{'original_training':TRAIN_SHA,'replay_script':sha(Path(__file__).resolve()),
                              'ptbxl_database':METADATA_SHA,'scp_statements':SCP_SHA,'SHA256SUMS':SUMS_SHA},
             'evidence_sha256':{'training_oof_predictions.csv':EXPECTED_OOF_SHA,
                                'full_oof_report.json':EXPECTED_REPORT_SHA,'manifest.json':EXPECTED_MANIFEST_SHA,
                                'prior_paired_statistical_audit':EXPECTED_AUDIT_SHA},
             'fold_audit':audits,
             'fold9_10_labels_or_signals_examined':False,
             'limitations':['Independent execution of the same locked training algorithm, not an independent algorithm.',
                            'No statistical confidence or clinical validity is established by exact replay.',
                            'Threshold optimization and statistical estimands were audited separately.',
                            'Existing research source artifacts remain unchanged.']}
    output.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive create protects existing evidence, including concurrent execution.
    with output.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(payload,f,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)
        f.write('\n')
    print('STATUS: REPRODUCED_WITHIN_TOLERANCE',flush=True)
    for model in ('baseline','candidate'):
        print(f'{model.upper()} MAX ABSOLUTE DELTA: {worst[model]:.17g}',flush=True)
    print('FOLD 9/10: LABELS/SIGNALS NOT READ',flush=True)
    print('REPORT:',output,flush=True)
    return payload

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',type=Path,required=True)
    p.add_argument('--pilot-source',type=Path,required=True)
    p.add_argument('--oof-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--tolerance',type=float,default=1e-12)
    a=p.parse_args()
    try:
        execute(a.data_dir,a.pilot_source,a.oof_dir,a.output,a.tolerance)
    except (ValueError,OSError,KeyError,TypeError,OverflowError,SyntaxError) as ex:
        p.exit(2,f'FAIL_CLOSED: {ex}\n')
if __name__=='__main__':
    main()
