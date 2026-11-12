"""Read-only, reviewer-grounded gap triage views. NEVER a regulatory conformity verdict."""
from __future__ import annotations
import csv
import html
import io
import json
from collections import Counter
from pathlib import Path


def follow_up_fields(r: dict, event: dict | None, candidate: dict | None) -> dict:
    """Separate source-observed facts, reviewer opinions, and non-approved suggestions."""
    if not event:
        return {
            'finding': 'No human finding recorded',
            'evidence_gap': 'Not assessed by a reviewer',
            'required_action': 'Human review required' if r.get('candidates') else 'Search additional controlled documents',
            'action_origin': 'SYSTEM_TRIAGE_SUGGESTION_NOT_REVIEWED',
        }
    observation = candidate.get('passage') if candidate else None
    finding = observation or 'No specific candidate passage selected'
    gap = (event.get('gap_or_follow_up') or '').strip()
    if gap:
        action = gap
        origin = 'REVIEWER_ENTERED'
    elif (r['requirement_id'] == 'MDR-10-9-L'
          and event.get('relevance') == 'RELEVANT'
          and event.get('evidence_sufficiency_review') == 'INSUFFICIENT'
          and candidate and 'effectiveness verification records' in observation.lower()):
        action = ('Request approved CAPA procedure and documented effectiveness '
                  'verification records for completed CAPA actions; reviewer must confirm.')
        origin = 'SYSTEM_TRIAGE_SUGGESTION_NOT_REVIEWED'
    else:
        action = 'Reviewer must specify and confirm required follow-up action'
        origin = 'SYSTEM_TRIAGE_SUGGESTION_NOT_REVIEWED'
    return {
        'finding': finding,
        'evidence_gap': gap if gap else ('Reviewer classified evidence as '
             + str(event.get('evidence_sufficiency_review', 'NOT_ASSESSED'))
             + '; no separate gap narrative recorded'),
        'required_action': action,
        'action_origin': origin,
    }


def build_report(assessment: dict, events: list[dict], source_sha: str) -> dict:
    requirements = assessment.get('requirements', [])
    if len(requirements) != 13:
        raise ValueError('Source requirement count mismatch')
    current = {}
    stale_count = 0
    for e in events:
        if e.get('source_assessment_sha256') != source_sha:
            stale_count += 1
            continue
        current[e['requirement_id']] = e
    rows = []
    for r in requirements:
        event = current.get(r['requirement_id'])
        candidates = r.get('candidates', [])
        candidate = None
        # Selected reviewer evidence must still occur in current source candidates.
        if event and event.get('candidate_id'):
            candidate = next((c for c in candidates if c['document_id'] == event['candidate_id']), None)
            if candidate is None or event.get('requirement_sha256') != r['requirement_sha256']:
                event = None
                candidate = None
        if event is None:
            state = 'PENDING_REVIEW' if candidates else 'NO_CANDIDATE_REVIEW_NEEDED'
        elif event.get('relevance') == 'NOT_RELEVANT':
            state = 'CANDIDATE_REJECTED'
        elif event.get('relevance') == 'UNCERTAIN':
            state = 'REVIEW_UNCERTAIN'
        elif event.get('evidence_sufficiency_review') == 'INSUFFICIENT':
            state = 'REVIEWER_REPORTS_INSUFFICIENT'
        elif event.get('evidence_sufficiency_review') == 'PARTIAL':
            state = 'REVIEWER_REPORTS_PARTIAL'
        elif event.get('evidence_sufficiency_review') == 'REVIEWER_CONSIDERS_SUFFICIENT':
            state = 'REVIEWER_CONSIDERS_SUFFICIENT_NOT_APPROVED'
        else:
            state = 'RELEVANT_SUFFICIENCY_NOT_ASSESSED'
        follow_up = follow_up_fields(r, event, candidate)
        rows.append({
            **follow_up,
            'requirement_id': r['requirement_id'],
            'requirement': r['requirement'],
            'requirement_sha256': r['requirement_sha256'],
            'source_review': r.get('source_review','UNKNOWN'),
            'candidate_count': len(candidates),
            'candidate_ids': [c['document_id'] for c in candidates],
            'selected_document': event.get('candidate_id') if event else None,
            'selected_passage': candidate.get('passage') if candidate else None,
            'selected_passage_sha256': candidate.get('passage_sha256') if candidate else None,
            'state': state,
            'reviewer': event.get('reviewer') if event else None,
            'relevance': event.get('relevance') if event else None,
            'evidence_sufficiency_review': event.get('evidence_sufficiency_review') if event else None,
            'reviewer_rationale': event.get('rationale') if event else None,
            'gap_or_follow_up': event.get('gap_or_follow_up') if event else None,
            'review_timestamp_utc': event.get('timestamp_utc') if event else None,
            'review_event_sha256': event.get('event_sha256') if event else None,
            'decision_scope': event.get('decision_scope') if event else None,
            'next_action': follow_up['required_action'],
        })
    return {
        'title': 'CardioAhead — Reviewer-Grounded Evidence Gap Triage',
        'kind': 'DEMONSTRATION_NOT_COMPLIANCE_FINDING',
        'source_assessment_sha256': source_sha,
        'source_pdf_sha256': assessment.get('source_pdf_sha256'),
        'requirement_count': len(rows),
        'candidate_requirements': sum(bool(x['candidate_count']) for x in rows),
        'current_human_reviews': sum(bool(x['review_event_sha256']) for x in rows),
        'historical_events_with_different_source': stale_count,
        'counts_by_review_state': dict(Counter(r['state'] for r in rows)),
        'rows': rows,
        'release_gate': 'NOT_PRODUCTION',
        'limitations': [
            'Synthetic CardioAhead documents and extracted MDR clauses have not been legally validated.',
            'Matching documents are candidate evidence, not proof of implementation or regulatory conformity.',
            'Reviewer classification is attributed opinion, not a system compliance approval.',
            'No-candidate does not mean a missing company document or confirmed compliance gap.',
            'Only latest review PER REQUIREMENT is shown; audit log retains all events.',
            'System-suggested actions are not reviewer-approved. Reviewer-entered actions are attributed to the reviewer.',
        ],
    }


def to_html(report: dict) -> str:
    esc = lambda x: html.escape(str(x or ''))
    sections=[]
    for r in report['rows']:
        badge = r['state'].replace('_',' ')
        candidate_passage = f'<p><strong>Reviewed passage:</strong> {esc(r["selected_passage"])}</p>' if r['selected_passage'] else ''
        sections.append(f'''<section class="card"><h2>{esc(r['requirement_id'])} <span>{esc(badge)}</span></h2>
        <p class="requirement">{esc(r['requirement'])}</p>
        <dl><dt>Candidate documents</dt><dd>{esc(', '.join(r['candidate_ids']) or 'None retrieved')}</dd>
        <dt>Selected evidence</dt><dd>{esc(r['selected_document'] or 'Not selected')}</dd>
        <dt>Reviewer</dt><dd>{esc(r['reviewer'] or 'Pending')}</dd>
        <dt>Relevance</dt><dd>{esc(r['relevance'] or 'Not assessed')}</dd>
        <dt>Sufficiency opinion</dt><dd>{esc(r['evidence_sufficiency_review'] or 'Not assessed')}</dd>
        <dt>Reviewer rationale</dt><dd>{esc(r['reviewer_rationale'] or 'No review recorded')}</dd>
        <dt>Finding (observed passage)</dt><dd>{esc(r['finding'])}</dd>
        <dt>Evidence gap / review status</dt><dd>{esc(r['evidence_gap'])}</dd>
        <dt>Required action / follow-up</dt><dd>{esc(r['required_action'])}</dd>
        <dt>Action attribution</dt><dd>{esc(r['action_origin'])}</dd>
        <dt>Evidence passage SHA-256</dt><dd>{esc(r['selected_passage_sha256'] or 'Not selected')}</dd>
        <dt>Requirement SHA-256</dt><dd>{esc(r['requirement_sha256'])}</dd>
        <dt>Review timestamp (UTC)</dt><dd>{esc(r['review_timestamp_utc'] or 'Not reviewed')}</dd>
        <dt>Review event SHA-256</dt><dd>{esc(r['review_event_sha256'] or 'Not reviewed')}</dd>
        <dt>Decision scope</dt><dd>{esc(r['decision_scope'] or 'Not reviewed')}</dd></dl>{candidate_passage}</section>''')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MedAI Gap Review</title><style>
    *{{box-sizing:border-box}}body{{background:#f4f7fa;color:#182b3a;font:15px system-ui,Arial;margin:0}}header{{padding:24px 5%;background:#17364a;color:white}}main{{max-width:1100px;margin:24px auto;padding:0 18px}}.card{{background:white;border:1px solid #dce5eb;border-radius:12px;padding:20px;margin-bottom:16px}}h2{{font-size:17px}}h2 span{{font-size:11px;color:#637c89;margin-left:10px}}.warning{{padding:15px;background:#fff0d6;border-radius:8px}}dl{{display:grid;grid-template-columns:210px 1fr;gap:8px}}dt{{font-weight:600}}dd{{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}}.requirement{{font-style:italic}}a{{color:#176c86}}@media(max-width:600px){{dl{{grid-template-columns:1fr}}}}</style></head><body>
    <header><h1>CardioAhead — Evidence Gap Triage</h1><p>{report['requirement_count']} requirements · {report['candidate_requirements']} with candidates · {report['current_human_reviews']} currently reviewed</p></header>
    <main><p class="warning"><strong>NOT PRODUCTION · NO COMPLIANCE APPROVAL.</strong> This is a synthetic document triage pilot. Reviewer opinions are not certification or legal conclusions. System-generated follow-up suggestions must be confirmed by a qualified reviewer. Stale-source events excluded: {report['historical_events_with_different_source']}.</p>
    <p><a href="/">Return to Review Workbench</a> · <a href="/gap-report.csv">Export CSV</a> · <a href="/gap-report.json">Export JSON</a></p>{''.join(sections)}</main></body></html>'''


def to_csv_bytes(report: dict) -> bytes:
    out=io.StringIO(newline='')
    fields=['requirement_id','requirement','requirement_sha256','source_review','candidate_count','candidate_ids','selected_document','selected_passage','selected_passage_sha256','state','finding','evidence_gap','required_action','action_origin','reviewer','relevance','evidence_sufficiency_review','reviewer_rationale','next_action','review_timestamp_utc','review_event_sha256','decision_scope']
    w=csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    for row in report['rows']:
        r={k:row.get(k) for k in fields}
        r['candidate_ids']='; '.join(row['candidate_ids'])
        # Spreadsheet formula injection defense for data coming from documents/reviewer inputs.
        for k,v in r.items():
            if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')):
                r[k]="'"+v
        w.writerow(r)
    return out.getvalue().encode('utf-8-sig')
