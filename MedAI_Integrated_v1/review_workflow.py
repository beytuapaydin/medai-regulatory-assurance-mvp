r"""Local, human-controlled, append-only evidence review (not compliance certification).

Run from repository root:
  .\.venv\Scripts\python.exe .\MedAI_Integrated_v1\review_workflow.py serve

Uses the existing Integrated v1 assessment.json without changing it.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import html
import io
import json
import os
from pathlib import Path
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from gap_report import build_report, to_html, to_csv_bytes

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'output' / 'assessment.json'
OUT = ROOT / 'output' / 'human_review'
EVENTS = OUT / 'review_events.jsonl'
HTML_LIMIT = 16000
VALID_RELEVANCE = {'RELEVANT', 'NOT_RELEVANT', 'UNCERTAIN'}
VALID_SUFFICIENCY = {'NOT_ASSESSED', 'PARTIAL', 'INSUFFICIENT', 'REVIEWER_CONSIDERS_SUFFICIENT'}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def read_source():
    if not SOURCE.is_file():
        raise ValueError('Missing assessment.json. Run MedAI_Integrated_v1/run.py first.')
    data = json.loads(SOURCE.read_text(encoding='utf-8-sig'))
    requirements = data.get('requirements')
    if not isinstance(requirements, list) or len(requirements) != 13:
        raise ValueError('Expected exactly 13 MDR Article 10(9) requirements.')
    ids = [r['requirement_id'] for r in requirements]
    if len(set(ids)) != 13 or any(not r.get('requirement_sha256') for r in requirements):
        raise ValueError('Duplicate or invalid source requirement IDs.')
    for r in requirements:
        if sha(r['requirement']) != r['requirement_sha256']:
            raise ValueError('Source requirement integrity mismatch: '+r['requirement_id'])
        for c in r.get('candidates', []):
            if sha(c['passage']) != c['passage_sha256']:
                raise ValueError('Candidate passage integrity mismatch: '+r['requirement_id'])
    return data, sha(SOURCE.read_text(encoding='utf-8-sig'))


def read_events():
    events=[]
    prev='GENESIS'
    if not EVENTS.exists():
        return events
    for number,line in enumerate(EVENTS.read_text(encoding='utf-8').splitlines(),1):
        if not line.strip():
            continue
        event=json.loads(line)
        digest=event.get('event_sha256')
        unsigned={k:v for k,v in event.items() if k != 'event_sha256'}
        if unsigned.get('previous_sha256') != prev or sha(canonical(unsigned)) != digest:
            raise ValueError('Review log integrity check FAILED at event '+str(number))
        prev=digest
        events.append(event)
    return events


def make_event(data, source_sha, events, payload):
    index={r['requirement_id']:r for r in data['requirements']}
    rid=payload.get('requirement_id', '')
    if rid not in index:
        raise ValueError('Unknown requirement')
    r=index[rid]
    cid=payload.get('candidate_id', '')
    choices={c['document_id'] for c in r.get('candidates', [])}
    if cid and cid not in choices:
        raise ValueError('Candidate not in source record')
    relevance=payload.get('relevance', '')
    sufficiency=payload.get('sufficiency', '')
    if relevance not in VALID_RELEVANCE or sufficiency not in VALID_SUFFICIENCY:
        raise ValueError('Invalid review classification')
    if not cid and relevance == 'RELEVANT':
        raise ValueError('Cannot mark missing evidence as relevant')
    if sufficiency == 'REVIEWER_CONSIDERS_SUFFICIENT' and relevance != 'RELEVANT':
        raise ValueError('Only relevant evidence can be assessed as potentially sufficient')
    reviewer=payload.get('reviewer','').strip()
    rationale=payload.get('rationale','').strip()
    gap=payload.get('gap','').strip()
    if not (2 <= len(reviewer) <= 100 and 15 <= len(rationale) <= 4000 and len(gap) <= 2000):
        raise ValueError('Reviewer (2â€“100 chars) and detailed rationale (15â€“4000 chars) required')
    event={
        'event_number':len(events)+1,
        'timestamp_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'source_assessment_sha256':source_sha,
        'requirement_id':rid,
        'requirement_sha256':r['requirement_sha256'],
        'candidate_id':cid or None,
        'relevance':relevance,
        'evidence_sufficiency_review':sufficiency,
        'reviewer':reviewer,
        'rationale':rationale,
        'gap_or_follow_up':gap,
        'decision_scope':'EVIDENCE_TRIAGE_ONLY_NOT_LEGAL_COMPLIANCE',
        'previous_sha256':events[-1]['event_sha256'] if events else 'GENESIS',
    }
    event['event_sha256']=sha(canonical(event))
    return event


def append_event(event):
    OUT.mkdir(parents=True, exist_ok=True)
    with EVENTS.open('a',encoding='utf-8',newline='\n') as file:
        file.write(canonical(event)+'\n')
        file.flush()
        os.fsync(file.fileno())


def export(data, events):
    OUT.mkdir(parents=True,exist_ok=True)
    latest={}
    for e in events:latest[e['requirement_id']]=e
    fields=['requirement_id','requirement','candidate_count','candidate_ids','review_state','reviewer','relevance','evidence_sufficiency_review','rationale','gap_or_follow_up','timestamp_utc','event_sha256']
    target=OUT/'review_summary.csv'
    with target.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in data['requirements']:
            e=latest.get(r['requirement_id'],{})
            w.writerow({'requirement_id':r['requirement_id'],'requirement':r['requirement'],
              'candidate_count':len(r.get('candidates',[])),
              'candidate_ids':'; '.join(c['document_id'] for c in r.get('candidates',[])),
              'review_state':'REVIEWED' if e else 'PENDING',
              **{x:e.get(x,'') for x in fields if x not in ('requirement_id','requirement','candidate_count','candidate_ids','review_state')}})
    return target


def page(data,events,token,notice=''):
    latest={}
    for e in events:latest[e['requirement_id']]=e
    reviewed=len(latest)
    cards=[]
    for r in data['requirements']:
        rid=r['requirement_id']; old=latest.get(rid)
        candidates=r.get('candidates',[])
        options='<option value="">No candidate / missing evidence</option>' + ''.join('<option value="'+html.escape(c['document_id'],quote=True)+'">'+html.escape(c['document_id'])+'</option>' for c in candidates)
        candidate_html=''.join('<div class="candidate"><b>'+html.escape(c['document_id'])+'</b> Â· '+html.escape(c['filename'])+'<blockquote>'+html.escape(c['passage'])+'</blockquote><small>SHA-256: '+html.escape(c['passage_sha256'])+'</small></div>' for c in candidates) or '<p class="muted">No automatically retrieved candidate; do not infer noncompliance.</p>'
        last='<p class="reviewed">Latest review: '+html.escape(old['relevance'])+' / '+html.escape(old['evidence_sufficiency_review'])+' by '+html.escape(old['reviewer'])+'</p>' if old else '<p class="muted">Pending human review</p>'
        cards.append('<section class="card"><h3>'+html.escape(rid)+' <span class="pill">'+str(len(candidates))+' candidate(s)</span></h3><p>'+html.escape(r['requirement'])+'</p>'+candidate_html+last+
          '<form method="POST" action="/review"><input type="hidden" name="csrf" value="'+token+'"><input type="hidden" name="requirement_id" value="'+html.escape(rid)+'"><div class="fields"><label>Candidate<select name="candidate_id">'+options+'</select></label><label>Relevance<select name="relevance"><option>UNCERTAIN</option><option>RELEVANT</option><option>NOT_RELEVANT</option></select></label><label>Evidence sufficiency (reviewer only)<select name="sufficiency"><option>NOT_ASSESSED</option><option>PARTIAL</option><option>INSUFFICIENT</option><option>REVIEWER_CONSIDERS_SUFFICIENT</option></select></label></div><label>Reviewer name / identifier<input required minlength="2" maxlength="100" name="reviewer" placeholder="Qualified reviewer"></label><label>Rationale (minimum 15 characters)<textarea required minlength="15" maxlength="4000" name="rationale" placeholder="Explain exactly what this passage supports and does not support"></textarea></label><label>Gap / next action<textarea name="gap" maxlength="2000" placeholder="What evidence or review is still required?"></textarea></label><button type="submit">Record review decision</button></form></section>')
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MedAI Evidence Review</title>'+
      '<style>body{font:15px system-ui,Arial;background:#f4f6f8;color:#172338;margin:0}header{background:#142d43;color:white;padding:25px 5vw}main{max-width:1000px;margin:25px auto;padding:0 15px}.card{background:white;border:1px solid #dee5ea;border-radius:12px;padding:22px;margin:18px 0;box-shadow:0 3px 13px #11111108}h1{margin:0 0 8px}h3{margin:0 0 10px}.muted,small{color:#627284}.candidate{border-left:3px solid #558296;padding:12px;margin:10px 0;background:#f7fafb}blockquote{margin:10px 0;white-space:pre-wrap}.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}label{display:block;font-weight:600;margin:12px 0 3px}input,select,textarea{display:block;width:100%;box-sizing:border-box;padding:10px;border:1px solid #bdc9d4;border-radius:6px;margin-top:5px;font:inherit}textarea{min-height:65px}button{background:#19677b;color:white;border:0;border-radius:7px;padding:11px 18px;cursor:pointer}.pill{font-size:12px;color:#416275}.reviewed{color:#145a42;font-weight:600}.note{padding:12px 15px;background:#fff5dc;border-radius:8px;color:#624a16}</style>'+
      '<header><h1>MedAI Â· Evidence Review Workbench</h1><div>CardioAhead synthetic demonstration Â· '+str(reviewed)+'/13 requirements reviewed Â· '+str(len(events))+' audit events</div></header><main><p class="note"><b>NOT PRODUCTION â€” NOT A COMPLIANCE DECISION.</b> Candidate passages are not proof of regulatory conformity. Human review events are append-only, with a hash chain for accidental-change detection (not a tamper-proof signature).</p>'+('<p class="note">'+html.escape(notice)+'</p>' if notice else '')+'<p><a href="/gap-report">Gap Assessment Report</a> Â· <a href="/gap-report.csv">Gap CSV</a> Â· <a href="/summary.csv">Export review CSV</a> Â· <a href="/events.jsonl">Download audit log</a></p>'+''.join(cards)+'</main></html>')


def serve(port):
    data, source_sha=read_source()
    read_events() # verify before accepting new reviews
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def send(self,body,content_type='text/html; charset=utf-8',status=200):
            raw=body.encode('utf-8') if isinstance(body,str) else body
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            try:
                events=read_events()
                if self.path=='/': self.send(page(data,events,token));return
                if self.path in ('/gap-report','/gap-report.json','/gap-report.csv'):
                    report=build_report(data,events,source_sha)
                    if self.path=='/gap-report': self.send(to_html(report));return
                    if self.path=='/gap-report.csv': self.send(to_csv_bytes(report),'text/csv; charset=utf-8');return
                    self.send(json.dumps(report,ensure_ascii=False,indent=2),'application/json; charset=utf-8');return
                if self.path=='/summary.csv':
                    self.send(export(data,events).read_bytes(),'text/csv; charset=utf-8');return
                if self.path=='/events.jsonl':
                    self.send(EVENTS.read_bytes() if EVENTS.exists() else b'','application/x-ndjson; charset=utf-8');return
                self.send('Not found',status=404)
            except Exception as e:self.send('Audit integrity failure: '+html.escape(str(e)),status=500)
        def do_POST(self):
            if self.path!='/review':self.send('Not found',status=404);return
            n=int(self.headers.get('Content-Length','0'))
            if n <= 0 or n > HTML_LIMIT:self.send('Invalid form size',status=400);return
            if self.headers.get('Origin') not in (None,f'http://127.0.0.1:{port}'):
                self.send('Invalid origin',status=403);return
            form={k:v[0] for k,v in parse_qs(self.rfile.read(n).decode('utf-8'),keep_blank_values=True).items()}
            if not secrets.compare_digest(form.get('csrf',''),token):self.send('Invalid form token',status=403);return
            try:
                events=read_events()
                event=make_event(data,source_sha,events,form)
                append_event(event)
                self.send_response(303);self.send_header('Location','/');self.send_header('Content-Length','0');self.end_headers()
            except ValueError as exc:self.send(page(data,read_events(),token,str(exc)),status=400)
    srv=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print('LOCAL REVIEW UI: http://127.0.0.1:'+str(port),flush=True)
    print('EXISTING SOURCE (read only):',SOURCE,flush=True)
    print('AUDIT LOG:',EVENTS,flush=True)
    print('RELEASE GATE: NOT PRODUCTION',flush=True)
    try:srv.serve_forever()
    except KeyboardInterrupt:print('\nLocal reviewer stopped.')
    finally:srv.server_close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['serve','export','check'])
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    data,_=read_source()
    events=read_events()
    if args.command=='check':print('SOURCE:',len(data['requirements']),'requirements; AUDIT EVENTS:',len(events));print('INTEGRITY: OK')
    elif args.command=='export':print('EXPORTED:',export(data,events))
    elif args.command=='serve':serve(args.port)

if __name__=='__main__':main()

