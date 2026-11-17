#!/usr/bin/env python3
"""MedAI v0.5: independently regenerated, research-only model-change assessment.

Depends on the already-installed medai_real_evidence_v04.py (same directory).
No third-party imports, no fold-10 access, no clinical/release approval.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
from pathlib import Path
from typing import Any

import medai_real_evidence_v04 as upstream

SCHEMA = "medai-model-change-assurance-v0.5"
FILE_JSON = "model_change_assessment.json"
FILE_MD = "model_change_report.md"
FILE_HTML = "model_change_report.html"
MODELS = ("baseline", "candidate")


class ChangeError(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ChangeError(reason)


def digest(path: Path) -> str:
    return upstream.file_sha(path)


def doc_digest(obj: Any) -> str:
    return upstream.doc_sha(obj)


def read_json(path: Path) -> Any:
    return upstream.json_file(path)


def exact_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def original_paths(root: Path, protocol: Path) -> dict[str, Path]:
    pilot = root / "benchmark_v1" / "pilot_v1"
    return {
        "pilot_train": pilot / "pilot_train.json",
        "pilot_validation": pilot / "pilot_validation.json",
        "pilot_manifest": pilot / "pilot_manifest.json",
        "models": pilot / "model_v1" / "models.json",
        "pilot_model_report": pilot / "model_v1" / "pilot_model_report.json",
        "validation_predictions": pilot / "model_v1" / "validation_predictions.csv",
        "oof_report": pilot / "oof_thresholds_v1" / "oof_threshold_development_report.json",
        "training_oof_predictions": pilot / "oof_thresholds_v1" / "training_oof_predictions.csv",
        "v04_evidence": pilot / "real_evidence_v04" / "research_evidence.json",
        "protocol": protocol,
    }


def verify_inventory(inventory: Path, root: Path, protocol: Path) -> dict:
    """Compare 10 CSV entries with real files, not merely CSV row count."""
    require(inventory.is_file(), f"Required SHA-256 inventory not found: {inventory}")
    expected = original_paths(root, protocol)
    paths_to_keys = {exact_path(p): name for name, p in expected.items()}
    require(len(paths_to_keys) == len(expected), "Duplicated expected snapshot paths")
    observed: dict[str, str] = {}
    with inventory.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == ["Path", "Hash"], "Invalid inventory CSV header")
        for row in reader:
            require(set(row) == {"Path", "Hash"} and all(row.values()), "Malformed inventory CSV row")
            p = exact_path(row["Path"])
            require(p in paths_to_keys, "Unexpected path in inventory")
            name = paths_to_keys[p]
            require(name not in observed, "Duplicate inventory entry")
            sha = row["Hash"].strip().lower()
            require(len(sha) == 64 and all(ch in "0123456789abcdef" for ch in sha),
                    "Invalid inventory digest")
            require(p.is_file(), f"Inventory source missing: {name}")
            require(digest(p) == sha, f"Inventory hash mismatch: {name}")
            observed[name] = sha
    require(set(observed) == set(expected),
            f"Inventory incomplete: missing {sorted(set(expected) - set(observed))}")
    return {"status": "MATCHES_10_LOCAL_FILES", "files_verified": len(observed),
            "inventory_sha256": digest(inventory),
            "qualification": "LOCAL_INTEGRITY_ONLY_NOT_SIGNED_OR_IMMUTABLE"}


def finite_number(value: Any, label: str) -> float:
    require(type(value) in (int, float) and math.isfinite(value), f"Invalid numeric {label}")
    return float(value)


def delta(new: Any, old: Any) -> float | None:
    if new is None or old is None:
        return None
    return round(finite_number(new, "new metric") - finite_number(old, "old metric"), 12)


def rank_auroc(labels: list[int], probs: list[float]) -> float | None:
    """Rank-based AUROC, ties counted as 0.5; descriptive estimate only."""
    require(len(labels) == len(probs), "Invalid AUROC inputs")
    positives = [p for y, p in zip(labels, probs) if y == 1]
    negatives = [p for y, p in zip(labels, probs) if y == 0]
    require(all(y in (0, 1) for y in labels), "Invalid AUROC labels")
    if not positives or not negatives:
        return None
    return sum((p > n) + .5 * (p == n) for p in positives for n in negatives) / (
        len(positives) * len(negatives))


def ranking_metrics(root: Path, protocol: Path) -> dict:
    """Compute AUROC from hash-verified prior fold-9 CSV, without opening fold 10."""
    path = original_paths(root, protocol)["validation_predictions"]
    columns = ("ecg_id", "patient_id", "strat_fold", "age", "y_true",
               "baseline_probability", "baseline_pred", "candidate_probability", "candidate_pred")
    records = upstream.read_csv(path, columns)
    labels = [int(row["y_true"]) for row in records]
    a = [upstream.score(row["baseline_probability"]) for row in records]
    b = [upstream.score(row["candidate_probability"]) for row in records]
    base = rank_auroc(labels, a)
    new = rank_auroc(labels, b)
    return {"baseline_auroc": base, "candidate_auroc": new,
            "delta_candidate_minus_baseline": delta(new, base),
            "scope": "FOLD9_PREVIOUSLY_INSPECTED_DEVELOPMENT_ONLY"}


def compare_metrics(base: dict, candidate: dict) -> dict:
    required = ("n", "tp", "fn", "fp", "tn", "sensitivity", "specificity")
    for model, result in (("baseline", base), ("candidate", candidate)):
        require(isinstance(result, dict) and all(x in result for x in required),
                f"Missing model metrics: {model}")
        for name in ("tp", "fn", "fp", "tn", "n"):
            require(type(result[name]) is int and result[name] >= 0,
                    f"Malformed count: {model}/{name}")
        require(result["tp"] + result["fn"] + result["fp"] + result["tn"] == result["n"],
                f"Nonconserving confusion matrix: {model}")
    require(base["n"] == candidate["n"] and base["tp"] + base["fn"] ==
            candidate["tp"] + candidate["fn"], "Unpaired validation cohorts")
    return {"baseline": {key: base[key] for key in required},
            "candidate": {key: candidate[key] for key in required},
            "delta_candidate_minus_baseline": {
                "tp": candidate["tp"] - base["tp"],
                "fn": candidate["fn"] - base["fn"],
                "fp": candidate["fp"] - base["fp"],
                "tn": candidate["tn"] - base["tn"],
                "sensitivity": delta(candidate["sensitivity"], base["sensitivity"]),
                "specificity": delta(candidate["specificity"], base["specificity"]),
            }}


def build(root: Path, protocol: Path, inventory: Path, package_path: Path) -> dict:
    """Fail closed: re-verify original evidence, protocol, sources and CSV hash snapshot."""
    root, protocol, inventory, package_path = map(exact_path, (root, protocol, inventory, package_path))
    required_package = original_paths(root, protocol)["v04_evidence"].resolve()
    require(package_path == required_package, "v0.4 package path must be the known pilot evidence path")
    require(package_path.is_file(), "v0.4 evidence package missing")
    v04 = read_json(package_path)
    upstream.verify(v04, root, protocol)  # recomputes all source metrics + selected waveform SHA-256
    require(v04.get("schema_version") == upstream.SCHEMA, "Unsupported v0.4 schema")
    require(v04.get("clinical_gate") == "NOT_EVALUATED" and
            v04.get("release_decision") == "OUTSIDE_PLATFORM_SCOPE" and
            v04.get("status") == "RESEARCH_EVIDENCE_ONLY" and
            v04.get("real_ptbxl_independent_clinical_validation") is False,
            "Upstream evidence incorrectly claims clinical approval")
    require(v04.get("dataset", {}).get("test_fold_10") == "NOT_ACCESSED_BY_THIS_ADAPTER",
            "Upstream fold-10 claim unexpected")
    verified_inventory = verify_inventory(inventory, root, protocol)
    definitions = read_json(original_paths(root, protocol)["models"])
    require(isinstance(definitions, dict) and set(definitions) == set(MODELS),
            "Unexpected model definitions")
    model_info: dict[str, dict] = {}
    for name in MODELS:
        definition = definitions[name]
        require(isinstance(definition, dict) and definition.get("type") == "l2_logistic_regression",
                "Unexpected model class")
        penalty = definition.get("l2_penalty")
        require(penalty is None or (type(penalty) in (int, float) and math.isfinite(penalty)
                and penalty >= 0), "Invalid L2 penalty in models.json")
        weights = definition.get("weights")
        require(weights is None or (isinstance(weights, list) and len(weights) == 72
                and all(type(w) in (int, float) and math.isfinite(w) for w in weights)),
                "Unexpected model weights or feature dimension")
        source_model = v04.get("models", {}).get(name)
        require(isinstance(source_model, dict), "Missing v0.4 model metrics")
        model_info[name] = {"model_type": "l2_logistic_regression",
                            "feature_count": len(weights) if weights is not None else None,
                            "l2_penalty": penalty,
                            "configuration_completeness": "REPORTED" if penalty is not None
                            and weights is not None else "INCOMPLETE_IN_MODEL_ARTIFACT",
                            "training_oof_threshold": source_model["oof_training_selection"]["threshold"]}
    whole = compare_metrics(v04["models"]["baseline"]["fold9_development_only"],
                            v04["models"]["candidate"]["fold9_development_only"])
    train_oof = compare_metrics(v04["models"]["baseline"]["oof_training_selection"],
                                v04["models"]["candidate"]["oof_training_selection"])
    groups = v04.get("subgroups")
    require(isinstance(groups, list) and {g.get("cohort_id") for g in groups} ==
            {"ALL", "AGE75_PLUS"} and len(groups) == 2, "Missing required subgroups")
    subgroup_reports: list[dict] = []
    for group in groups:
        evaluations = group["diagnostic_only_previously_inspected_fold9"]
        require(set(evaluations) == set(MODELS), "Incomplete subgroup model comparison")
        subgroup_reports.append({
            "cohort_id": group["cohort_id"],
            "counts": group["counts"],
            "demo_count_adequacy": group["sample_adequacy_for_demonstration_rules"],
            "sample_shortfalls": group["sample_shortfalls"],
            "development_only_model_comparison": compare_metrics(evaluations["baseline"],
                                                                  evaluations["candidate"]),
        })
    by_group = {g["cohort_id"]: g for g in subgroup_reports}
    require(by_group["ALL"]["development_only_model_comparison"] == whole,
            "ALL cohort metrics do not match model metrics")
    shortfalls = [f'{g["cohort_id"]}: {reason}' for g in subgroup_reports
                  for reason in g["sample_shortfalls"]]
    # Warning, not a formal risk score and not a clinical acceptance decision.
    risk_findings = [
        {"id": "OBS-01", "severity": "EVIDENCE_GAP", "title": "Independent holdout not evaluated",
         "description": "Fold 9 was repeatedly inspected for development; fold 10 was not accessed."},
        {"id": "OBS-02", "severity": "EVIDENCE_GAP", "title": "Non-random selection",
         "description": "Subset consists of files available when ordered download was interrupted."},
        {"id": "OBS-03", "severity": "PERFORMANCE_CONCERN", "title": "Missed MI-labelled records",
         "description": (f'Fold-9 development-only: baseline FN={whole["baseline"]["fn"]}, '
                         f'candidate FN={whole["candidate"]["fn"]}; not a clinical estimate.')},
        {"id": "OBS-04", "severity": "EVIDENCE_GAP", "title": "Unquantified model-change uncertainty",
         "description": "No patient-cluster confidence intervals or multiplicity assessment."},
        {"id": "OBS-05", "severity": "EVIDENCE_GAP", "title": "Prediction regeneration not assessed",
         "description": "Existing predictions and models are hash-checked; v0.5 does not retrain/re-run predictions."},
    ]
    if shortfalls:
        risk_findings.append({"id": "OBS-06", "severity": "EVIDENCE_GAP",
                              "title": "Demonstration cohort size shortfall",
                              "description": "; ".join(shortfalls)})
    result = {
        "schema_version": SCHEMA,
        "status": "RESEARCH_MODEL_CHANGE_REPORT_ONLY",
        "comparison": "baseline_to_candidate",
        "dataset": {"name": "PTB-XL", "version": "1.0.3", "sample": "CONVENIENCE_SAMPLE",
                    "train_records": v04["sample"]["training_records"],
                    "validation_records": v04["sample"]["validation_records"],
                    "validation_data_role": "PREVIOUSLY_INSPECTED_DEVELOPMENT_ONLY",
                    "fold10": "NOT_ACCESSED_BY_THIS_ASSESSMENT"},
        "protocol": {"id": v04["trusted_protocol"]["id"],
                     "version": v04["trusted_protocol"]["version"],
                     "sha256": digest(protocol),
                     "claim_id": v04["trusted_protocol"]["claim_id"],
                     "risk_control_id": v04["trusted_protocol"]["risk_control_id"],
                     "scope": "DEMONSTRATION_ONLY"},
        "integrity": {"upstream_package_file_sha256": digest(package_path),
                      "upstream_artifact_sha256": v04["artifact_sha256"],
                      "upstream_verification": "RECOMPUTED_FROM_SOURCES_AND_LOCKED_PROTOCOL",
                      "audit_inventory": verified_inventory,
                      "waveform_files_sha256_checked_by_upstream":
                          v04["source_integrity"]["waveform_files_checked"],
                      "limitations": "HASHES_DO_NOT_PROVE_AUTHENTICITY_OR_IMMUTABLE_STORAGE"},
        "models": model_info,
        "training_oof_development": train_oof,
        "previously_inspected_fold9": whole,
        "ranking_diagnostic_auroc": ranking_metrics(root, protocol),
        "subgroups": subgroup_reports,
        "findings": risk_findings,
        "sample_shortfalls": shortfalls,
        "evaluation_conclusion": "CLINICAL_MODEL_CHANGE_BENEFIT_NOT_ESTABLISHED",
        "evidence_adequacy": v04["evidence_adequacy"],
        "clinical_gate": "NOT_EVALUATED",
        "independent_clinical_validation": False,
        "release_decision": "OUTSIDE_PLATFORM_SCOPE",
        "human_review": "REQUIRED_FOR_INTERPRETATION_CANNOT_OVERRIDE_MISSING_EVIDENCE",
        "limitations": [
            "Development-only thresholds were derived on train OOF; selection metrics are not independent.",
            "Fold 9 was previously inspected; deltas cannot demonstrate generalizable benefit.",
            "Demo count criteria do not constitute clinical acceptance criteria.",
            "This comparison is descriptive; paired patient-cluster uncertainty is unmeasured.",
            "The platform does not make diagnoses, CE/MDR conformity, or QMS release decisions.",
        ],
    }
    result["assessment_sha256"] = doc_digest(result)
    return result


def fmt_pct(x: Any) -> str:
    return "N/A" if x is None else f"{float(x) * 100:.1f}%"


def signed_pp(x: Any) -> str:
    return "N/A" if x is None else f"{float(x) * 100:+.1f} pp"


def render_markdown(report: dict) -> str:
    s = report["previously_inspected_fold9"]
    d = s["delta_candidate_minus_baseline"]
    lines = [
        "# MedAI Assurance v0.5 — Model Change Assessment",
        "",
        "**RESEARCH / DEVELOPMENT ONLY — NOT A CLINICAL VALIDATION**",
        "",
        "**Change:** baseline → candidate | **Dataset:** PTB-XL 1.0.3 (non-random pilot)",
        "",
        "**Assessment:** CLINICAL_MODEL_CHANGE_BENEFIT_NOT_ESTABLISHED. "
        "Clinical gate: NOT_EVALUATED. Release decision: OUTSIDE_PLATFORM_SCOPE.",
        "",
        "## Development-only fold 9 comparison (previously inspected)", "",
        "| Metric | Baseline | Candidate | Delta |", "|---|---:|---:|---:|",
        f'| Sensitivity | {fmt_pct(s["baseline"]["sensitivity"])} | '
        f'{fmt_pct(s["candidate"]["sensitivity"])} | {signed_pp(d["sensitivity"])} |',
        f'| Specificity | {fmt_pct(s["baseline"]["specificity"])} | '
        f'{fmt_pct(s["candidate"]["specificity"])} | {signed_pp(d["specificity"])} |',
        f'| AUROC (ranking) | {report["ranking_diagnostic_auroc"]["baseline_auroc"]:.3f} | '
        f'{report["ranking_diagnostic_auroc"]["candidate_auroc"]:.3f} | '
        f'{report["ranking_diagnostic_auroc"]["delta_candidate_minus_baseline"]:+.3f} |',
        f'| True positives | {s["baseline"]["tp"]} | {s["candidate"]["tp"]} | {d["tp"]:+d} |',
        f'| False negatives | {s["baseline"]["fn"]} | {s["candidate"]["fn"]} | {d["fn"]:+d} |',
        f'| False positives | {s["baseline"]["fp"]} | {s["candidate"]["fp"]} | {d["fp"]:+d} |',
        "", "**Interpretation:** These are exploratory paired point estimates, not independent "
        "validation, statistical non-inferiority, or a clinical risk acceptance result.",
        "", "## Model configuration", "",
        f'- Baseline: L2 penalty {report["models"]["baseline"]["l2_penalty"]}; '
        f'OOF threshold {report["models"]["baseline"]["training_oof_threshold"]:.6f}',
        f'- Candidate: L2 penalty {report["models"]["candidate"]["l2_penalty"]}; '
        f'OOF threshold {report["models"]["candidate"]["training_oof_threshold"]:.6f}',
        "", "## Required subgroups", "",
    ]
    for cohort in report["subgroups"]:
        counts = cohort["counts"]
        cmp = cohort["development_only_model_comparison"]
        lines.extend([
            f'### {cohort["cohort_id"]}', "",
            f'- Positive/negative patients: {counts["n_positive_patients"]} / '
            f'{counts["n_negative_patients"]}',
            f'- Demo count adequacy: {cohort["demo_count_adequacy"]}',
            f'- Sensitivity: {fmt_pct(cmp["baseline"]["sensitivity"])} → '
            f'{fmt_pct(cmp["candidate"]["sensitivity"])}',
            f'- Specificity: {fmt_pct(cmp["baseline"]["specificity"])} → '
            f'{fmt_pct(cmp["candidate"]["specificity"])}',
        ])
        for shortfall in cohort["sample_shortfalls"]:
            lines.append(f'- Shortfall: {shortfall}')
        lines.append("")
    lines.extend(["## Evidence provenance and integrity", "",
                  f'- v0.4 evidence SHA-256: `{report["integrity"]["upstream_package_file_sha256"]}`',
                  f'- Locked protocol SHA-256: `{report["protocol"]["sha256"]}`',
                  f'- Snapshot CSV SHA-256: `{report["integrity"]["audit_inventory"]["inventory_sha256"]}`',
                  f'- Snapshot files rechecked: {report["integrity"]["audit_inventory"]["files_verified"]}',
                  f'- Waveform files rechecked by v0.4: '
                  f'{report["integrity"]["waveform_files_sha256_checked_by_upstream"]}',
                  "- Cryptographic authenticity and immutable custody: NOT ESTABLISHED", "",
                  "## Findings", ""])
    for item in report["findings"]:
        lines.append(f'- **{item["id"]} · {item["severity"]} · {item["title"]}:** '
                     f'{item["description"]}')
    lines.extend(["", "## Interpretation and restrictions", ""])
    for limitation in report["limitations"]:
        lines.append(f'- {limitation}')
    lines.extend(["", "Human expert review required; cannot change verified technical findings. "
                  "No patient-level identifiers are included in this report.", "",
                  f'Assessment SHA-256: `{report["assessment_sha256"]}`', ""])
    return "\n".join(lines)


def render_html(report: dict) -> str:
    """Offline, printable report. Escape all variable text; no external assets or scripts."""
    h = lambda s: html.escape(str(s), quote=True)
    cmp = report["previously_inspected_fold9"]
    delta_cmp = cmp["delta_candidate_minus_baseline"]
    rows = [
        ("Sensitivity", fmt_pct(cmp["baseline"]["sensitivity"]),
         fmt_pct(cmp["candidate"]["sensitivity"]), signed_pp(delta_cmp["sensitivity"])),
        ("Specificity", fmt_pct(cmp["baseline"]["specificity"]),
         fmt_pct(cmp["candidate"]["specificity"]), signed_pp(delta_cmp["specificity"])),
        ("AUROC (ranking)", f'{report["ranking_diagnostic_auroc"]["baseline_auroc"]:.3f}',
         f'{report["ranking_diagnostic_auroc"]["candidate_auroc"]:.3f}',
         f'{report["ranking_diagnostic_auroc"]["delta_candidate_minus_baseline"]:+.3f}'),
        ("True positives", cmp["baseline"]["tp"], cmp["candidate"]["tp"],
         f'{delta_cmp["tp"]:+d}'),
        ("False negatives", cmp["baseline"]["fn"], cmp["candidate"]["fn"],
         f'{delta_cmp["fn"]:+d}'),
        ("False positives", cmp["baseline"]["fp"], cmp["candidate"]["fp"],
         f'{delta_cmp["fp"]:+d}'),
    ]
    metric_rows = "\n".join("<tr>" + "".join(f"<td>{h(col)}</td>" for col in row) + "</tr>" for row in rows)
    subgroup_cards = []
    for subgroup in report["subgroups"]:
        c = subgroup["counts"]
        subgroup_cmp = subgroup["development_only_model_comparison"]
        caution = subgroup["demo_count_adequacy"] == "INSUFFICIENT_EVIDENCE"
        shortfalls = "".join(f"<li>{h(x)}</li>" for x in subgroup["sample_shortfalls"])
        subgroup_cards.append(f'''<section class="sub-card"><div class="sub-heading"><h3>{h(subgroup["cohort_id"])}</h3>
        <strong class="{'bad' if caution else 'neutral'}">{h(subgroup["demo_count_adequacy"])}</strong></div>
        <p>Positive / negative patients: <b>{c["n_positive_patients"]} / {c["n_negative_patients"]}</b></p>
        <p>Development-only sensitivity: {h(fmt_pct(subgroup_cmp["baseline"]["sensitivity"]))} →
        {h(fmt_pct(subgroup_cmp["candidate"]["sensitivity"]))}</p>
        <p>Development-only specificity: {h(fmt_pct(subgroup_cmp["baseline"]["specificity"]))} →
        {h(fmt_pct(subgroup_cmp["candidate"]["specificity"]))}</p><ul>{shortfalls}</ul></section>''')
    finding_html = "\n".join(f'<li><b>{h(x["id"])} — {h(x["title"])}</b><br>{h(x["description"])}</li>'
                             for x in report["findings"])
    limits = "\n".join(f'<li>{h(item)}</li>' for item in report["limitations"])
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MedAI v0.5 — Model Change Assurance (research)</title>
<style>
:root{{--ink:#142239;--muted:#526377;--paper:#f2f5fa;--line:#dae2ec;--navy:#152a48;--red:#ae3e34;--amber:#926018;}}
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.56 system-ui,'Segoe UI',Arial,sans-serif;color:var(--ink);background:var(--paper)}}
main{{max-width:980px;margin:36px auto;background:#fff;box-shadow:0 12px 42px #14223914;border:1px solid var(--line);border-radius:14px;overflow:hidden}}
header{{background:var(--navy);color:#fff;padding:35px 42px}}header small{{text-transform:uppercase;letter-spacing:.15em;color:#b8c9df}}
h1{{font-size:31px;line-height:1.15;margin:12px 0}}header p{{color:#d5deec;max-width:660px}}
.content{{padding:30px 42px 40px}}.tag{{display:inline-block;border-radius:20px;padding:4px 11px;background:#fff2e8;color:#8e421b;font-size:12px;font-weight:700}}
.block{{border-top:1px solid var(--line);margin-top:26px;padding-top:22px}}h2{{font-size:19px;margin:0 0 14px}}h3{{font-size:16px;margin:0 0 6px}}
.details{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:18px 0}}
.stat{{padding:14px;border:1px solid var(--line);border-radius:10px}}.stat small{{display:block;color:var(--muted)}}.stat strong{{display:block;font-size:19px;overflow-wrap:anywhere}}
table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid var(--line);padding:11px 9px;text-align:left}}th{{background:#f6f8fb;font-size:12px;color:var(--muted)}}td:not(:first-child){{font-variant-numeric:tabular-nums}}
.subs{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.sub-card{{border:1px solid var(--line);border-radius:12px;padding:18px}}
.sub-heading{{display:flex;justify-content:space-between;gap:9px;flex-wrap:wrap}}.sub-heading strong{{font-size:10px;letter-spacing:.03em}}
.bad{{color:var(--red)}}.neutral{{color:var(--amber)}}ul{{padding-left:21px}}li{{margin:7px 0}}.note{{background:#f8fafc;border-left:3px solid var(--amber);padding:12px 15px}}
.hash{{font:12px/1.7 ui-monospace,Consolas,monospace;overflow-wrap:anywhere}}footer{{color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding:18px 42px}}
@media(max-width:680px){{main{{margin:0;border-radius:0}}header,.content,footer{{padding:25px 20px}}.details,.subs{{grid-template-columns:1fr}}h1{{font-size:25px}}}}
@media print{{body{{background:white}}main{{box-shadow:none;border:0;margin:0}}header{{print-color-adjust:exact;-webkit-print-color-adjust:exact}}.block{{break-inside:avoid}}}}
</style></head><body><main>
<header><small>MedAI Assurance · v0.5 / Research demonstration</small><h1>Model Change Assessment</h1>
<p>PTB-XL 1.0.3 · baseline → candidate · historical, previously inspected fold-9 development data</p>
</header><div class="content">
<span class="tag">CLINICAL BENEFIT NOT ESTABLISHED</span>
<div class="details">
<div class="stat"><small>Evidence integrity</small><strong>REVERIFIED</strong></div>
<div class="stat"><small>Clinical gate</small><strong>NOT_EVALUATED</strong></div>
<div class="stat"><small>Release decision</small><strong>OUTSIDE_SCOPE</strong></div></div>
<p class="note">These development-only findings are not independent validation or statistical evidence of non-inferiority. Not for diagnostic or regulatory release decisions.</p>
<section class="block"><h2>01 / Paired descriptive performance</h2>
<table><thead><tr><th>Measure</th><th>Baseline</th><th>Candidate</th><th>Δ Candidate–Baseline</th></tr></thead>
<tbody>{metric_rows}</tbody></table><p>OOF training thresholds: baseline <b>{report["models"]["baseline"]["training_oof_threshold"]:.6f}</b>;
 candidate <b>{report["models"]["candidate"]["training_oof_threshold"]:.6f}</b>. L2 penalty:
 baseline <b>{h(report["models"]["baseline"]["l2_penalty"])}</b> →
 candidate <b>{h(report["models"]["candidate"]["l2_penalty"])}</b>.
 Fold 9 was used for prior development.</p></section>
<section class="block"><h2>02 / Required cohorts</h2><div class="subs">{''.join(subgroup_cards)}</div></section>
<section class="block"><h2>03 / Evidence gaps and observed concerns</h2><ul>{finding_html}</ul></section>
<section class="block"><h2>04 / Evidence and protocol traceability</h2>
<p>Protocol: <b>{h(report["protocol"]["id"])} / {h(report["protocol"]["version"])}</b>;
 claim: <b>{h(report["protocol"]["claim_id"])}</b>; control: <b>{h(report["protocol"]["risk_control_id"])}</b></p>
<p>Training: {report["dataset"]["train_records"]} ECG; previously inspected validation: {report["dataset"]["validation_records"]} ECG;
 verified waveform files: {report["integrity"]["waveform_files_sha256_checked_by_upstream"]};
 inventory entries: {report["integrity"]["audit_inventory"]["files_verified"]}.</p>
<div class="hash">v0.4 package SHA-256: {h(report["integrity"]["upstream_package_file_sha256"])}<br>
Protocol SHA-256: {h(report["protocol"]["sha256"])}<br>
Inventory SHA-256: {h(report["integrity"]["audit_inventory"]["inventory_sha256"])}<br>
Assessment SHA-256: {h(report["assessment_sha256"])}</div>
<p>Hash checks establish local integrity and consistency only; not signed provenance or immutable custody.</p></section>
<section class="block"><h2>05 / Limitations and next review</h2><ul>{limits}</ul>
<p>Human expert interpretation is necessary. Technical evidence gaps cannot be overridden by a reviewer.</p></section></div>
<footer>Research only · no patient identifiers in this report · Generated deterministically from verified v0.4 research evidence.</footer>
</main></body></html>\n'''


def write_atomic(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".temporary")
    try:
        temporary.write_text(data, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def output_files(directory: Path) -> dict[str, Path]:
    return {"json": directory / FILE_JSON, "markdown": directory / FILE_MD,
            "html": directory / FILE_HTML}


def verify_outputs(output_dir: Path, root: Path, protocol: Path, inventory: Path,
                   package_path: Path) -> dict:
    paths = output_files(output_dir)
    require(all(p.is_file() for p in paths.values()), "Missing v0.5 report artifact")
    observed = read_json(paths["json"])
    require(isinstance(observed, dict) and observed.get("schema_version") == SCHEMA,
            "Unexpected v0.5 report schema")
    provided = observed.get("assessment_sha256")
    require(isinstance(provided, str) and provided == doc_digest({k: v for k, v in observed.items()
                                                                  if k != "assessment_sha256"}),
            "v0.5 report SHA-256 mismatch")
    rebuilt = build(root, protocol, inventory, package_path)
    require(observed == rebuilt, "v0.5 report does not match recalculated sources")
    require(paths["markdown"].read_text(encoding="utf-8") == render_markdown(rebuilt),
            "Markdown report changed")
    require(paths["html"].read_text(encoding="utf-8") == render_html(rebuilt),
            "HTML report changed")
    return rebuilt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "verify"))
    parser.add_argument("--data-dir", type=Path,
                        default=Path.home() / "Documents" / "MedAI-Data" / "ptb-xl-1.0.3")
    parser.add_argument("--protocol", type=Path, required=True,
                        help="Independent locked PTB-XL demo protocol JSON")
    parser.add_argument("--inventory", type=Path, help="v0.4 ten-file SHA-256 snapshot CSV")
    parser.add_argument("--v04-package", type=Path, help="Existing v0.4 research_evidence.json")
    parser.add_argument("--out-dir", type=Path, help="Report output directory")
    args = parser.parse_args()
    root = exact_path(args.data_dir)
    pilot = root / "benchmark_v1" / "pilot_v1"
    inventory = exact_path(args.inventory or pilot / "audit_snapshot_v04" / "sha256_inventory.csv")
    package = exact_path(args.v04_package or pilot / "real_evidence_v04" / "research_evidence.json")
    outdir = exact_path(args.out_dir or pilot / "model_change_v05")
    protocol = exact_path(args.protocol)
    if args.mode == "build":
        result = build(root, protocol, inventory, package)
        files = output_files(outdir)
        write_atomic(files["json"], json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        write_atomic(files["markdown"], render_markdown(result))
        write_atomic(files["html"], render_html(result))
        verify_outputs(outdir, root, protocol, inventory, package)
        print("MEDAI v0.5 MODEL CHANGE REPORT: CREATED AND VERIFIED")
        print("V0.4 SOURCE EVIDENCE + LOCKED PROTOCOL: REVERIFIED")
        print("AUDIT INVENTORY: 10/10 LOCAL HASHES MATCH")
        comp = result["previously_inspected_fold9"]
        print("FOLD-9 DEV SENSITIVITY: baseline={:.3f} candidate={:.3f}".format(
            comp["baseline"]["sensitivity"], comp["candidate"]["sensitivity"]))
        for sub in result["subgroups"]:
            print("SUBGROUP:", sub["cohort_id"], sub["demo_count_adequacy"])
        print("CLINICAL GATE: NOT_EVALUATED")
        print("FOLD 10: NOT ACCESSED")
        print("HTML REPORT:", files["html"])
        print("JSON REPORT:", files["json"])
    else:
        verify_outputs(outdir, root, protocol, inventory, package)
        print("MEDAI v0.5 MODEL CHANGE REPORT VERIFICATION: OK")
        print("JSON + MARKDOWN + HTML + V0.4 SOURCES: CONSISTENT")
        print("CLINICAL GATE: NOT_EVALUATED")
        print("RELEASE DECISION: OUTSIDE_PLATFORM_SCOPE")


if __name__ == "__main__":
    try:
        main()
    except (ChangeError, upstream.EvidenceError, OSError, ValueError, TypeError,
            KeyError, IndexError, json.JSONDecodeError) as exc:
        raise SystemExit(f"MEDAI v0.5 VERIFICATION FAILED: {exc}") from exc
