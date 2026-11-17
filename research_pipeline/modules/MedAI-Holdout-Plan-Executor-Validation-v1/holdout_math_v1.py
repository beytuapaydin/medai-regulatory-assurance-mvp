"""Research-only metrics for PRE-HOLDOUT validation. Does not read PTB-XL or waveforms."""
from __future__ import annotations
import math, random
from collections import defaultdict

THRESHOLD=0.3795860831201651

def validate_rows(rows):
    if not isinstance(rows,list) or not rows: raise ValueError('FAIL_CLOSED: no rows')
    seen=set(); folds={}
    for r in rows:
        if not isinstance(r,dict) or set(r)!={'ecg_id','patient_id','fold','y_true','probability','age','sex'}:raise ValueError('FAIL_CLOSED: invalid row schema')
        e,p=r['ecg_id'],r['patient_id']; f=r['fold']
        if type(e) is not int or e<=0 or type(p) is not int or p<=0:raise ValueError('FAIL_CLOSED: invalid identifier')
        if e in seen:raise ValueError('FAIL_CLOSED: repeated ECG')
        seen.add(e)
        if type(f) is not int or f not in range(1,11):raise ValueError('FAIL_CLOSED: invalid fold')
        if p in folds and folds[p]!=f:raise ValueError('FAIL_CLOSED: patient spans multiple folds')
        folds[p]=f
        if type(r['y_true']) is not int or r['y_true'] not in (0,1):raise ValueError('FAIL_CLOSED: invalid truth label')
        prob=r['probability']
        if type(prob) not in (int,float) or not math.isfinite(prob) or not 0<=prob<=1:raise ValueError('FAIL_CLOSED: invalid probability')
        a=r['age'];s=r['sex']
        if a is not None and (type(a) is not int or a<0 or a>300 or (a>120 and a!=300)):raise ValueError('FAIL_CLOSED: invalid age')
        if s is not None and (type(s) is not int or s not in (0,1)):raise ValueError('FAIL_CLOSED: invalid sex')
    return len(folds)

def patient_components(rows,threshold=THRESHOLD):
    validate_rows(rows)
    if threshold!=THRESHOLD: raise ValueError('FAIL_CLOSED: threshold not locked')
    counts=defaultdict(lambda: {'pos_total':0,'pos_correct':0,'neg_total':0,'neg_correct':0})
    for r in rows:
        c=counts[r['patient_id']]; predicted=int(r['probability']>=THRESHOLD)
        if r['y_true']==1:
            c['pos_total']+=1;c['pos_correct']+=predicted
        else:
            c['neg_total']+=1;c['neg_correct']+=1-predicted
    return dict(counts)

def weighted_stats(components):
    if not components:raise ValueError('FAIL_CLOSED: empty components')
    p=[c['pos_correct']/c['pos_total'] for c in components.values() if c['pos_total']]
    n=[c['neg_correct']/c['neg_total'] for c in components.values() if c['neg_total']]
    return {'sensitivity':sum(p)/len(p) if p else None,'specificity':sum(n)/len(n) if n else None,
            'n_sensitivity_patients':len(p),'n_specificity_patients':len(n),'mixed_label_patients':sum(bool(c['pos_total'] and c['neg_total']) for c in components.values())}

def record_stats(rows):
    validate_rows(rows)
    pos=[r for r in rows if r['y_true']==1];neg=[r for r in rows if r['y_true']==0]
    return {'sensitivity':sum(r['probability']>=THRESHOLD for r in pos)/len(pos) if pos else None,
            'specificity':sum(r['probability']<THRESHOLD for r in neg)/len(neg) if neg else None,
            'n_positive_records':len(pos),'n_negative_records':len(neg)}

def bootstrap_ci(components,replicates=2000,seed=20261117):
    if type(replicates) is not int or replicates<100:raise ValueError('FAIL_CLOSED: replicates too few')
    keys=sorted(components)
    if len(keys)<2:raise ValueError('FAIL_CLOSED: too few patients')
    rng=random.Random(seed); sens=[];spec=[]
    # Sample the WHOLE patient once per draw; mixed-label patient remains intact.
    for _ in range(replicates):
        a=[];b=[]
        for _ in keys:
            c=components[keys[rng.randrange(len(keys))]]
            if c['pos_total']:a.append(c['pos_correct']/c['pos_total'])
            if c['neg_total']:b.append(c['neg_correct']/c['neg_total'])
        if not a or not b:raise ValueError('FAIL_CLOSED: degenerate bootstrap resample')
        sens.append(sum(a)/len(a));spec.append(sum(b)/len(b))
    def pct(x,q):
        xs=sorted(x);k=(len(xs)-1)*q;i=int(k);alpha=k-i
        return xs[i]*(1-alpha)+xs[min(i+1,len(xs)-1)]*alpha
    return {'sensitivity_ci95':[pct(sens,.025),pct(sens,.975)],
            'specificity_ci95':[pct(spec,.025),pct(spec,.975)],'replicates':replicates,'seed':seed,
            'method':'patient-cluster paired resampling, fixed threshold; percentile CI'}

def age_bucket(age):
    if age is None:return 'AGE_MISSING'
    if age==300:return 'AGE_300_SENTINEL'
    return 'AGE_LT_65' if age<65 else ('AGE_65_74' if age<75 else 'AGE_75_PLUS')

def subgroup_summary(rows,minimum_class_patients=30):
    validate_rows(rows)
    groups=defaultdict(list)
    for r in rows:
        groups['age:'+age_bucket(r['age'])].append(r)
        groups['sex:'+('UNKNOWN' if r['sex'] is None else str(r['sex']))].append(r)
    result={}
    for group,subset in sorted(groups.items()):
        s=weighted_stats(patient_components(subset))
        enough=s['n_sensitivity_patients']>=minimum_class_patients and s['n_specificity_patients']>=minimum_class_patients
        result[group]={'n_records':len(subset),'n_positive_patients':s['n_sensitivity_patients'],
            'n_negative_patients':s['n_specificity_patients'],
            'status':'EXPLORATORY_DESCRIPTIVE' if enough else 'INSUFFICIENT_EVIDENCE',
            'sensitivity':s['sensitivity'] if enough else None,'specificity':s['specificity'] if enough else None}
    return result
