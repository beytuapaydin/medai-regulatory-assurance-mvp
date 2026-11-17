#!/usr/bin/env python3
"""MEDAI-PTBXL-MI-001: research-only final model replay and inference audit.

Reads PTB-XL waveforms ONLY for strat_fold 1..8. Never scores holdout.
"""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import os

EXPECTED = {
    'candidate_model.json': 'B0DBD0E84285F7F920545AEA8FA5C52E3812F399A8A1BE5F2C3EEDEB0CC231A0',
    'final_model_manifest.json': 'C344B33BED7613420A854868BD849BCA0A7B89AC98D5EE101EE79CB8E402A50A',
}
FREEZE = {
    'protocol.json': 'B19AB6DF758A1C98B43C233B209DC6EF6F891677EA8A4FBCA6E1DD62F1FF2DBE',
    'evidence_index.json': '75F267B823B4A9FCF177C70C38725E8380541848C58960F8D43451FE3983E78D',
    'freeze_manifest.json': '53FFD3AE20CC6347B2969DF5C334F17052A650F8CAD71779DC11445C86CEDD61',
}
SOURCE_HASH = '9C0F6EEAE4A77FF77B361055C1D18CD21143DBF97828EFC56F7BA8CBB0CF4C0C'
METADATA_HASH = '7600DE9C1B27D181D850B3C6038A35D7C3DDB6BB33B702E3A20252A6859D216B'
SCP_HASH = 'AD05B0B1FCAE83BB1230755AD9CFC7C96F303FEDDC08A4A9AD5BDC9CA63BAC8F'
SUMS_HASH = 'B7224B92B341511EC3CEB13DC6652079B2C36A06504BCB49506F157F51DC695D'
THRESHOLD = 0.3795860831201651
FIELDS = ('weights', 'feature_mean', 'feature_std')


def fail(msg):
    raise ValueError('FAIL_CLOSED: ' + msg)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest().upper()


def check_pins(folder, pins):
    for name, expected in pins.items():
        p = Path(folder) / name
        if not p.is_file() or sha(p) != expected:
            fail('Locked SHA256 mismatch: ' + name)


def check_model(m):
    if not isinstance(m, dict) or m.get('type') != 'l2_logistic_regression':
        fail('Wrong model type')
    for k, v in [('l2_penalty', .1), ('epochs', 200), ('learning_rate', .25), ('decision_threshold', THRESHOLD)]:
        if type(m.get(k)) not in (float, int) or m[k] != v:
            fail('Wrong model hyperparameter: ' + k)
    for k in FIELDS:
        if not isinstance(m.get(k), list) or len(m[k]) != 72 or not all(type(x) in (float,int) and math.isfinite(x) for x in m[k]):
            fail('Bad model vector: ' + k)
    if any(x <= 0 for x in m['feature_std']) or type(m.get('intercept')) not in (float,int) or not math.isfinite(m['intercept']):
        fail('Bad intercept or scaler')
    if m.get('features_per_lead') != ['mean','std','p05_centered','p95_centered','mean_abs_diff','peak_to_peak']:
        fail('Unexpected feature order')
    if m.get('lead_order') != ['I','II','III','AVR','AVL','AVF','V1','V2','V3','V4','V5','V6']:
        fail('Unexpected lead order')


def compare_models(reproduced, locked, tolerance=0.0):
    check_model(reproduced)
    check_model(locked)
    if not math.isfinite(tolerance) or tolerance < 0 or tolerance > 1e-12:
        fail('Tolerance outside approved bound')
    keys = {'type','l2_penalty','epochs','learning_rate','decision_threshold','features_per_lead','lead_order'}
    for key in keys:
        if reproduced[key] != locked[key]:
            fail('Model definition mismatch: ' + key)
    deltas = {}
    for key in ('intercept', *FIELDS):
        x, y = reproduced[key], locked[key]
        d = abs(x-y) if key == 'intercept' else max(abs(a-b) for a,b in zip(x,y))
        deltas[key] = d
        if not math.isfinite(d) or d > tolerance:
            fail(f'Model replay mismatch in {key}: delta={d}')
    return deltas


def independent_score(m, x):
    check_model(m)
    if not isinstance(x, (list,tuple)) or len(x) != 72 or any(type(v) not in (int,float) or not math.isfinite(v) for v in x):
        fail('Invalid inference feature input')
    z = m['intercept'] + sum(w * (v-mean)/std for w,v,mean,std in zip(m['weights'],x,m['feature_mean'],m['feature_std']))
    return 1/(1+math.exp(-z)) if z >= 0 else math.exp(z)/(1+math.exp(z))


def import_train(path):
    if sha(path) != SOURCE_HASH:
        fail('Training source SHA mismatch')
    spec = importlib.util.spec_from_file_location('_locked_ptbxl_train_model_audit', path)
    if spec is None or spec.loader is None: fail('Cannot load locked training code')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if mod.MODEL_CONFIGS != (('baseline',1.0),('candidate',.1)) or mod.MODEL_EPOCHS != 200 or mod.MODEL_LEARNING_RATE != .25:
        fail('Training source configuration mismatch')
    return mod


def normalize_id(x):
    s = str(x).strip()
    if re.fullmatch(r'[1-9][0-9]*(?:\.0+)?', s) is None:
        fail('Malformed patient or ECG ID')
    return str(int(s.split('.')[0]))


def development_rows(data):
    for file, expected in [('ptbxl_database.csv', METADATA_HASH), ('scp_statements.csv',SCP_HASH), ('SHA256SUMS.txt',SUMS_HASH)]:
        if sha(data/file) != expected: fail('Dataset source hash mismatch: ' + file)
    mi = set()
    with (data/'scp_statements.csv').open('r', encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            if r['diagnostic_class'] == 'MI' and r['diagnostic'] in ('1','1.0'):
                mi.add(r[''])
    if len(mi) != 14: fail('MI superclass label definition changed')
    rows, patients, ecgs = [], {}, set()
    with (data/'ptbxl_database.csv').open('r', encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            fold = int(r['strat_fold'])
            if fold not in range(1,9):
                continue  # Never parse outcome or waveform locator for folds 9/10.
            ecg, patient = normalize_id(r['ecg_id']), normalize_id(r['patient_id'])
            if ecg in ecgs or patient in patients and patients[patient] != fold:
                fail('Duplicate ECG or patient-fold leakage')
            ecgs.add(ecg); patients[patient] = fold
            codes = ast.literal_eval(r['scp_codes'])
            if not isinstance(codes, dict): fail('SCP codes are not a dictionary')
            label = int(bool(mi.intersection(codes)))
            loc = r['filename_lr']
            if re.fullmatch(r'records100/[0-9]{5}/[0-9]{5}_lr', loc) is None:
                fail('Unsafe waveform locator')
            rows.append((ecg, patient, fold, label, loc))
    if len(rows)!=17418 or len(patients)!=15023 or sum(y for _,_,_,y,_ in rows)!=4379:
        fail('Development inventory mismatch')
    return rows


def check_locked_model(model_dir):
    check_pins(model_dir, EXPECTED)
    manifest = json.loads((model_dir/'final_model_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status') != 'LOCAL_INTEGRITY_MANIFEST_NOT_HOLDOUT_AUTHORIZATION':
        fail('Unexpected final model manifest status')
    for name in ('candidate_model.json','final_model_report.json'):
        if manifest.get('files_sha256',{}).get(name,'').upper() != sha(model_dir/name):
            fail('Inner model manifest mismatch: ' + name)
    model = json.loads((model_dir/'candidate_model.json').read_text(encoding='utf-8'))
    check_model(model)
    report = json.loads((model_dir/'final_model_report.json').read_text(encoding='utf-8'))
    if report.get('status') != 'FINAL_CANDIDATE_TRAINED_AND_LOCALLY_FROZEN_HOLDOUT_NOT_AUTHORIZED':
        fail('Unexpected final report status')
    if report.get('model_sha256','').upper() != EXPECTED['candidate_model.json']:
        fail('Final report model link mismatch')
    if report.get('training_records') != 17418 or report.get('training_patients') != 15023 or report.get('training_folds') != list(range(1,9)):
        fail('Final report training split mismatch')
    if report.get('source_sha256',{}).get('training_module','').upper() != SOURCE_HASH:
        fail('Final report source mismatch')
    if report.get('fold9_fold10_labels_signals_read') is not False:
        fail('Holdout access declaration changed')
    return model, manifest


def audit(data_dir, pilot_source, frozen, freeze_dir, output, tolerance):
    for p in (data_dir,pilot_source,frozen,freeze_dir):
        if not p.is_dir(): fail('Missing prerequisite folder: ' + str(p))
    if output.exists(): fail('Output exists; refusing overwrite')
    if output == data_dir or data_dir in output.parents or output == frozen or frozen in output.parents:
        fail('Output path inside protected data or model folder')
    check_pins(freeze_dir,FREEZE)
    protocol = json.loads((freeze_dir/'protocol.json').read_text(encoding='utf-8'))
    if protocol.get('status') != 'DEVELOPMENT_PROTOCOL_AND_EVIDENCE_FROZEN_HOLDOUT_NOT_AUTHORIZED':
        fail('Study protocol has not remained frozen')
    stored, _ = check_locked_model(frozen)
    train = import_train(pilot_source/'ptbxl_pilot_train.py')
    rows = development_rows(data_dir)
    official = train.official_hashes(data_dir/'SHA256SUMS.txt')
    X,y = [],[]
    for i, (_, _, _, label, loc) in enumerate(rows, 1):
        train.verify_record_files(data_dir, loc, official)
        x = train.read_features(data_dir, loc)
        if len(x) != 72 or not all(math.isfinite(v) for v in x): fail('Invalid feature vector')
        X.append(x);y.append(label)
        if i%2000 == 0 or i==len(rows):print(f'REPLAY FEATURES VERIFIED: {i}/17418',flush=True)
    print('REPLAY TRAINING: FINAL CANDIDATE / FOLDS 1-8',flush=True)
    replay = train.train_logistic(X,y,.1,epochs=200,lr=.25)
    replay['decision_threshold']=THRESHOLD
    deltas = compare_models(replay,stored,tolerance)
    # Independent inference checks: all 17,418 development feature vectors.
    score_delta = 0.0; decision_mismatch=0
    for i,x in enumerate(X,1):
        p1 = independent_score(stored,x)
        p2 = train.predict(replay,x)
        d=abs(p1-p2)
        score_delta=max(score_delta,d)
        decision_mismatch += int((p1 >= THRESHOLD)!=(p2 >= THRESHOLD))
        if d > 1e-12:fail(f'Inference mismatch at development row {i}, delta={d}')
    if decision_mismatch:fail('Inference decision mismatch')
    payload = {
        'schema_version':'medai-final-model-reproduction-v1',
        'status':'REPRODUCED_FINAL_MODEL_WITHIN_TOLERANCE_HOLDOUT_NOT_AUTHORIZED',
        'study_id':'MEDAI-PTBXL-MI-001',
        'records':len(rows),'patients':len({r[1] for r in rows}),
        'model_parameters_max_abs_delta':deltas,
        'inference_records_compared':len(X),
        'inference_max_abs_delta':score_delta,
        'classification_disagreements':decision_mismatch,
        'parameter_tolerance':tolerance,'inference_tolerance':1e-12,
        'source_sha256':SOURCE_HASH,
        'locked_final_model_sha256':sha(frozen/'candidate_model.json'),
        'locked_final_model_manifest_sha256':sha(frozen/'final_model_manifest.json'),
        'locked_protocol_manifest_sha256':sha(freeze_dir/'freeze_manifest.json'),
        'audit_source_sha256':sha(Path(__file__)),
        'fold9_10_signals_labels_read':False,
        'limitations':['Uses the same hashed feature extraction/training implementation, not an independent algorithm implementation',
                       'No clinical validation or performance evaluation on independent patients',
                       'No fold 9/10 signal or label access',
                       'Does not authorize holdout evaluation or manufacturer release']
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.medai_final_repro_',suffix='.tmp',dir=str(output.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
            json.dump(payload,f,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)
            f.write('\n');f.flush();os.fsync(f.fileno())
        if output.exists():fail('Output collision detected')
        Path(tmp).rename(output)
    finally:
        if Path(tmp).exists():Path(tmp).unlink()
    print('STATUS:',payload['status'])
    print('MODEL MAX ABSOLUTE DELTA:',max(deltas.values()))
    print('INFERENCE MAX ABSOLUTE DELTA:',score_delta)
    print('CLASSIFICATION DISAGREEMENTS:',decision_mismatch)
    print('FOLD 9/10: LABELS/SIGNALS NOT READ')
    print('REPORT:',output)
    print('REPORT SHA256:',sha(output))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for arg in ('data-dir','pilot-source','model-dir','freeze-dir','output'):
        ap.add_argument('--'+arg,required=True,type=Path)
    ap.add_argument('--tolerance',type=float,default=1e-12)
    args=ap.parse_args()
    try:
        audit(args.data_dir.resolve(),args.pilot_source.resolve(),args.model_dir.resolve(),args.freeze_dir.resolve(),args.output.resolve(),args.tolerance)
    except (ValueError,OSError,KeyError,TypeError,ImportError,OverflowError,json.JSONDecodeError,SyntaxError) as exc:
        ap.exit(2,str(exc)+'\n')

if __name__=='__main__':main()
