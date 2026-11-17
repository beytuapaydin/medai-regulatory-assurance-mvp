"""Bridge between existing MedAI v1 document review and v0.2 clinical evaluation.

No compliance verdict and no manufacturer release authorization are generated.
The original eval_engine, gap_report and review_workflow modules remain untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


ALLOWED_CLINICAL = {"PASS", "FAIL", "INSUFFICIENT_EVIDENCE", "NOT_MEASURED"}
REVIEW_CHOICES = {
    "REVIEWED_WITH_FINDINGS", "FOLLOW_UP_REQUIRED", "EVIDENCE_ACCEPTED_FOR_FURTHER_QMS_REVIEW"
}


def _legacy_modules():
    root = Path(__file__).resolve().parents[1]
    old = root / "MedAI_Integrated_v1"
    clinic = root / "clinical_benchmark_v0_2"
    if not (old / "review_workflow.py").is_file() or not (clinic / "src" / "clinical_validation").is_dir():
        raise ValueError("Repository must contain MedAI_Integrated_v1/ and clinical_benchmark_v0_2/ beside medai_unified_v0_3/")
    for folder in (old, clinic):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    import gap_report
    import review_workflow
    from src.clinical_validation.clinical_eval_runner import compute_sha256
    return gap_report, review_workflow, compute_sha256


def _load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _file_sha(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha_json(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _verify_assessment(assessment: dict, legacy: Any) -> None:
    requirements = assessment.get("requirements")
    if not isinstance(requirements, list) or len(requirements) != 13:
        raise ValueError("Expected 13 requirement records in regulatory assessment")
    seen = set()
    for item in requirements:
        rid, content = item.get("requirement_id"), item.get("requirement")
        if not isinstance(rid, str) or not rid or rid in seen:
            raise ValueError("Invalid/duplicate requirement_id")
        seen.add(rid)
        if not isinstance(content, str) or legacy.sha(content) != item.get("requirement_sha256"):
            raise ValueError(f"Requirement text integrity invalid: {rid}")
        ids = set()
        for candidate in item.get("candidates", []):
            doc_id = candidate.get("document_id")
            passage = candidate.get("passage")
            if not doc_id or doc_id in ids or not isinstance(passage, str):
                raise ValueError(f"Invalid candidate ID/passage: {rid}")
            ids.add(doc_id)
            if legacy.sha(passage) != candidate.get("passage_sha256"):
                raise ValueError(f"Candidate passage integrity invalid: {rid}")


def _events(path: str | Path | None, legacy: Any, *, expected_source: str | None = None) -> list[dict]:
    if path is None:
        return []
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Review log missing: {path}")
    prev, events = "GENESIS", []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict) or event.get("event_number") != len(events) + 1:
            raise ValueError(f"Invalid event sequence at line {number}")
        unsigned = {k: v for k, v in event.items() if k != "event_sha256"}
        if unsigned.get("previous_sha256") != prev or legacy.sha(legacy.canonical(unsigned)) != event.get("event_sha256"):
            raise ValueError(f"Regulatory review hash-chain mismatch at line {number}")
        if not isinstance(event.get("source_assessment_sha256"), str):
            raise ValueError(f"Regulatory event lacks source hash at line {number}")
        prev = event["event_sha256"]
        events.append(event)
    return events


def _number(value: Any, *, lo: float = -1.0, hi: float = 1.0) -> bool:
    return type(value) in (int, float) and lo <= value <= hi


def _is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _verify_clinical(clinical: dict, core_sha) -> None:
    """Offline *semantic consistency*, not authentication of underlying model records."""
    if not isinstance(clinical, dict) or clinical.get("schema_version") != "medai-evidence-v0.2":
        raise ValueError("Expected a v0.2-format clinical evidence package")
    unsigned = {k: v for k, v in clinical.items() if k != "artifact_sha256"}
    if core_sha(unsigned) != clinical.get("artifact_sha256"):
        raise ValueError("Clinical artifact SHA-256 mismatch")
    proto = clinical.get("protocol")
    integ = clinical.get("integrity")
    if (not isinstance(proto, dict) or not isinstance(integ, dict)
            or not _is_sha256_hex(proto.get("sha256"))
            or proto.get("sha256") != integ.get("protocol_sha256")):
        raise ValueError("Clinical protocol SHA-256 mismatch or invalid digest")
    overall = clinical.get("overall_gate_status")
    gate = clinical.get("technical_gate")
    findings = clinical.get("statistical_findings")
    if overall not in ALLOWED_CLINICAL or not isinstance(gate, dict) or gate.get("status") not in ALLOWED_CLINICAL:
        raise ValueError("Missing/invalid clinical gate status")
    if not isinstance(findings, dict):
        raise ValueError("Missing statistical findings")
    fails = findings.get("confirmed_demo_threshold_failures")
    insuff = findings.get("evidence_insufficiencies")
    if any(not isinstance(v, list) or any(not isinstance(x, str) for x in v) for v in (fails, insuff)):
        raise ValueError("Malformed clinical statistical findings")
    if gate["status"] == "FAIL" or fails:
        expected = "FAIL"
    elif gate["status"] == "NOT_MEASURED":
        expected = "NOT_MEASURED"
    elif gate["status"] == "INSUFFICIENT_EVIDENCE" or insuff:
        expected = "INSUFFICIENT_EVIDENCE"
    else:
        expected = "PASS"
    if overall != expected:
        raise ValueError(f"Clinical overall_gate_status contradicts underlying gate/statistical findings: expected {expected}, found {overall}")

    # Always inspect cohorts, even when an attacker downgrades FAIL to
    # INSUFFICIENT_EVIDENCE or NOT_MEASURED. Absence cannot hide known failures.
    rules = clinical.get("acceptance_rules")
    cohorts = clinical.get("cohort_evaluations")
    if not isinstance(rules, dict) or not isinstance(cohorts, list) or not cohorts:
        raise ValueError("Clinical evidence requires verifiable acceptance_rules and cohort_evaluations")
    required = rules.get("required_subgroups")
    if (not isinstance(required, list) or not required or "ALL" not in required
            or any(not isinstance(x, str) or not x for x in required)
            or len(required) != len(set(required))):
        raise ValueError("Invalid required_subgroups; must include ALL")
    ids = [c.get("cohort_id") if isinstance(c, dict) else None for c in cohorts]
    if len(ids) != len(required) or set(ids) != set(required) or len(ids) != len(set(ids)):
        raise ValueError("Clinical cohort evaluations do not match required_subgroups")
    for key in ("min_positive_records", "min_negative_records", "min_positive_patients", "min_negative_patients"):
        if type(rules.get(key)) is not int or rules[key] < 1:
            raise ValueError(f"Invalid acceptance rule {key}")
    for key in ("max_sensitivity_drop", "max_critical_fn_rate", "max_specificity_drop"):
        if not _number(rules.get(key), lo=0, hi=1):
            raise ValueError(f"Invalid acceptance threshold {key}")
    margin = rules.get("non_inferiority_margin_sensitivity_delta")
    if not _number(margin) or not -1 < margin < 0:
        raise ValueError("Invalid demonstration non-inferiority margin")

    observed_fail = False
    observed_insuff = False
    any_measured = False
    tol = 1e-9
    for c in cohorts:
        cid = c["cohort_id"]
        m = c.get("basic_metrics")
        ci = c.get("paired_sensitivity_delta_ci")
        if m is None:
            if ci is not None:
                raise ValueError(f"Unmeasured cohort has CI: {cid}")
            observed_insuff = True
            continue
        if not isinstance(m, dict) or type(m.get("measured")) is not bool:
            raise ValueError(f"Malformed cohort metrics: {cid}")
        for key in ("n_total", "n_positive", "n_negative", "n_positive_patients", "n_negative_patients"):
            if type(m.get(key)) is not int or m[key] < 0:
                raise ValueError(f"Invalid cohort counts: {cid} / {key}")
        if m["n_total"] != m["n_positive"] + m["n_negative"]:
            raise ValueError(f"Inconsistent cohort record counts: {cid}")
        if m["n_positive_patients"] > m["n_positive"] or m["n_negative_patients"] > m["n_negative"]:
            raise ValueError(f"Inconsistent independent patient counts: {cid}")
        insufficient_count = any(m[value] < rules[minimum] for value, minimum in (
            ("n_positive", "min_positive_records"),
            ("n_negative", "min_negative_records"),
            ("n_positive_patients", "min_positive_patients"),
            ("n_negative_patients", "min_negative_patients"),
        ))
        if insufficient_count:
            observed_insuff = True
        if m["measured"] is False:
            if ci is not None:
                raise ValueError(f"Unmeasured cohort has paired CI: {cid}")
            observed_insuff = True
            continue
        any_measured = True
        if insufficient_count:
            raise ValueError(f"Measured cohort has insufficient cohort patient/record evidence: {cid}")
        if (c.get("n_distinct_positive_patients") != m["n_positive_patients"]
                or c.get("n_distinct_negative_patients") != m["n_negative_patients"]):
            raise ValueError(f"Inconsistent cohort summary vs basic_metrics patient counts: {cid}")
        for key in ("sensitivity_v1", "sensitivity_v2", "specificity_v1", "specificity_v2", "critical_fn_rate_v2"):
            if not _number(m.get(key), lo=0, hi=1):
                raise ValueError(f"Invalid cohort rate: {cid} / {key}")
        for key in ("sensitivity_drop", "specificity_drop"):
            if not _number(m.get(key)):
                raise ValueError(f"Invalid cohort derived metric: {cid} / {key}")
        expected_derived = {
            "sensitivity_drop": m["sensitivity_v1"] - m["sensitivity_v2"],
            "specificity_drop": m["specificity_v1"] - m["specificity_v2"],
            "critical_fn_rate_v2": 1 - m["sensitivity_v2"],
        }
        if any(abs(m[k] - v) > tol for k, v in expected_derived.items()):
            raise ValueError(f"PASS contradicts observed metric: inconsistent derived metric arithmetic in {cid}")
        for mk, rule in (("sensitivity_drop", "max_sensitivity_drop"),
                         ("specificity_drop", "max_specificity_drop"),
                         ("critical_fn_rate_v2", "max_critical_fn_rate")):
            if m[mk] > rules[rule] + 1e-12:
                observed_fail = True
        if ci is None:
            observed_insuff = True
        else:
            if not isinstance(ci, dict):
                raise ValueError(f"Malformed paired CI in {cid}")
            pt, lo, hi = (ci.get(k) for k in ("point_delta_v2_minus_v1", "ci_lower", "ci_upper"))
            if not all(_number(v) for v in (pt, lo, hi)) or lo > hi:
                raise ValueError(f"Invalid CI bounds in {cid}")
            if abs(pt - (m["sensitivity_v2"] - m["sensitivity_v1"])) > tol:
                raise ValueError(f"Inconsistent paired CI point delta in {cid}")
            if (ci.get("unique_positive_patient_clusters") != m["n_positive_patients"]
                    or ci.get("unique_patient_clusters") != m["n_positive_patients"]):
                raise ValueError(f"Inconsistent bootstrap cluster count vs positive patients in {cid}")
            # Percentile bootstrap intervals need NOT contain the original
            # point estimator; do not incorrectly enforce lo <= pt <= hi.
            if hi < margin:
                observed_fail = True
            elif lo < margin:
                observed_insuff = True
    if observed_fail and overall != "FAIL":
        raise ValueError("FAIL observed in cohort metrics/CI cannot be downgraded")
    if overall == "PASS":
        if observed_insuff:
            raise ValueError("PASS with insufficient cohort patient/record evidence or lacks paired sensitivity confidence interval")
        if not any_measured:
            raise ValueError("PASS without any measured cohorts")
    if overall == "NOT_MEASURED" and any_measured:
        raise ValueError("NOT_MEASURED contradicts measured cohort results")

    if clinical.get("source_type") not in ("SYNTHETIC_ENGINE_TEST", "USER_SUPPLIED_UNVERIFIED"):
        raise ValueError("Unsupported clinical evidence provenance type")
    if clinical.get("manufacturer_release_decision") != "OUTSIDE_PLATFORM_SCOPE":
        raise ValueError("Clinical report must not contain a release authorization")
    if not isinstance(clinical.get("human_review"), dict) or clinical["human_review"].get("technical_result_can_be_overridden") is not False:
        raise ValueError("Clinical gate must not permit human override")
    if clinical.get("source_type") == "SYNTHETIC_ENGINE_TEST" and clinical.get("real_ptbxl_validation_completed") is not False:
        raise ValueError("Synthetic evidence cannot claim completion of real PTB-XL validation")
    trace = clinical.get("traceability")
    if not isinstance(trace, dict) or not isinstance(trace.get("claim_id"), str) or not trace["claim_id"]:
        raise ValueError("Clinical claim ID required")


def _verify_protocol_lock(clinical: dict, protocol_path: str | Path) -> None:
    """Cross-check an independently supplied demonstration protocol, not a self-asserted rule."""
    _legacy_modules()
    from src.clinical_validation.protocol_loader import ProtocolError, load_protocol
    path = Path(protocol_path)
    if not path.is_file():
        raise ValueError(f"Trusted protocol file missing: {path}")
    try:
        locked = load_protocol(path)
    except (ProtocolError, OSError, ValueError, TypeError) as exc:
        raise ValueError(f"Trusted protocol invalid: {exc}") from exc
    proto = clinical.get("protocol", {})
    integ = clinical.get("integrity", {})
    trace = clinical.get("traceability", {})
    if (proto.get("id") != locked.data["protocol_id"]
            or proto.get("version") != locked.data["protocol_version"]
            or proto.get("sha256") != locked.sha256
            or integ.get("protocol_sha256") != locked.sha256):
        raise ValueError("Clinical protocol metadata/SHA-256 does not match locked protocol")
    if (trace.get("claim_id") != locked.data["clinical_claim_id"]
            or trace.get("risk_control_id") != locked.data["risk_control_id"]):
        raise ValueError("Clinical traceability IDs do not match locked protocol")
    expected_rules = {
        **{key: locked.data["rules"][key] for key in (
            "min_positive_records", "min_negative_records",
            "min_positive_patients", "min_negative_patients",
            "max_sensitivity_drop", "max_critical_fn_rate", "max_specificity_drop",
            "non_inferiority_margin_sensitivity_delta",
        )},
        "required_subgroups": list(locked.data["required_subgroups"]),
    }
    if clinical.get("acceptance_rules") != expected_rules:
        raise ValueError("Clinical acceptance_rules or required_subgroups do not match locked protocol")

    # Bootstrap settings are part of the predeclared protocol, not editable
    # result metadata. Reject re-hashed artifacts with cherry-picked seeds,
    # insufficient resamples or narrower confidence intervals.
    locked_rules = locked.data["rules"]
    for cohort in clinical.get("cohort_evaluations", []):
        ci = cohort.get("paired_sensitivity_delta_ci")
        if ci is None:
            continue  # Insufficient/unmeasured cohorts may legitimately lack a CI.
        cid = cohort.get("cohort_id", "UNKNOWN")
        confidence = ci.get("confidence_level")
        requested = ci.get("replicates_requested")
        valid = ci.get("replicates_valid")
        seed = ci.get("seed")
        if (type(confidence) not in (int, float)
                or confidence != locked_rules["bootstrap_confidence_level"]
                or type(requested) is not int or requested != locked_rules["bootstrap_replicates"]
                or type(seed) is not int or seed != locked_rules["bootstrap_seed"]):
            raise ValueError(f"Cohort {cid}: bootstrap parameters do not match locked protocol")
        if (ci.get("method") != "paired_positive_patient_cluster_bootstrap_percentile_exploratory"
                or type(valid) is not int
                or valid < max(200, int(requested * 0.95))
                or valid > requested):
            raise ValueError(f"Cohort {cid}: invalid bootstrap method or replicate count")
        alpha = ci.get("one_sided_non_inferiority_alpha")
        if type(alpha) not in (int, float) or abs(alpha - (1 - confidence) / 2) > 1e-12:
            raise ValueError(f"Cohort {cid}: bootstrap alpha contradicts locked confidence level")


def _verify_regulatory_triage(reg: dict) -> None:
    """Check internal structure; source assessment remains needed for real provenance."""
    from collections import Counter
    if (not isinstance(reg, dict)
        or reg.get("kind") != "DEMONSTRATION_NOT_COMPLIANCE_FINDING"
        or reg.get("interpretation") != "Retrieval candidates and reviewer opinions; not technical compliance or certification"):
        raise ValueError("Invalid regulatory_document_triage scope")
    rows = reg.get("requirements")
    if not isinstance(rows, list) or len(rows) != 13 or reg.get("requirement_count") != 13:
        raise ValueError("Invalid regulatory_document_triage requirements/count")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid regulatory_document_triage requirement record")
        rid = row.get("requirement_id")
        digest = row.get("requirement_sha256")
        state = row.get("evidence_review_state")
        if not isinstance(rid, str) or not rid or rid in seen:
            raise ValueError("Invalid regulatory_document_triage requirement IDs")
        seen.add(rid)
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError("Invalid regulatory_document_triage requirement digest")
        if state not in {
            'PENDING_REVIEW', 'NO_CANDIDATE_REVIEW_NEEDED', 'CANDIDATE_REJECTED',
            'REVIEW_UNCERTAIN', 'REVIEWER_REPORTS_INSUFFICIENT', 'REVIEWER_REPORTS_PARTIAL',
            'REVIEWER_CONSIDERS_SUFFICIENT_NOT_APPROVED', 'RELEVANT_SUFFICIENCY_NOT_ASSESSED',
        }:
            raise ValueError("Invalid regulatory_document_triage evidence state")
        if type(row.get('candidate_count')) is not int or row['candidate_count'] < 0:
            raise ValueError("Invalid regulatory_document_triage candidate count")
        if row.get('selected_document') is not None and row['candidate_count'] == 0:
            raise ValueError("Invalid regulatory_document_triage selected candidate")
        if state == 'REVIEWER_CONSIDERS_SUFFICIENT_NOT_APPROVED' and not row.get('human_review_event_sha256'):
            raise ValueError("Regulatory reviewer opinion missing review reference")
    if reg.get('states') != dict(Counter(row['evidence_review_state'] for row in rows)):
        raise ValueError("Inconsistent regulatory_document_triage state counts")
    review_count = sum(bool(row.get('human_review_event_sha256')) for row in rows)
    if type(reg.get('current_human_reviews')) is not int or reg['current_human_reviews'] != review_count:
        raise ValueError("Inconsistent regulatory_document_triage human review count")
    if type(reg.get('stale_source_review_events')) is not int or reg['stale_source_review_events'] < 0:
        raise ValueError("Invalid regulatory_document_triage stale review count")


def build_unified(assessment_path: str | Path, clinical_path: str | Path,
                  regulatory_events_path: str | Path | None = None,
                  retrieval_eval_path: str | Path | None = None) -> dict:
    """Deterministic snapshot of two *separate* evidence domains; never a compliance verdict."""
    gap_report, legacy, core_sha = _legacy_modules()
    assessment = _load_json(assessment_path)
    _verify_assessment(assessment, legacy)
    clinical = _load_json(clinical_path)
    _verify_clinical(clinical, core_sha)
    # Matches the canonical assessment digest computed by the unmodified review_workflow.read_source.
    source_text = Path(assessment_path).read_text(encoding="utf-8-sig")
    source_digest = legacy.sha(source_text)
    events = _events(regulatory_events_path, legacy)
    doc_report = gap_report.build_report(assessment, events, source_digest)
    review_rows = [{
        "requirement_id": r["requirement_id"], "requirement_sha256": r["requirement_sha256"],
        "evidence_review_state": r["state"], "candidate_count": r["candidate_count"],
        "selected_document": r["selected_document"],
        "human_review_event_sha256": r["review_event_sha256"],
        "reviewer_sufficiency_opinion": r["evidence_sufficiency_review"],
        "next_action_origin": r["action_origin"], "next_action": r["required_action"],
    } for r in doc_report["rows"]]
    retrieval = {"state": "NOT_PROVIDED", "note": "eval_engine.py benchmark is separate from regulatory conformity"}
    if retrieval_eval_path is not None:
        ev = _load_json(retrieval_eval_path)
        if ev.get("benchmark_status") not in ("EVALUABLE", "NOT_MEASURED"):
            raise ValueError("Invalid retrieval benchmark state")
        retrieval = {
            "state": ev["benchmark_status"],
            "expert_validated_pairs": ev.get("annotation_summary", {}).get("expert_validated_pairs"),
            "fully_expert_labeled_requirements": ev.get("fully_expert_labeled_requirements", []),
            "source_file_sha256": _file_sha(retrieval_eval_path),
            "note": "Retrieval quality, not evidence sufficiency or MDR conformity",
        }
    payload = {
        "schema_version": "medai-unified-evidence-v0.3",
        "intended_use": "Engineering QA/RA evidence preparation, no diagnosis, no legal conformity conclusion",
        "source_provenance": {
            "regulatory_assessment_file_sha256": _file_sha(assessment_path),
            "regulatory_assessment_text_sha256": source_digest,
            "regulatory_review_log_file_sha256": _file_sha(regulatory_events_path) if regulatory_events_path else None,
            "clinical_evidence_file_sha256": _file_sha(clinical_path),
        },
        "regulatory_document_triage": {
            "kind": doc_report["kind"],
            "requirement_count": doc_report["requirement_count"],
            "current_human_reviews": doc_report["current_human_reviews"],
            "stale_source_review_events": doc_report["historical_events_with_different_source"],
            "states": doc_report["counts_by_review_state"],
            "requirements": review_rows,
            "interpretation": "Retrieval candidates and reviewer opinions; not technical compliance or certification",
        },
        "retrieval_quality_benchmark": retrieval,
        "cross_domain_traceability": {
            "state": "NOT_ESTABLISHED",
            "clinical_claim_id": clinical["traceability"]["claim_id"],
            "clinical_risk_control_id": clinical["traceability"].get("risk_control_id"),
            "matched_regulatory_requirement_ids": [],
            "reason": "Original documentary triage concerns 13 MDR Article 10(9) requirements, not validated links to this clinical claim or risk control.",
        },
        "clinical_evidence": clinical,
        "evidence_domains_are_independent": True,
        "technical_gate_result_is_not_reviewer_approval": True,
        "unified_human_review": {"state": "NO_REVIEW_RECORDED_IN_THIS_SNAPSHOT", "event_log_separate": True},
        "manufacturer_release_decision": "OUTSIDE_PLATFORM_SCOPE",
        "limitations": [
            "Clinical source may be entirely synthetic; not evidence of real PTB-XL model validity.",
            "Regulatory document triage is not MDR conformity, evidence sufficiency or clinical risk approval.",
            "Package and review event SHA-256 checksums detect change, but do not provide immutable storage, identity verification or trusted timestamps.",
            "No combined PASS is calculated; technical findings and human review retain distinct scopes.",
        ],
    }
    payload["package_sha256"] = _sha_json(payload)
    return payload


def verify_unified(package: dict, *, assessment_path: str | Path | None = None,
                   clinical_path: str | Path | None = None,
                   protocol_path: str | Path | None = None,
                   require_protocol_lock: bool = False) -> str:
    """Self-consistency check; optionally bind to independently supplied input files.

    Neither mode authenticates the origin of a newly reissued, self-consistent
    package. For authenticity, use separately trusted signed provenance.
    """
    if require_protocol_lock and protocol_path is None:
        raise ValueError("Protocol-locked verification requires a trusted --protocol file")
    _, _, core_sha = _legacy_modules()
    if package.get("schema_version") != "medai-unified-evidence-v0.3":
        raise ValueError("Unknown unified package schema")
    unsigned = {k: v for k, v in package.items() if k != "package_sha256"}
    if _sha_json(unsigned) != package.get("package_sha256"):
        raise ValueError("Unified package SHA-256 mismatch")
    _verify_clinical(package.get("clinical_evidence"), core_sha)
    if protocol_path is not None:
        _verify_protocol_lock(package["clinical_evidence"], protocol_path)
    _verify_regulatory_triage(package.get("regulatory_document_triage"))
    if package.get("manufacturer_release_decision") != "OUTSIDE_PLATFORM_SCOPE":
        raise ValueError("Package cannot authorize a release")
    if package.get("evidence_domains_are_independent") is not True:
        raise ValueError("Evidence separation must be maintained")
    trace = package.get("cross_domain_traceability", {})
    if trace.get("state") != "NOT_ESTABLISHED" or trace.get("matched_regulatory_requirement_ids") != []:
        raise ValueError("Unverified clinical-regulatory cross-links are not permitted")
    provenance = package.get("source_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("Missing source_provenance")
    if assessment_path is not None:
        _, legacy, _ = _legacy_modules()
        if _file_sha(assessment_path) != provenance.get("regulatory_assessment_file_sha256"):
            raise ValueError("Source assessment raw SHA-256 mismatch")
        source_text = Path(assessment_path).read_text(encoding="utf-8-sig")
        if legacy.sha(source_text) != provenance.get("regulatory_assessment_text_sha256"):
            raise ValueError("Source assessment text SHA-256 mismatch")
        _verify_assessment(_load_json(assessment_path), legacy)
    if clinical_path is not None:
        if _file_sha(clinical_path) != provenance.get("clinical_evidence_file_sha256"):
            raise ValueError("Source clinical raw SHA-256 mismatch")
        if _load_json(clinical_path) != package["clinical_evidence"]:
            raise ValueError("Source clinical content differs from unified clinical evidence")
    if protocol_path is not None and assessment_path is not None and clinical_path is not None:
        return "PROTOCOL_AND_INPUT_FILES_LOCKED"
    if protocol_path is not None:
        return "PROTOCOL_LOCKED"
    if assessment_path is not None and clinical_path is not None:
        return "INPUT_FILES_MATCH"
    return "SELF_CONSISTENCY_ONLY"


def read_unified_reviews(log_path: str | Path | None, package: dict) -> list[dict]:
    if log_path is None or not Path(log_path).exists():
        return []
    if not Path(log_path).is_file():
        raise ValueError("Invalid review log path")
    events, prev = [], "GENESIS"
    for ln, line in enumerate(Path(log_path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        e = json.loads(line)
        unsigned = {k: v for k, v in e.items() if k != "event_sha256"}
        if (e.get("event_number") != len(events) + 1 or e.get("previous_sha256") != prev
            or _sha_json(unsigned) != e.get("event_sha256")
            or e.get("package_sha256") != package["package_sha256"]
            or e.get("observed_clinical_gate") != package["clinical_evidence"]["overall_gate_status"]
            or e.get("decision_scope") != "EVIDENCE_REVIEW_ONLY_NO_QMS_RELEASE"
            or e.get("disposition") not in REVIEW_CHOICES):
            raise ValueError(f"Unified review log integrity/scope failure at line {ln}")
        events.append(e)
        prev = e["event_sha256"]
    return events


def append_unified_review(package_path: str | Path, log_path: str | Path, reviewer: str,
                          disposition: str, rationale: str) -> dict:
    package = _load_json(package_path)
    verify_unified(package)
    if disposition not in REVIEW_CHOICES:
        raise ValueError("Unsupported reviewer disposition")
    if not (2 <= len(reviewer.strip()) <= 100 and 15 <= len(rationale.strip()) <= 4000):
        raise ValueError("Reviewer must be 2–100 chars and rationale 15–4000 chars")
    events = read_unified_reviews(log_path, package)
    event = {
        "event_number": len(events) + 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "package_sha256": package["package_sha256"],
        "observed_clinical_gate": package["clinical_evidence"]["overall_gate_status"],
        "reviewer_unverified_local_identifier": reviewer.strip(),
        "disposition": disposition,
        "rationale": rationale.strip(),
        "decision_scope": "EVIDENCE_REVIEW_ONLY_NO_QMS_RELEASE",
        "previous_sha256": events[-1]["event_sha256"] if events else "GENESIS",
    }
    event["event_sha256"] = _sha_json(event)
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return event


def write_package(package: dict, output: str | Path) -> Path:
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite existing evidence package: {out}")
    out.write_text(json.dumps(package, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return out
