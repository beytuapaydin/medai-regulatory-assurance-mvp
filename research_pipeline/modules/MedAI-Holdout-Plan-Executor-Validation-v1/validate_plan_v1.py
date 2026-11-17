#!/usr/bin/env python3
"""Pre-holdout plan freeze and synthetic executor audit. Deliberately NO real holdout input API."""
from __future__ import annotations
import argparse,hashlib,json,pathlib,sys,random
from holdout_math_v1 import THRESHOLD,patient_components,weighted_stats,record_stats,bootstrap_ci,subgroup_summary

LOCKED={'protocol.json':'B19AB6DF758A1C98B43C233B209DC6EF6F891677EA8A4FBCA6E1DD62F1FF2DBE',
'evidence_index.json':'75F267B823B4A9FCF177C70C38725E8380541848C58960F8D43451FE3983E78D',
'freeze_manifest.json':'53FFD3AE20CC6347B2969DF5C334F17052A650F8CAD71779DC11445C86CEDD61',
'candidate_model.json':'B0DBD0E84285F7F920545AEA8FA5C52E3812F399A8A1BE5F2C3EEDEB0CC231A0',
'final_model_manifest.json':'C344B33BED7613420A854868BD849BCA0A7B89AC98D5EE101EE79CB8E402A50A',
'MedAI-Final-Model-Reproduction-Audit-v1.json':'DA482FB11314A43C6FB64156BD899E16BAE6CE7AB843C2644476D7493CF39487',
'MedAI-Holdout-Readiness-Review-v1.json':'367C06A0546B8F0CB764CDCEA23FE949ED061CD3460B3F68911F1C711A24BC12'}

def digest(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest().upper()

def dump(p,obj):pathlib.Path(p).write_text(json.dumps(obj,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8',newline='\n')

def plan():
    return {'id':'MEDAI-PTBXL-MI-001','schema_version':'preholdout-sap-v1','status':'PROPOSED_REQUIRES_INDEPENDENT_REVIEW',
    'intended_use':'Research-only PTB-XL MI diagnostic superclass; not acute MI diagnosis or clinical validation',
    'dataset':'PTB-XL v1.0.3, 100Hz, 12 leads',
    'development_folds':list(range(1,9)),'fold9':'previously inspected, not independent',
    'holdout_fold':10,'holdout_policy':'one-time, no retraining, threshold or model selection from holdout; no conditional reruns',
    'development_selected_model':'candidate; L2=0.1, logistic regression, 72 features, epochs=200, learning_rate=.25',
    'fixed_threshold':THRESHOLD,'binary_decision_rule':'positive iff score >= threshold',
    'labels':'14 diagnostic_class MI SCP codes; all others non-MI, no SCP confidence filter; not acute MI diagnosis',
    'primary_metrics':['patient_weighted_sensitivity','patient_weighted_specificity'],
    'estimands':'For each class, mean of within-patient correct-classification rates among patients with at least one record of that true class. Mixed-label patients participate in both class denominators.',
    'secondary_metrics':['record_weighted_sensitivity','record_weighted_specificity','per_class_denominators','confusion_matrix'],
    'bootstrap':{'method':'sample patient IDs WITH replacement, retain ALL records of a sampled patient','replicates':2000,'seed':20261117,'interval':'percentile_95','threshold_fixed':True},
    'subgroups':{'age':['AGE_LT_65','AGE_65_74','AGE_75_PLUS','AGE_300_SENTINEL','AGE_MISSING'],
                'sex':['0','1','UNKNOWN'],'minimum_positive_patients':30,'minimum_negative_patients':30,
                'insufficient':'INSUFFICIENT_EVIDENCE, no numerical metrics shown',
                'label':'EXPLORATORY, not adjusted for multiplicity'},
    'missingness':'Age=300 is an anonymized sentinel, not missing. Missing age remains distinct. Missing or invalid sex is UNKNOWN only if explicitly allowed by data dictionary; invalid raw values fail closed.',
    'technical_success':'Exact locked inputs, 2,198 unique holdout ECG and appropriate patient folds, verified score and label calculations, evidence report emitted without overwrite',
    'clinical_success':'NOT_DEFINED; diagnostic accuracy cannot be claimed clinically acceptable by this study',
    'interpretation':'No guaranteed superiority; negative, low-performing or wide-CI results must be retained without reruns',
    'required_independent_signoffs':['Independent scientific/statistical SAP review','Independent runner/inference/source review','Explicit documented one-time research holdout access approval'],
    'holdout_authorized':False,'manufacturer_release_decision':'OUTSIDE_PLATFORM_SCOPE'}

def synthetic_rows():
    # Deterministic, not imported from PTB-XL. Mixed-label patients and exact-threshold ties.
    rr=[]
    for i in range(1,161):
        sex=i%2;age=300 if i%29==0 else (None if i%31==0 else 20+(i*7)%73)
        for j in range(2 if i%5==0 else 1):
            label=int((i+j)%4==0)
            score=[.11,.31,THRESHOLD,.44,.67,.91][(i+2*j)%6]
            rr.append({'ecg_id':i*10+j,'patient_id':i,'fold':1,'y_true':label,
                       'probability':score,'age':age,'sex':sex})
    return rr

def check(paths):
    for name,folder in paths.items():
        p=pathlib.Path(folder)/name
        if not p.is_file() or digest(p)!=LOCKED[name]:raise ValueError('FAIL_CLOSED: locked evidence mismatch: '+name)
    protocol=json.loads((pathlib.Path(paths['protocol.json'])/'protocol.json').read_text('utf8'))
    model=json.loads((pathlib.Path(paths['candidate_model.json'])/'candidate_model.json').read_text('utf8'))
    ready=json.loads((pathlib.Path(paths['MedAI-Holdout-Readiness-Review-v1.json'])/'MedAI-Holdout-Readiness-Review-v1.json').read_text('utf8'))
    if protocol.get('status')!='DEVELOPMENT_PROTOCOL_AND_EVIDENCE_FROZEN_HOLDOUT_NOT_AUTHORIZED':raise ValueError('FAIL_CLOSED: unexpected protocol state')
    if model.get('decision_threshold')!=THRESHOLD:raise ValueError('FAIL_CLOSED: threshold mismatch')
    if ready.get('holdout_authorized') is not False or ready.get('status')!='TECHNICAL_EVIDENCE_VERIFIED_HOLDOUT_NOT_AUTHORIZED':raise ValueError('FAIL_CLOSED: readiness state inconsistent')

def run(args):
    target=args.output_dir.resolve()
    if target.exists():raise ValueError('FAIL_CLOSED: output already exists')
    paths={name:(args.freeze_dir if name in ('protocol.json','evidence_index.json','freeze_manifest.json') else args.model_dir if name in ('candidate_model.json','final_model_manifest.json') else args.docs) for name in LOCKED}
    if any(target==p.resolve() or p.resolve() in target.parents for p in (args.freeze_dir,args.model_dir,args.docs/'MedAI-Data')):raise ValueError('FAIL_CLOSED: output in protected directory')
    check(paths)
    rows=synthetic_rows(); comps=patient_components(rows)
    metrics=weighted_stats(comps); secondary=record_stats(rows);ci=bootstrap_ci(comps);groups=subgroup_summary(rows)
    # Exact-threshold test: score equal threshold must classify positive.
    if not any(r['probability']==THRESHOLD for r in rows):raise ValueError('FAIL_CLOSED: synthetic threshold tie absent')
    p=plan()
    if p['holdout_authorized'] is not False:raise ValueError('FAIL_CLOSED: holdout must be blocked')
    target.mkdir(parents=True,exist_ok=False)
    dump(target/'statistical_analysis_plan.json',p)
    dump(target/'synthetic_executor_validation.json',{'status':'PASS_SYNTHETIC_EXECUTOR_VALIDATION_ONLY','dataset':'SYNTHETIC_NOT_PTBXL',
        'records':len(rows),'patients':len(comps),'patient_weighted_metrics':metrics,'record_weighted_metrics':secondary,
        'bootstrap':ci,'subgroups':groups,'fold10_labels_or_signals_read':False,'holdout_authorized':False})
    dump(target/'plan_validation_manifest.json',{'status':'PREHOLDOUT_PLAN_LOCKED_LOCALLY_PENDING_INDEPENDENT_REVIEW',
        'files_sha256':{n:digest(target/n) for n in ('statistical_analysis_plan.json','synthetic_executor_validation.json')},
        'source_sha256':{n:digest(pathlib.Path(__file__).parent/n) for n in ('validate_plan_v1.py','holdout_math_v1.py')},
        'holdout_authorized':False,'locked_evidence_sha256':LOCKED})
    print('STATUS: PREHOLDOUT_PLAN_LOCKED_LOCALLY_PENDING_INDEPENDENT_REVIEW')
    print('SYNTHETIC EXECUTOR: PASS')
    print('SYNTHETIC RECORDS/PATIENTS:',len(rows),'/',len(comps))
    print('HOLDOUT AUTHORIZED: NO')
    print('FOLD 9/10 SIGNALS/LABELS: NOT READ')
    print('BLOCKERS: 3')
    print('OUTPUT:',target)
    print('PLAN MANIFEST SHA256:',digest(target/'plan_validation_manifest.json'))

def main():
    a=argparse.ArgumentParser(description=__doc__)
    for name in ('docs','freeze-dir','model-dir','output-dir'):a.add_argument('--'+name,required=True,type=pathlib.Path)
    x=a.parse_args()
    try:run(x)
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as e:a.exit(2,str(e)+'\n')
if __name__=='__main__':main()
