"""MedAI integrated evidence inventory, local and read-only towards inputs.

Does not provide a legal compliance decision. Candidate matches require expert review.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import html
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
KNOWN_SHA = 'a8cca6f45159c678e2562ad5ad9140f4d1caad9b074ed97d78bc2b2347f912d0'
STOP = set('a an the and or to of for by with in on as is are be at from that this including under shall other all any such into their those'.split())
# Search-expansion hints, NOT legal or semantic equivalence proof.
CONCEPTS = {
    'a': 'regulatory strategy conformity assessment change control modifications',
    'b': 'gspr requirements safety performance verification traceability worksheet',
    'c': 'management responsibility roles responsibility matrix leadership accountability',
    'd': 'supplier subcontractor resources purchasing vendor qualification',
    'e': 'risk hazards harm risk management residual acceptability',
    'f': 'clinical evaluation pmcf clinical evidence literature',
    'g': 'design development production service realization lifecycle',
    'h': 'udi assignment registration identifiers eudamed',
    'i': 'post market surveillance pms monitoring',
    'j': 'communication competent authority notified body stakeholders customer',
    'k': 'vigilance incidents field safety corrective action fs ca reporting',
    'l': 'capa preventive corrective actions effectiveness verification',
    'm': 'measurement monitoring output performance improvement analysis',
}
MAX_SIZE = 5 * 1024 * 1024
MAX_FILES = 250


def sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def load_requirements(path: Path) -> tuple[list[dict], dict]:
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if data.get('article') != 10 or data.get('subsection') != 9 or data.get('source_pdf_sha256') != KNOWN_SHA:
        raise ValueError('Unrecognized MDR requirement source/version')
    clauses = data.get('clauses', [])
    if [c.get('label') for c in clauses] != list('abcdefghijklm'):
        raise ValueError('Missing, repeated or reordered legal clauses')
    for c in clauses:
        if sha(c['text']) != c['text_sha256'] or c.get('expert_validated') is not False:
            raise ValueError('Source clause integrity/review state is not acceptable')
    return clauses, data


def read_text(path: Path) -> str:
    if path.stat().st_size > MAX_SIZE:
        raise ValueError(f'Document too large: {path.name}')
    suffix = path.suffix.lower()
    if suffix in ('.txt', '.md'):
        return path.read_text(encoding='utf-8-sig')
    if suffix == '.pdf':
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError('PDF input requires pypdf in the project venv') from exc
        return '\n\n'.join(f'[PDF page {i}]\n{page.extract_text() or ""}' for i, page in enumerate(PdfReader(str(path)).pages, 1))
    if suffix == '.docx':
        try:
            from docx import Document
        except ImportError as exc:
            raise ValueError('DOCX input requires python-docx in the project venv') from exc
        doc = Document(str(path))
        lines = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                lines.append(' | '.join(c.text for c in row.cells))
        return '\n'.join(lines)
    raise ValueError('Unsupported document file type')


def ingest(folder: Path) -> list[dict]:
    if not folder.is_dir():
        raise ValueError('Document directory does not exist')
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {'.txt','.md','.pdf','.docx'})
    if not files or len(files) > MAX_FILES:
        raise ValueError('Expected 1-250 supported document files')
    docs = []
    for p in files:
        text = read_text(p)
        if not text.strip():
            raise ValueError('Empty or unreadable document: ' + p.name)
        docs.append({'document_id': p.stem, 'filename': p.name, 'text': text,
                     'sha256': sha(text), 'bytes': p.stat().st_size})
    return docs


def tokenize(text: str) -> list[str]:
    # Normalize PDF soft hyphen and word-breaking spaces for retrieval only.
    text = text.replace('\u00ad ', '').replace('\u00ad', '')
    return [x for x in re.findall(r'[a-zA-Z0-9]{3,}', text.lower()) if x not in STOP]


def paragraphs(text: str, length: int = 650) -> list[dict]:
    """Small deterministic spans; retain exact content and location."""
    blocks = [b.strip() for b in re.split(r'\n\s*\n', text) if b.strip()]
    out = []
    offset = 0
    for block in blocks:
        start = text.find(block, offset)
        if start < 0:
            start = offset
        offset = start + len(block)
        for i in range(0, len(block), length):
            excerpt = block[i:i+length]
            if excerpt.strip():
                out.append({'text': excerpt, 'start_char': start+i, 'end_char': start+i+len(excerpt)})
    return out


def similarity(query: str, passage: str) -> tuple[float, list[str]]:
    q = set(tokenize(query)); words = set(tokenize(passage))
    common = q & words
    if not q or not words:
        return 0.0, []
    # Dice coefficient: non-calibrated retrieval heuristic; never interpret as confidence.
    return round(2*len(common)/(len(q)+len(words)), 5), sorted(common)


def candidates(clauses: list[dict], docs: list[dict], limit: int = 3) -> list[dict]:
    results=[]
    for clause in clauses:
        key = clause['label']
        query = clause['text']+' '+CONCEPTS[key]
        scored=[]
        for doc in docs:
            for p in paragraphs(doc['text']):
                score, terms = similarity(query,p['text'])
                if score > 0 and len(terms) >= 2:
                    scored.append({'document_id':doc['document_id'], 'filename':doc['filename'],
                                   'document_sha256':doc['sha256'], 'passage':p['text'],
                                   'passage_sha256':sha(p['text']), 'start_char':p['start_char'],
                                   'end_char':p['end_char'], 'retrieval_score':score,
                                   'matched_terms':terms})
        scored.sort(key=lambda x:(-x['retrieval_score'],x['document_id'],x['start_char']))
        distinct=[];seen=set()
        for item in scored:
            if item['document_id'] not in seen:
                distinct.append(item); seen.add(item['document_id'])
                if len(distinct) == limit: break
        results.append({'requirement_id':f'MDR-10-9-{key.upper()}', 'label':key,
                        'requirement':clause['text'], 'requirement_sha256':clause['text_sha256'],
                        'source_id':clause['source_id'], 'source_version':clause['source_version'],
                        'source_review':'EXTRACT_UNVERIFIED',
                        'state':'CANDIDATE_FOR_REVIEW' if distinct else 'NO_RETRIEVAL_CANDIDATE',
                        'candidates':distinct,
                        'evidence_sufficiency':'NOT_ASSESSED', 'legal_applicability':'NOT_ASSESSED',
                        'human_review':'PENDING',
                        'review_action':('Check passage relevance, evidence completeness, controlled approval and implementation records.' if distinct else 'Search other controlled records; absence of a candidate is not proof of a compliance gap.')})
    return results


def html_report(report: dict) -> str:
    E=lambda s: html.escape(str(s),quote=True)
    rows=[]
    for r in report['requirements']:
        blocks=[]
        for c in r['candidates']:
            blocks.append(f'<div class="candidate"><b>{E(c["filename"])}</b><span class="muted"> · revision not assessed · retrieval score {E(c["retrieval_score"])} (not confidence)</span><blockquote>{E(c["passage"])}</blockquote><small>Matched terms: {E(", ".join(c["matched_terms"]))} · SHA256: {E(c["passage_sha256"][:16])}… · char offset {E(c["start_char"])}</small></div>')
        candidate_html=''.join(blocks) if blocks else '<div class="candidate muted">No candidate found in provided files. This is not a compliance deficiency finding.</div>'
        rows.append(f'<article data-state="{E(r["state"])}"><div class="head"><h3>Article 10(9)({E(r["label"])})</h3><span class="pill">{E(r["state"])}</span></div><p class="req">{E(r["requirement"])}</p><h4>Automatically retrieved passages — unverified</h4>{candidate_html}<p class="foot"><b>Review action:</b> {E(r["review_action"])}<br>Evidence sufficiency: NOT ASSESSED · Human review: PENDING</p></article>')
    cand=sum(r['state']=='CANDIDATE_FOR_REVIEW' for r in report['requirements'])
    return '''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MedAI | Regulatory Evidence Assessment</title><style>
    body{margin:0;background:#f4f7fa;color:#183348;font:15px/1.6 system-ui,Segoe UI,Arial}header{background:#143647;color:#fff;padding:38px 22px}header p{color:#cddfe9}main,header .wrap{max-width:1120px;margin:auto}main{padding:22px}h1{font-size:32px;margin:0}h3{font-size:20px;margin:0}h4{margin:16px 0 8px}small,.muted{color:#657a89}.muted{font-size:13px}.note{padding:16px;background:#fff3dd;border-left:4px solid #b78321;border-radius:8px;margin:16px 0}.stat{display:flex;gap:14px;flex-wrap:wrap}.stat div{background:#fff;padding:16px 22px;border-radius:10px;border:1px solid #dae4e9}.stat strong{font-size:25px}article{background:#fff;border:1px solid #dce4e8;border-radius:12px;padding:20px;margin:15px 0}.head{display:flex;justify-content:space-between;gap:14px}.pill{font-size:11px;background:#e8f0f4;border-radius:100px;padding:5px 10px;height:max-content}.req{background:#f6f9fb;padding:12px;border-radius:7px}.candidate{border-left:3px solid #8cb3c1;padding:7px 14px;margin:10px 0;background:#f5f9fa}blockquote{margin:7px 0;font-size:14px}.foot{border-top:1px solid #e1e8ec;padding-top:12px;font-size:13px}.toolbar{display:flex;gap:10px;margin:15px 0}.toolbar button{background:#fff;border:1px solid #bed0d9;padding:10px 13px;border-radius:7px;cursor:pointer}article[hidden]{display:none}@media print{.toolbar{display:none}article{break-inside:avoid}} </style></head><body><header><div class="wrap"><small>MEDAI · CARDIOAHEAD / SYNTHETIC DEMONSTRATION</small><h1>Regulatory Evidence Assessment</h1><p>Automatic candidate passages from supplied documents, linked to extracted MDR Article 10(9) requirements. Evidence sufficiency, legal applicability and compliance NOT evaluated.</p></div></header><main><div class="note"><b>NOT PRODUCTION · HUMAN REVIEW REQUIRED</b><p>Documents are synthetic or user-supplied. Source requirement extraction not expert-verified. Retrieval score is not a probability of correctness. No evidence candidate is an approved compliance claim.</p></div><div class="stat"><div><strong>13</strong><br>MDR requirements</div><div><strong>''' + str(cand) + '''</strong><br>With retrieved candidates</div><div><strong>''' + str(13-cand) + '''</strong><br>Without candidates</div><div><strong>0</strong><br>Expert-verified cases</div></div><div class="toolbar"><button onclick="filter('all')">All</button><button onclick="filter('CANDIDATE_FOR_REVIEW')">With candidates</button><button onclick="filter('NO_RETRIEVAL_CANDIDATE')">No candidate</button><button onclick="window.print()">Print / Save PDF</button></div>''' + ''.join(rows) + '''<p class="muted">MDR consolidation: 2026-07-19. Requirement extract hash verified against bundled reference. Output has no compliance approval authority.</p></main><script>function filter(v){document.querySelectorAll('article').forEach(x=>x.hidden=(v!=='all'&&x.dataset.state!==v))}</script></body></html>'''


def save(report: dict, folder: Path) -> None:
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'assessment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    columns=['requirement_id','source_review','state','candidate_document','passage_sha256','retrieval_score','evidence_sufficiency','legal_applicability','human_review','review_action','reviewer','review_notes']
    with (folder/'review_queue.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,columns);writer.writeheader()
        for r in report['requirements']:
            top=r['candidates'][0] if r['candidates'] else {}
            writer.writerow({'requirement_id':r['requirement_id'],'source_review':r['source_review'],'state':r['state'],
                             'candidate_document':top.get('filename',''),'passage_sha256':top.get('passage_sha256',''),
                             'retrieval_score':top.get('retrieval_score',''), 'evidence_sufficiency':'NOT_ASSESSED',
                             'legal_applicability':'NOT_ASSESSED','human_review':'PENDING','review_action':r['review_action'],
                             'reviewer':'','review_notes':''})
    (folder/'dashboard.html').write_text(html_report(report),encoding='utf-8')


def main() -> int:
    parser=argparse.ArgumentParser(description='MedAI local requirement-to-evidence retrieval pilot')
    parser.add_argument('--documents',default=str(BASE/'docs_demo'),help='Folder containing TXT, MD, PDF or DOCX evidence files')
    parser.add_argument('--output',default=str(BASE/'output'))
    args=parser.parse_args()
    try:
        clauses, evidence=load_requirements(BASE/'data/article10_9_clause_evidence.json')
        docs=ingest(Path(args.documents))
        results=candidates(clauses,docs)
        report={'project':'CardioAhead · MedAI Integrated Pilot','generated_utc':datetime.now(timezone.utc).isoformat(),
                'type':'LOCAL_RETRIEVAL_CANDIDATES_NOT_COMPLIANCE_FINDINGS', 'source_pdf_sha256':KNOWN_SHA,
                'documents':[{'id':d['document_id'],'filename':d['filename'],'sha256':d['sha256']} for d in docs],
                'requirements':results,'release_gate':'NOT_PRODUCTION',
                'limitations':['Source extracted from MDR PDF; expert verification pending',
                               'Retrieval uses lexical/concept heuristic, not semantic legal entailment',
                               'Documents are not vetted for authenticity, scope, revision or applicability',
                               'Any candidate requires human relevance, sufficiency and applicability review']}
        save(report,Path(args.output))
        print('DOCUMENTS READ:',len(docs))
        print('REQUIREMENTS:',len(results))
        print('CANDIDATE REQUIREMENTS:',sum(bool(x['candidates']) for x in results))
        print('NO CANDIDATE:',sum(not x['candidates'] for x in results))
        print('HUMAN VERIFIED: 0')
        print('DASHBOARD:',(Path(args.output)/'dashboard.html').resolve())
        print('REVIEW QUEUE:',(Path(args.output)/'review_queue.csv').resolve())
        print('RELEASE GATE: NOT_PRODUCTION')
        return 0
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        print('FAIL CLOSED:',type(exc).__name__,str(exc));return 2

if __name__=='__main__':
    raise SystemExit(main())
