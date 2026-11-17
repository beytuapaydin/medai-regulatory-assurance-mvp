"""Research-only, auditable-ish evidence *format*: not a validated QMS tool.

All test data remains local. No automatic clinical or legal interpretation.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
from .clinical_eval_runner import _canonical_patient_id, compute_sha256, evaluate_model_regression
from .ptbxl_age_policy import ptbxl_age75_membership
from .paired_statistics import patient_cluster_paired_sensitivity_ci
from .paired_estimands_v1 import paired_estimands_exploratory, _validate as _validate_exploratory_inputs
from .protocol_loader import LockedProtocol

VALID_STATUSES = {"PASS", "FAIL", "INSUFFICIENT_EVIDENCE", "NOT_MEASURED"}


def _invalid_payload(rows: Sequence[Mapping[str, Any]] | None) -> list[str]:
    """Verify age-derived membership; never accept caller-asserted subgroup labels blindly."""
    problems = []
    if not isinstance(rows, list):
        return ["records must be supplied as a JSON list"]
    for i, record in enumerate(rows):
        if not isinstance(record, dict):
            problems.append(f"record {i} is not an object")
            continue
        try:
            is_age75 = ptbxl_age75_membership(record.get("age"))
        except ValueError as exc:
            problems.append(f"record {i} missing/invalid PTB-XL age: {exc}")
            continue
        expected = {"ALL"} | ({"AGE75_PLUS"} if is_age75 else set())
        tags = record.get("subgroups")
        if (not isinstance(tags, (list, tuple))
                or any(not isinstance(tag, str) for tag in tags)
                or set(tags) != expected or len(tags) != len(expected)):
            problems.append(f"record {i} subgroup tags disagree with age (derive from source metadata)")
        if len(problems) >= 10:
            break
    return problems


def _basic_package(protocol: LockedProtocol, source_type: str, model_ids: tuple[str, str],
                   records: Sequence[Mapping[str, Any]] | None,
                   training_ids: Sequence[str] | None) -> dict[str, Any]:
    """No raw patient records, patient IDs or signal data in JSON evidence output."""
    try:
        inputs_hash = compute_sha256({
            "records": records,
            "training_patient_ids": sorted(training_ids) if training_ids is not None else None,
        })
    except (ValueError, TypeError):
        inputs_hash = None
    return {
        "schema_version": "medai-evidence-v0.2",
        "intended_use": "Non-clinical QA/RA software engineering research demonstration; not clinical validation, regulatory approval or release authorization.",
        "source_type": source_type,
        "real_ptbxl_validation_completed": False,
        "protocol": {
            "id": protocol.data["protocol_id"],
            "version": protocol.data["protocol_version"],
            "sha256": protocol.sha256,
            "demonstration_thresholds_not_clinically_justified": True,
        },
        "traceability": {
            "claim_id": protocol.data["clinical_claim_id"],
            "risk_control_id": protocol.data["risk_control_id"],
            "scope": protocol.data["claim_scope"],
            "risk_control_scope": protocol.data["risk_control_scope"],
            "relationship": "DEMONSTRATION_LINK_ONLY; manufacturer must assess clinical validity",
        },
        "models": {"baseline": model_ids[0], "candidate": model_ids[1]},
        # Explicit demo criteria used by downstream offline semantic verifier.
        # All values originate from the locked protocol, not from reviewer input.
        "acceptance_rules": {**{key: protocol.data["rules"][key] for key in (
            "min_positive_records", "min_negative_records",
            "min_positive_patients", "min_negative_patients",
            "max_sensitivity_drop", "max_critical_fn_rate", "max_specificity_drop",
            "non_inferiority_margin_sensitivity_delta",
        )}, "required_subgroups": list(protocol.data["required_subgroups"])},
        "change_classification": {
            "change_type": "MODEL_WEIGHT_UPDATE_DEMO",
            "changed_components": ["model_weights"],
            "unchanged_components": "NOT_VERIFIED",
            "clinical_consequence_tier": "TBD_BY_MANUFACTURER",
            "regulatory_significance": "NOT_ASSESSED",
            "evidence_response": "PAIRED_REGRESSION_DEMONSTRATION",
        },
        "integrity": {
            "protocol_sha256": protocol.sha256,
            "inputs_sha256": inputs_hash,
            "hash_caveat": "SHA-256 is an integrity digest, not immutability, signature, true provenance or trusted timestamp.",
        },
        "known_limitations": [
            "Input truth labels, source metadata and model provenance are not independently authenticated.",
            "Illustrative acceptance thresholds were not clinically justified or prospectively qualified.",
            "Test data may be synthetic; local execution alone is not external clinical validation.",
            "No patient- or site-level generalizability claims; no clinical benefit-risk determination.",
            "No medical-device/AI-Act significant-modification decision or QMS release authorization.",
            "Exploratory percentile bootstrap requires statistical review and predeclared multiplicity policy before clinical use.",
            "Input hash alone does not prove source identity, training-data completeness or external pretraining integrity.",
        ],
    }


def build_evidence_package(
    protocol: LockedProtocol,
    records: list[dict[str, Any]] | None,
    *, training_patient_ids: list[str] | None,
    model_v1_id: str, model_v2_id: str,
    source_type: str = "SYNTHETIC_ENGINE_TEST",
) -> dict[str, Any]:
    if source_type not in {"SYNTHETIC_ENGINE_TEST", "USER_SUPPLIED_UNVERIFIED"}:
        raise ValueError("Unsupported evidence source classification")
    if not model_v1_id or not model_v2_id or model_v1_id == model_v2_id:
        raise ValueError("Distinct nonempty model identifiers required")
    package = _basic_package(protocol, source_type, (model_v1_id, model_v2_id), records, training_patient_ids)
    input_problems = _invalid_payload(records)
    if package["integrity"]["inputs_sha256"] is None:
        input_problems.append("Input data cannot be canonically hashed; input integrity not established")
    if training_patient_ids is not None and len(training_patient_ids) == 0:
        input_problems.append("empty training manifest does not demonstrate patient-level independence")
    if input_problems:
        status = ("NOT_MEASURED" if not records or package["integrity"]["inputs_sha256"] is None
                  else "INSUFFICIENT_EVIDENCE")
        result = {"gate_status": status, "reasons": input_problems, "subgroup_metrics": {}}
    else:
        result = evaluate_model_regression(
            records, training_patient_ids=training_patient_ids,
            model_v1_id=model_v1_id, model_v2_id=model_v2_id,
            dataset_version=protocol.data["dataset"]["reference_name"] + "-FORMAT-DEMO",
            policy=protocol.engine_policy,
            is_synthetic_run=source_type == "SYNTHETIC_ENGINE_TEST",
        )
    package["technical_gate"] = {
        "status": result["gate_status"],
        "reasons": result["reasons"],
        "clinical_eval_core_report_sha256": result.get("report_sha256"),
    }
    cohort_results: list[dict[str, Any]] = []
    additional_fails: list[str] = []
    additional_insuff: list[str] = []
    rules = protocol.data["rules"]
    for cohort in protocol.data["required_subgroups"]:
        metric = result.get("subgroup_metrics", {}).get(cohort)
        item: dict[str, Any] = {"cohort_id": cohort, "basic_metrics": metric, "paired_sensitivity_delta_ci": None}
        if metric and metric.get("measured"):
            selected = [r for r in (records or []) if cohort in r["subgroups"]]
            pos_ids = {_canonical_patient_id(r["patient_id"]) for r in selected if r["y_true"] == 1}
            neg_ids = {_canonical_patient_id(r["patient_id"]) for r in selected if r["y_true"] == 0}
            item["n_distinct_positive_patients"] = len(pos_ids)
            item["n_distinct_negative_patients"] = len(neg_ids)
            if (len(pos_ids) < rules["min_positive_patients"]
                    or len(neg_ids) < rules["min_negative_patients"]):
                additional_insuff.append(
                    f"{cohort}: only {len(pos_ids)} distinct positive patients "
                    f"and {len(neg_ids)} distinct negative patients; requires "
                    f">= {rules['min_positive_patients']} positive and "
                    f">= {rules['min_negative_patients']} negative patients."
                )
            else:
                stat = patient_cluster_paired_sensitivity_ci(
                    selected, confidence_level=rules["bootstrap_confidence_level"],
                    replicates=rules["bootstrap_replicates"],
                    seed=rules["bootstrap_seed"],
                )
                item["paired_sensitivity_delta_ci"] = stat
                if stat is None:
                    additional_insuff.append(f"{cohort}: cluster-bootstrap confidence interval not estimable")
                else:
                    margin = rules["non_inferiority_margin_sensitivity_delta"]
                    if stat["ci_upper"] < margin:
                        additional_fails.append(f"{cohort}: CI upper {stat['ci_upper']:.4f} below demo non-inferiority margin {margin:.4f}")
                    elif stat["ci_lower"] < margin:
                        additional_insuff.append(f"{cohort}: cannot establish demo non-inferiority: CI lower {stat['ci_lower']:.4f} < margin {margin:.4f}")
        cohort_results.append(item)
    core_status = result["gate_status"]
    # A confirmed failing criterion cannot be masked by evidence insufficiency.
    if core_status == "FAIL" or additional_fails:
        overall = "FAIL"
    elif core_status == "NOT_MEASURED":
        overall = "NOT_MEASURED"
    elif core_status == "INSUFFICIENT_EVIDENCE" or additional_insuff:
        overall = "INSUFFICIENT_EVIDENCE"
    else:
        overall = "PASS"
    package["cohort_evaluations"] = cohort_results
    package["statistical_findings"] = {
        "confirmed_demo_threshold_failures": additional_fails,
        "evidence_insufficiencies": additional_insuff,
        "multiple_testing_policy": "NOT_SPECIFIED_FOR_CLINICAL_INFERENCE",
    }
    # Optional research-only addendum. Only construct after the common input
    # validator succeeds; these values NEVER feed the technical gate.
    exploratory = None
    try:
        if records:
            _validate_exploratory_inputs(records)
        research_input_valid = bool(records)
    except ValueError:
        research_input_valid = False
    if not input_problems and research_input_valid and result.get("gate_status") != "NOT_MEASURED":
        research_by_cohort = {}
        for cohort in protocol.data["required_subgroups"]:
            subset = [r for r in records if cohort in r["subgroups"]]
            research_by_cohort[cohort] = paired_estimands_exploratory(
                subset,
                confidence_level=rules["bootstrap_confidence_level"],
                replicates=rules["bootstrap_replicates"],
                seed=rules["bootstrap_seed"],
                min_patient_count=max(rules["min_positive_patients"],
                                      rules["min_negative_patients"]),
            ) if subset else None
        exploratory = {
            "schema_version": "medai-exploratory-evidence-v1",
            "scope": "RESEARCH_ONLY_NOT_A_CLINICAL_GATE",
            "source_inputs_sha256": package["integrity"]["inputs_sha256"],
            "cohorts": research_by_cohort,
            "verification_level": "SOURCE_RECALCULATION_REQUIRED",
        }
    package["exploratory_estimands"] = exploratory
    package["overall_gate_status"] = overall
    package["human_review"] = {"status": "PENDING_REVIEW", "review_record_separate": True, "technical_result_can_be_overridden": False}
    package["manufacturer_release_decision"] = "OUTSIDE_PLATFORM_SCOPE"
    package["artifact_sha256"] = compute_sha256(package)
    return package


def write_evidence_files(package: Mapping[str, Any], output_folder: str | Path) -> tuple[Path, Path]:
    folder = Path(output_folder)
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / "evidence_package.json"
    html_path = folder / "report.html"
    json_path.write_text(json.dumps(package, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    def table_rows() -> str:
        result = []
        for cohort in package.get("cohort_evaluations", []):
            metrics = cohort.get("basic_metrics") or {}
            ci = cohort.get("paired_sensitivity_delta_ci") or {}
            delta = ci.get("point_delta_v2_minus_v1")
            lower = ci.get("ci_lower")
            upper = ci.get("ci_upper")
            fmt = lambda v: "—" if v is None else f"{v:.4f}"
            result.append("<tr>" + "".join(f"<td>{escape(str(x))}</td>" for x in [
                cohort["cohort_id"], metrics.get("n_positive", "—"),
                metrics.get("n_negative", "—"), fmt(delta),
                f"[{fmt(lower)}, {fmt(upper)}]", metrics.get("measured", False),
            ]) + "</tr>")
        return "".join(result)
    reasons = "".join(f"<li>{escape(str(r))}</li>" for r in package["technical_gate"]["reasons"])
    reasons += "".join(f"<li>{escape(str(r))}</li>" for r in package["statistical_findings"]["confirmed_demo_threshold_failures"])
    reasons += "".join(f"<li>{escape(str(r))}</li>" for r in package["statistical_findings"]["evidence_insufficiencies"])
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MedAI Evidence - Research demonstration</title><style>body{{font-family:system-ui,Arial;max-width:950px;margin:2.4rem auto;padding:0 1rem;line-height:1.5;color:#152333}}.alert{{padding:1rem;background:#fff2df;border-left:4px solid #bb6800}}table{{width:100%;border-collapse:collapse}}td,th{{padding:.7rem;border-bottom:1px solid #ddd;text-align:left}}code{{background:#edf1f6;padding:.15rem .3rem}}.subtitle{{color:#516070}}</style></head><body>
<h1>MedAI Assurance — Evidence Summary</h1><div class="alert"><strong>Research-only demonstration.</strong> No real PTB-XL model performance or clinical safety is claimed. No regulatory decision or release approval.</div>
<p><strong>Source:</strong> {escape(str(package['source_type']))}</p>
<p><strong>Overall demo policy result:</strong> <code>{escape(str(package['overall_gate_status']))}</code></p>
<p><strong>Protocol:</strong> {escape(str(package['protocol']['id']))} / {escape(str(package['protocol']['version']))}</p>
<p><strong>Claim:</strong> {escape(str(package['traceability']['claim_id']))} · <strong>Risk control:</strong> {escape(str(package['traceability']['risk_control_id']))}</p>
<h2>Predeclared cohorts</h2><table><thead><tr><th>Cohort</th><th>Positives</th><th>Negatives</th><th>Paired Δ sens.</th><th>Exploratory 95% CI</th><th>Measured</th></tr></thead><tbody>{table_rows()}</tbody></table>
<h2>Reasons and outstanding evidence</h2><ul>{reasons}</ul>
<h2>Human review / manufacturer responsibility</h2><p>Human review is <strong>pending</strong>. Technical FAIL cannot be overridden. Formal release and regulatory decisions remain outside the platform and with the manufacturer.</p>
<p class="subtitle">Canonical evidence SHA-256: <code>{escape(str(package['artifact_sha256']))}</code>. Digest is not an immutable audit trail or a digital signature.</p>
<h2>Known limitations</h2><ul>{''.join('<li>'+escape(x)+'</li>' for x in package['known_limitations'])}</ul></body></html>'''
    html_path.write_text(html, encoding="utf-8", newline="\n")
    return json_path, html_path
