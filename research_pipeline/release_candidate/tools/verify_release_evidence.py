#!/usr/bin/env python3
"""Read-only local SHA-256 reconciliation for MedAI research RC1. No ECG/holdout access."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys

REGISTRY = Path(__file__).resolve().parent.parent / 'docs' / 'evidence_registry.json'

class AuditFailure(Exception):
    pass

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for piece in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(piece)
    return digest.hexdigest().upper()

def validate_relative_path(name: str) -> PurePosixPath:
    """Accept canonical, POSIX-separated relative evidence paths on any host OS.

    In particular, a rooted POSIX path must be rejected even on Windows,
    where pathlib.Path('/tmp/foo').is_absolute() may be false.
    """
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise AuditFailure('Unsafe relative path')
    p = PurePosixPath(name)
    w = PureWindowsPath(name)
    if (
        p.is_absolute() or w.is_absolute() or w.drive or w.root
        or not p.parts or any(part in ('.', '..') for part in name.split('/'))
        or any(':' in part or part.endswith((' ', '.')) for part in p.parts)
        or name.startswith('/') or name.endswith('/') or '//' in name
    ):
        raise AuditFailure('Unsafe relative path: ' + name)
    return p

def verify_entries(docs: Path, registry: dict) -> list:
    if registry.get('status') != 'RESEARCH_RELEASE_CANDIDATE_NO_GO' or registry.get('holdout_authorized') is not False:
        raise AuditFailure('Registry gate state changed')
    entries = registry.get('evidence')
    if not isinstance(entries, list) or len(entries) != 15:
        raise AuditFailure('Unexpected evidence registry size')
    seen = set()
    results = []
    docs = docs.resolve(strict=True)
    for e in entries:
        key = e['id']
        if key in seen: raise AuditFailure('Duplicate evidence entry: ' + key)
        seen.add(key)
        rel = validate_relative_path(e['relative_path'])
        expected = e['sha256'].upper()
        if len(expected) != 64 or any(c not in '0123456789ABCDEF' for c in expected):
            raise AuditFailure('Bad expected digest: ' + key)
        file_path = docs / rel
        try:
            resolved = file_path.resolve(strict=True)
        except FileNotFoundError:
            raise AuditFailure('Missing evidence: ' + str(rel)) from None
        if docs not in resolved.parents or not resolved.is_file():
            raise AuditFailure('Unsafe or non-file evidence: ' + str(rel))
        actual = sha256(resolved)
        if actual != expected:
            raise AuditFailure(f'SHA256 mismatch: {key} expected={expected} actual={actual}')
        results.append({'id':key,'path':rel.as_posix(),'sha256':actual,'bytes':resolved.stat().st_size})
    return results

def check_semantics(docs: Path):
    with (docs/'MEDAI-PTBXL-MI-001-Frozen-v1/protocol.json').open(encoding='utf-8') as f:protocol=json.load(f)
    with (docs/'MedAI-Final-Candidate-Frozen-v1/candidate_model.json').open(encoding='utf-8') as f:model=json.load(f)
    if protocol.get('status') != 'DEVELOPMENT_PROTOCOL_AND_EVIDENCE_FROZEN_HOLDOUT_NOT_AUTHORIZED':
        raise AuditFailure('Unexpected protocol status')
    if model.get('decision_threshold') != 0.3795860831201651 or len(model.get('weights',[])) != 72:
        raise AuditFailure('Model/threshold contract mismatch')

def verify(docs:Path, registry: dict, *, semantic:bool = True) -> dict:
    results=verify_entries(docs,registry)
    if semantic:check_semantics(docs)
    return {'schema_version':'medai-rc1-verification-v1',
            'status':'ALL_REGISTERED_EVIDENCE_HASHES_MATCH',
            'classification':'DOCUMENTATION_ONLY_RESEARCH_RC1',
            'holdout_authorized':False,
            'go_nogo':'NO_GO',
            'evidence_count':len(results),
            'registry_sha256':sha256(REGISTRY) if REGISTRY.exists() else None,
            'evidence':results,
            'limitations':['no independent review recorded','no Fold 10 read','not a clinical or complete software release']}

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docs',type=Path,required=True,help='User Documents containing original evidence')
    parser.add_argument('--output',type=Path,required=True,help='New verification JSON (must not exist)')
    args=parser.parse_args()
    try:
        if args.output.exists():raise AuditFailure('Refusing to overwrite output')
        with REGISTRY.open(encoding='utf-8') as f:registry=json.load(f)
        record=verify(args.docs,registry)
        data=json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8',newline='\n') as dst:dst.write(data)
        print('STATUS:',record['status'])
        print('EVIDENCE HASHES VERIFIED:',record['evidence_count'])
        print('HOLDOUT AUTHORIZED: NO')
        print('DECISION: NO_GO')
        print('FOLD 9/10 SIGNALS/LABELS: NOT READ')
        print('REPORT:',args.output)
        print('REPORT SHA256:',sha256(args.output))
        return 0
    except (AuditFailure, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as err:
        print('FAIL_CLOSED:',err,file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
