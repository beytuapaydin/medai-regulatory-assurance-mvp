#!/usr/bin/env python3
"""Read-only technical evidence verification and explicit NO-GO review packet; no holdout capability."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

EXPECTED = {
  'protocol.json': 'B19AB6DF758A1C98B43C233B209DC6EF6F891677EA8A4FBCA6E1DD62F1FF2DBE',
  'evidence_index.json': '75F267B823B4A9FCF177C70C38725E8380541848C58960F8D43451FE3983E78D',
  'freeze_manifest.json': '53FFD3AE20CC6347B2969DF5C334F17052A650F8CAD71779DC11445C86CEDD61',
  'candidate_model.json': 'B0DBD0E84285F7F920545AEA8FA5C52E3812F399A8A1BE5F2C3EEDEB0CC231A0',
  'final_model_manifest.json': 'C344B33BED7613420A854868BD849BCA0A7B89AC98D5EE101EE79CB8E402A50A',
  'MedAI-Final-Model-Reproduction-Audit-v1.json': 'DA482FB11314A43C6FB64156BD899E16BAE6CE7AB843C2644476D7493CF39487',
  'MedAI-Holdout-Readiness-Review-v1.json': '367C06A0546B8F0CB764CDCEA23FE949ED061CD3460B3F68911F1C711A24BC12',
  'plan_validation_manifest.json': '84862632310C1634CDC39BE82A43C260E7331E4CC9DA51757A7420B6A4DBCF27',
  'MedAI-Holdout-Integration-Review-v1.json': '0D36083C4D7FB8B1A87F6F2E19D3E8F228E1E09585807E28763D42929EC8E763',
}
THRESHOLD=0.3795860831201651

class AuditError(ValueError): pass

def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as src:
        for chunk in iter(lambda:src.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest().upper()

def read_json(path:Path):
    with path.open(encoding='utf-8') as fp:return json.load(fp)

def verify_one(path:Path,expected:str):
    if not path.is_file():raise AuditError('Missing evidence: '+path.name)
    observed=digest(path)
    if observed!=expected:raise AuditError(f'SHA256 mismatch: {path.name} actual={observed} expected={expected}')
    return {'name':path.name,'sha256':observed,'bytes':path.stat().st_size}

def paths(args):
    return {
      'protocol.json':args.freeze_dir/'protocol.json',
      'evidence_index.json':args.freeze_dir/'evidence_index.json',
      'freeze_manifest.json':args.freeze_dir/'freeze_manifest.json',
      'candidate_model.json':args.model_dir/'candidate_model.json',
      'final_model_manifest.json':args.model_dir/'final_model_manifest.json',
      'MedAI-Final-Model-Reproduction-Audit-v1.json':args.docs/'MedAI-Final-Model-Reproduction-Audit-v1.json',
      'MedAI-Holdout-Readiness-Review-v1.json':args.docs/'MedAI-Holdout-Readiness-Review-v1.json',
      'plan_validation_manifest.json':args.plan_dir/'plan_validation_manifest.json',
      'MedAI-Holdout-Integration-Review-v1.json':args.docs/'MedAI-Holdout-Integration-Review-v1.json',
    }

def review(args):
    files=paths(args)
    observed=[verify_one(files[name],sha) for name,sha in EXPECTED.items()]
    protocol=read_json(files['protocol.json'])
    model=read_json(files['candidate_model.json'])
    manifest=read_json(files['final_model_manifest.json'])
    replay=read_json(files['MedAI-Final-Model-Reproduction-Audit-v1.json'])
    ready=read_json(files['MedAI-Holdout-Readiness-Review-v1.json'])
    plan=read_json(files['plan_validation_manifest.json'])
    integ=read_json(files['MedAI-Holdout-Integration-Review-v1.json'])
    if protocol.get('status')!='DEVELOPMENT_PROTOCOL_AND_EVIDENCE_FROZEN_HOLDOUT_NOT_AUTHORIZED':raise AuditError('Unexpected frozen protocol state')
    if model.get('decision_threshold')!=THRESHOLD:raise AuditError('Threshold drift')
    if len(model.get('weights',[]))!=72:raise AuditError('Feature dimension mismatch')
    if manifest.get('status')!='LOCAL_INTEGRITY_MANIFEST_NOT_HOLDOUT_AUTHORIZATION':raise AuditError('Model manifest status mismatch')
    if replay.get('status')!='REPRODUCED_FINAL_MODEL_WITHIN_TOLERANCE_HOLDOUT_NOT_AUTHORIZED':raise AuditError('Final model replay not verified')
    if ready.get('status')!='TECHNICAL_EVIDENCE_VERIFIED_HOLDOUT_NOT_AUTHORIZED':raise AuditError('Readiness is not verified')
    if plan.get('status')!='PREHOLDOUT_PLAN_LOCKED_LOCALLY_PENDING_INDEPENDENT_REVIEW':raise AuditError('Plan is not locally locked')
    if integ.get('status')!='PASS_SYNTHETIC_WFDB_INTEGRATION_HOLDOUT_NOT_AUTHORIZED':raise AuditError('Integration is not verified')
    for name,obj in [('ready',ready),('plan',plan),('integration',integ)]:
        if obj.get('holdout_authorized') is not False:raise AuditError(name+' already authorizes holdout unexpectedly')
    for key in ('model_max_absolute_delta','inference_max_absolute_delta'):
        if key in replay and replay[key]!=0:raise AuditError('Replay discrepancy: '+key)
    return observed

def write_json_new(path,obj):
    # Exclusive create, no overwrite. File is unlinked on JSON serialization failure.
    data=json.dumps(obj,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
    with path.open('x',encoding='utf-8',newline='\n') as f:f.write(data)

def execute(args):
    target=args.output_dir.resolve()
    if target.exists():raise AuditError('Output directory exists; no overwrite')
    protected=[args.docs.resolve(),args.freeze_dir.resolve(),args.model_dir.resolve(),args.plan_dir.resolve()]
    for protected_dir in protected[1:]:
        if target==protected_dir or protected_dir in target.parents:raise AuditError('Output inside protected evidence')
    checked=review(args)
    doc={
      'schema_version':'medai-gonogo-v1',
      'status':'TECHNICAL_PRECHECK_PASS_INDEPENDENT_REVIEW_PENDING_NO_GO',
      'decision':'NO_GO',
      'holdout_authorized':False,
      'fold10_labels_signals_accessed':False,
      'evidence_files_verified':len(checked),
      'evidence':checked,
      'threshold_fixed':THRESHOLD,
      'model_selection':'Candidate selected on development folds 1-8; not externally validated',
      'review_items':[
        {'id':'SAP_INDEPENDENT_REVIEW','status':'PENDING','reviewer':None,'decision':None,'evidence':None},
        {'id':'RUNNER_INDEPENDENT_REVIEW','status':'PENDING','reviewer':None,'decision':None,'evidence':None},
        {'id':'ONE_TIME_HOLDOUT_APPROVAL','status':'NOT_AUTHORIZED','approver':None,'approval_record':None},
      ],
      'risks':[
        'Same development OOF set used for threshold selection and reported performance',
        'Sensitivity approximately 38.55 percent on OOF; no clinical acceptance demonstrated',
        'Synthetic WFDB integration uses same signal reader as training',
        'No independent human review has been documented',
        'No full real-holdout runner was reviewed or approved',
        'Fold 9 previously inspected; not an independent holdout',
      ],
      'release_scope':'RESEARCH ONLY; NOT medical diagnosis, CE marking, or manufacturer release',
      'next_gate':'Independent signed review; separate, explicit authorization before any Fold 10 access',
    }
    target.mkdir(parents=True,exist_ok=False)
    try:
        decision=target/'go_nogo_decision.json'
        write_json_new(decision,doc)
        manifest={'schema_version':'medai-gonogo-manifest-v1','status':doc['status'],
                  'go_nogo_decision_sha256':digest(decision),
                  'source_sha256':digest(Path(__file__).resolve()),'holdout_authorized':False}
        write_json_new(target/'go_nogo_manifest.json',manifest)
    except Exception:
        for f in target.iterdir():f.unlink()
        target.rmdir()
        raise
    print('STATUS:',doc['status'])
    print('TECHNICAL PRECHECK: PASS')
    print('EVIDENCE HASHES VERIFIED:',len(checked))
    print('INDEPENDENT REVIEW: PENDING')
    print('HOLDOUT AUTHORIZED: NO')
    print('DECISION: NO_GO')
    print('FOLD 9/10 SIGNALS/LABELS: NOT READ')
    print('REPORT:',decision)
    print('DECISION MANIFEST SHA256:',digest(target/'go_nogo_manifest.json'))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('docs','freeze-dir','model-dir','plan-dir','output-dir'):p.add_argument('--'+name,required=True,type=Path)
    args=p.parse_args()
    try:execute(args)
    except (AuditError,OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as e:p.exit(2,'FAIL_CLOSED: '+str(e)+'\n')

if __name__=='__main__':main()
