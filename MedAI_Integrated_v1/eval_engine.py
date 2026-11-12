"""MedAI v1.1 retrieval evaluation, deliberately conservative about incomplete labels.

Standard library only. UNLABELED and PROVISIONAL are not ground truth.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

RELEVANCE = {'UNLABELED', 'IRRELEVANT', 'TOPICALLY_RELATED', 'DIRECTLY_RELEVANT'}
POLARITY = {'UNLABELED', 'SUPPORTS', 'PARTIAL', 'CONTRADICTS', 'INSUFFICIENT_CONTEXT'}
SUFFICIENCY = {'UNLABELED', 'SUFFICIENT', 'PARTIAL', 'INSUFFICIENT', 'NOT_ASSESSABLE'}
STATUS = {'UNLABELED', 'PROVISIONAL', 'EXPERT_VALIDATED'}


class ValidationError(ValueError):
    pass


def validate_annotations(rows):
    if not isinstance(rows, list) or not rows:
        raise ValidationError('Expected a nonempty JSON array of annotation records')
    errors, seen = [], set()
    counts = Counter()
    by_req = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f'{i}: expected object'); continue
        req, doc = row.get('requirement_id'), row.get('document_id')
        if not isinstance(req, str) or not req or not isinstance(doc, str) or not doc:
            errors.append(f'{i}: missing requirement_id/document_id'); continue
        pair = (req, doc)
        if pair in seen: errors.append(f'{i}: duplicate pair {pair}')
        seen.add(pair)
        for field, allowed in [('relevance', RELEVANCE), ('evidence_polarity', POLARITY), ('sufficiency', SUFFICIENCY), ('annotation_status', STATUS)]:
            if row.get(field) not in allowed:
                errors.append(f'{i}: invalid {field}: {row.get(field)!r}')
        s = row.get('annotation_status')
        if s == 'UNLABELED' and any(row.get(x) != 'UNLABELED' for x in ('relevance','evidence_polarity','sufficiency')):
            errors.append(f'{i}: UNLABELED status but populated labels')
        if s in ('PROVISIONAL','EXPERT_VALIDATED'):
            if any(row.get(x) == 'UNLABELED' for x in ('relevance','evidence_polarity','sufficiency')):
                errors.append(f'{i}: labeled status but incomplete labels')
            if not isinstance(row.get('annotator'),str) or not row['annotator'].strip():
                errors.append(f'{i}: missing annotator')
            if not isinstance(row.get('rationale'),str) or len(row['rationale'].strip()) < 15:
                errors.append(f'{i}: rationale must be at least 15 characters')
        if s == 'EXPERT_VALIDATED' and row.get('annotator') == 'AI_ASSISTED_DRAFT':
            errors.append(f'{i}: AI-assisted draft cannot count as expert validated')
        counts[s] += 1
        by_req.setdefault(req,set()).add(doc)
    if errors: raise ValidationError('\n'.join(errors))
    return {'total_pairs':len(rows), 'unique_pairs':len(seen), 'requirements':len(by_req),
            'status_counts':{s:counts[s] for s in sorted(STATUS)},
            'expert_validated_pairs':counts['EXPERT_VALIDATED'],
            'provisional_pairs':counts['PROVISIONAL'],
            'unlabeled_pairs':counts['UNLABELED']}


def extract_predictions(assessment):
    """Return ordered document IDs per requirement, retaining original rank."""
    predicted = {}
    for req in assessment['requirements']:
        pairs = [(c['document_id'], float(c['retrieval_score'])) for c in req.get('candidates', [])]
        pairs.sort(key=lambda t:-t[1])  # Python stable sort preserves ties
        predicted[req['requirement_id']] = [d for d, score in pairs]
    return predicted


def evaluate(rows, predictions, ks=(1, 3, 5)):
    summary=validate_annotations(rows)
    gold={}
    all_docs={}
    for row in rows:
        req, doc = row['requirement_id'], row['document_id']
        all_docs.setdefault(req,set()).add(doc)
        if row['annotation_status']=='EXPERT_VALIDATED':
            gold.setdefault(req,{})[doc] = row['relevance'] in ('TOPICALLY_RELATED','DIRECTLY_RELEVANT')
    # Evaluate only when every document of a requirement has expert-validated annotation.
    complete=[req for req,docs in all_docs.items() if len(gold.get(req,{}))==len(docs)]
    metrics={}
    for k in ks:
        if not isinstance(k,int) or k<1: raise ValueError('k must be a positive integer')
        relevant=hit=selected=relevant_missed=0
        per_req=[]
        for req in sorted(complete):
            labels=gold[req]
            ranked=predictions.get(req,[])[:k]  # NEVER filter unlabelled first; that changes ranks
            if len(ranked)!=len(set(ranked)) or any(d not in labels for d in ranked):
                raise ValidationError(f'Unknown/duplicate ranked prediction for {req}')
            positives={d for d,v in labels.items() if v}
            h=sum(d in positives for d in ranked)
            relevant += len(positives); hit += h; selected += len(ranked)
            relevant_missed += len(positives)-h
            per_req.append({'requirement_id':req,'hits':h,'relevant':len(positives),'retrieved':len(ranked)})
        metrics[f'k={k}']={'recall_micro':round(hit/relevant,4) if relevant else None,
                         'precision_micro':round(hit/selected,4) if selected else None,
                         'false_negative_rate':round(relevant_missed/relevant,4) if relevant else None,
                         'evaluated_requirements':len(complete),'per_requirement':per_req}
    return {'benchmark_status': 'EVALUABLE' if complete else 'NOT_MEASURED',
            'annotation_summary':summary, 'fully_expert_labeled_requirements':sorted(complete),
            'incomplete_requirements': sorted(set(all_docs)-set(complete)), 'metrics':metrics,
            'limitations':['Only fully expert-validated requirement rows enter performance metrics.',
                           'Synthetic data do not establish generalization to real QMS documentation.',
                           'Document-level relevance metrics are not evidence sufficiency or compliance metrics.']}


def markdown_report(result):
    a=result['annotation_summary']
    lines=['# MedAI Retrieval Evaluation v0.1','',f"**Status:** {result['benchmark_status']}",
           f"**Pairs:** {a['total_pairs']} | Expert-validated: {a['expert_validated_pairs']} | Provisional: {a['provisional_pairs']} | Unlabeled: {a['unlabeled_pairs']}",
           f"**Fully reviewed requirements:** {len(result['fully_expert_labeled_requirements'])}/{a['requirements']}",'',
           '| k | Recall (micro) | Precision (micro) | FNR |', '|---|---:|---:|---:|']
    def fmt(v):return 'NOT MEASURED' if v is None else f'{v:.4f}'
    for k, m in result['metrics'].items():lines.append(f"| {k} | {fmt(m['recall_micro'])} | {fmt(m['precision_micro'])} | {fmt(m['false_negative_rate'])} |")
    lines+=['','## Limitations']+[f'- {x}' for x in result['limitations']]
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--annotations',type=Path,required=True)
    parser.add_argument('--assessment',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('eval_results'))
    args=parser.parse_args()
    rows=json.loads(args.annotations.read_text(encoding='utf-8-sig'))
    assessment=json.loads(args.assessment.read_text(encoding='utf-8-sig'))
    result=evaluate(rows,extract_predictions(assessment))
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'eval_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (args.output/'eval_report.md').write_text(markdown_report(result),encoding='utf-8')
    print('STATUS:',result['benchmark_status'])
    print('EXPERT_VALIDATED:',result['annotation_summary']['expert_validated_pairs'])
    print('FULLY_EVALUABLE_REQUIREMENTS:',len(result['fully_expert_labeled_requirements']))


if __name__=='__main__':main()
