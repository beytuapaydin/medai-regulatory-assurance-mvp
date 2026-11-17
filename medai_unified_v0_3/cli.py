"""CLI for unified evidence SNAPSHOT and separate human review (research only)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .core import (build_unified, verify_unified, write_package, read_unified_reviews,
                   append_unified_review, REVIEW_CHOICES, _load_json)


def main() -> None:
    p = argparse.ArgumentParser(description="MedAI Unified Evidence Bridge v0.3 (research only)")
    cmds = p.add_subparsers(dest="command", required=True)
    b = cmds.add_parser("build", help="Build immutable-in-this-snapshot (not tamperproof) unified evidence JSON")
    b.add_argument("--assessment", required=True, type=Path)
    b.add_argument("--clinical", required=True, type=Path)
    b.add_argument("--reg-events", type=Path)
    b.add_argument("--retrieval-eval", type=Path)
    b.add_argument("--output", required=True, type=Path)
    v = cmds.add_parser("verify")
    v.add_argument("--package", required=True, type=Path)
    v.add_argument("--review-log", type=Path)
    v.add_argument("--assessment", type=Path, help="Optional source assessment for binding verification")
    v.add_argument("--clinical", type=Path, help="Optional source clinical JSON for binding verification")
    v.add_argument("--protocol", type=Path, help="Independent locked protocol JSON")
    v.add_argument("--require-protocol-lock", action="store_true", help="Fail closed without --protocol")
    r = cmds.add_parser("review")
    r.add_argument("--package", required=True, type=Path)
    r.add_argument("--review-log", required=True, type=Path)
    r.add_argument("--reviewer", required=True)
    r.add_argument("--disposition", required=True, choices=sorted(REVIEW_CHOICES))
    r.add_argument("--rationale", required=True)
    args = p.parse_args()
    if args.command == "build":
        result = build_unified(args.assessment, args.clinical, args.reg_events, args.retrieval_eval)
        write_package(result, args.output)
        print(f"CREATED: {args.output} | CLINICAL_GATE: {result['clinical_evidence']['overall_gate_status']} | REGULATORY_CONFORMITY: NOT_ASSESSED | HUMAN_REVIEW: SEPARATE")
    elif args.command == "verify":
        data = _load_json(args.package)
        scope = verify_unified(
            data, assessment_path=args.assessment, clinical_path=args.clinical,
            protocol_path=args.protocol, require_protocol_lock=args.require_protocol_lock,
        )
        events = read_unified_reviews(args.review_log, data)
        print(f"PACKAGE_INTEGRITY: OK | VERIFICATION_SCOPE: {scope} | REVIEW_EVENTS: {len(events)} | CLINICAL_GATE: {data['clinical_evidence']['overall_gate_status']} | RELEASE_DECISION: OUTSIDE_SCOPE")
    else:
        event = append_unified_review(args.package, args.review_log, args.reviewer, args.disposition, args.rationale)
        print(f"REVIEW_EVENT: {event['event_number']} | CLINICAL_GATE_UNCHANGED: {event['observed_clinical_gate']} | DISPOSITION: {event['disposition']}")


if __name__ == "__main__":
    main()
