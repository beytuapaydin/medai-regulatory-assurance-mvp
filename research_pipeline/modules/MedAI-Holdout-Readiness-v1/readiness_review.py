#!/usr/bin/env python3
"""Read-only, fail-closed local pre-holdout readiness review. Never reads PTB-XL fold 10."""
import argparse, hashlib, json, math, os, pathlib, sys

FREEZE = {
'protocol.json':'B19AB6DF758A1C98B43C233B209DC6EF6F891677EA8A4FBCA6E1DD62F1FF2DBE',
'evidence_index.json':'75F267B823B4A9FCF177C70C38725E8380541848C58960F8D43451FE3983E78D',
'freeze_manifest.json':'53FFD3AE20CC6347B2969DF5C334F17052A650F8CAD71779DC11445C86CEDD61'}
MODEL = {'candidate_model.json':'B0DBD0E84285F7F920545AEA8FA5C52E3812F399A8A1BE5F2C3EEDEB0CC231A0',
'final_model_manifest.json':'C344B33BED7613420A854868BD849BCA0A7B89AC98D5EE101EE79CB8E402A50A'}
REPLAY='DA482FB11314A43C6FB64156BD899E16BAE6CE7AB843C2644476D7493CF39487'
OOF={'training_oof_predictions.csv':'ED83A106581E43275803D2E343F513D5BFC2B80A50E33584651816AE88A71E38',
'full_oof_report.json':'E6F4C9AEB01ED3C8469181A36CE97BA22328BA2E09845BA909077B390FDC0E6D',
'manifest.json':'CE779FC76ECFC203FEF105761AAF64A619A1A534F185A86BFDEB26DDFDD237CE'}
THRESHOLD=0.3795860831201651

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest().upper()

def verify(d, mapping):
    result={}
    for name,expected in mapping.items():
        p=pathlib.Path(d)/name
        if not p.is_file() or sha(p)!=expected:
            raise ValueError(f'Locked evidence hash mismatch: {name}')
        result[name]={'sha256':expected,'bytes':p.stat().st_size}
    return result

def review(docs, freeze_dir, model_dir, oof_dir):
    files={}
    files['protocol']=verify(freeze_dir,FREEZE)
    files['model']=verify(model_dir,MODEL)
    files['full_oof']=verify(oof_dir,OOF)
    files['repro']=verify(docs, {'MedAI-Final-Model-Reproduction-Audit-v1.json': REPLAY})
    protocol=json.loads((pathlib.Path(freeze_dir)/'protocol.json').read_text(encoding='utf-8'))
    pmanifest=json.loads((pathlib.Path(freeze_dir)/'freeze_manifest.json').read_text(encoding='utf-8'))
    model=json.loads((pathlib.Path(model_dir)/'candidate_model.json').read_text(encoding='utf-8'))
    mmanifest=json.loads((pathlib.Path(model_dir)/'final_model_manifest.json').read_text(encoding='utf-8'))
    repro=json.loads((pathlib.Path(docs)/'MedAI-Final-Model-Reproduction-Audit-v1.json').read_text(encoding='utf-8'))
    if protocol.get('status')!='DEVELOPMENT_PROTOCOL_AND_EVIDENCE_FROZEN_HOLDOUT_NOT_AUTHORIZED':raise ValueError('Unexpected protocol status')
    if protocol.get('development_folds')!=list(range(1,9)) or 'Previously inspected' not in protocol.get('fold9',''):raise ValueError('Unexpected development split')
    if pmanifest.get('status')!='LOCAL_PROTOCOL_FREEZE_ONLY_NOT_HOLDOUT_AUTHORIZATION':raise ValueError('Unexpected protocol manifest status')
    for n in ('protocol.json','evidence_index.json'):
        if str(pmanifest.get('files_sha256',{}).get(n,'')).upper()!=FREEZE[n]:raise ValueError('Protocol manifest link mismatch: '+n)
    for n in ('candidate_model.json','final_model_report.json'):
        actual=sha(pathlib.Path(model_dir)/n)
        if str(mmanifest.get('files_sha256',{}).get(n,'')).upper()!=actual:raise ValueError('Model manifest link mismatch: '+n)
    if mmanifest.get('status')!='LOCAL_INTEGRITY_MANIFEST_NOT_HOLDOUT_AUTHORIZATION':raise ValueError('Unexpected model manifest status')
    if model.get('type')!='l2_logistic_regression' or model.get('l2_penalty')!=.1 or model.get('epochs')!=200 or model.get('learning_rate')!=.25 or model.get('decision_threshold')!=THRESHOLD:raise ValueError('Model configuration mismatch')
    if any(not isinstance(model.get(k),list) or len(model[k])!=72 or any(type(v) not in (int,float) or not math.isfinite(v) for v in model[k]) for k in ('weights','feature_mean','feature_std')):raise ValueError('Invalid model dimensions')
    if any(v<=0 for v in model['feature_std']) or not math.isfinite(model.get('intercept',float('nan'))):raise ValueError('Invalid scaler/intercept')
    if protocol.get('models',{}).get('candidate',{}).get('threshold')!=THRESHOLD:raise ValueError('Protocol threshold mismatch')
    if protocol.get('models',{}).get('candidate',{}).get('selection') is None:raise ValueError('Development-selection disclosure missing')
    if not isinstance(protocol.get('holdout_prerequisites'),list) or len(protocol['holdout_prerequisites'])<4:raise ValueError('Missing holdout preconditions')
    if not isinstance(repro,dict) or not any('REPRODUCED_FINAL_MODEL' in str(v) for v in repro.values() if isinstance(v,str)):raise ValueError('Final replay status not recognized')
    # This does not authorize use of fold 10. Review remains intentionally blocked.
    return {
        'schema_version':'medai-holdout-readiness-review-v1',
        'status':'TECHNICAL_EVIDENCE_VERIFIED_HOLDOUT_NOT_AUTHORIZED',
        'protocol_id':'MEDAI-PTBXL-MI-001',
        'research_only':True,
        'holdout_authorized':False,
        'fold_9_10_signals_labels_read':False,
        'frozen_candidate_threshold':THRESHOLD,
        'training_folds':list(range(1,9)),
        'frozen_evidence':files,
        'proposed_analysis_plan_not_yet_approved':{
            'target':'PTB-XL MI diagnostic superclass (not acute MI)',
            'one_time_holdout':'Fold 10 only; no threshold optimization, retraining, model selection, or conditional reruns',
            'primary_metrics':['patient-weighted sensitivity','patient-weighted specificity'],
            'uncertainty':'patient-cluster bootstrap; resample whole patients, mixed-label patients remain intact; 2000 replicates, fixed threshold, percentile 95% intervals',
            'secondary_metrics':['record-weighted sensitivity','record-weighted specificity','patient and record counts','missingness','exploratory demographic subgroup denominators'],
            'exploratory_subgroups':'Age including 300 sentinel and missing; sex; predeclare exact bins and minimum denominators before evaluation',
            'failure_reporting':'Do not discard unfavorable findings or modify threshold; insufficient subgroup evidence explicitly reported',
            'no_clinical_acceptance_claim':True
        },
        'blocking_requirements':['Independent review and explicit approval of the locked statistical analysis plan including subgroup definitions and decision rules',
            'Independent inspection/test of holdout evaluation runner and feature/inference parity before any holdout access',
            'Explicit documented one-time research holdout authorization following readiness review'],
        'manufacturer_release_decision':'OUTSIDE_PLATFORM_SCOPE'
    }

def main():
    ap=argparse.ArgumentParser()
    for s in ('docs','freeze-dir','model-dir','oof-dir','output'):ap.add_argument('--'+s,required=True,type=pathlib.Path)
    a=ap.parse_args()
    try:
        if a.output.exists():raise ValueError('Refusing overwrite of evidence')
        if a.output.resolve().is_relative_to(a.oof_dir.resolve()) or a.output.resolve().is_relative_to(a.model_dir.resolve()) or a.output.resolve().is_relative_to(a.freeze_dir.resolve()):raise ValueError('Output may not be inside frozen evidence directories')
        result=review(a.docs,a.freeze_dir,a.model_dir,a.oof_dir)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
        print('STATUS:',result['status'])
        print('HOLDOUT AUTHORIZED: NO')
        print('BLOCKERS:',len(result['blocking_requirements']))
        print('FOLD 9/10: SIGNALS/LABELS NOT READ')
        print('REPORT:',a.output)
        print('SHA256:',sha(a.output))
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as e:
        print('FAIL_CLOSED:',e,file=sys.stderr);sys.exit(2)
if __name__=='__main__':main()
