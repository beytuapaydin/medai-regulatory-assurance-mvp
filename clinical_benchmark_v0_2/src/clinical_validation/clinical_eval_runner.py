"""Research-only deterministic release-evidence gate for binary ECG predictions.

Not a clinically validated decision-support or regulatory approval tool.
All thresholds are illustrative and require prospective clinical justification.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Sequence
from .ptbxl_age_policy import ptbxl_age75_membership


def _invalid_identifier(value: str) -> bool:
    """Reject empty, whitespace and invisible Unicode format/control characters before any cohort/leakage check.

    PTB-XL patient identifiers are numeric strings; synthetic test fixtures
    may also contain symbolic IDs without whitespace.
    """
    return not value or not value.isprintable() or any(ch.isspace() for ch in value)


def _canonical_patient_id(value: str) -> str:
    """Normalize equivalent representations consistently across all checks."""
    normalized = value.casefold()
    if re.fullmatch(r"\d+\.0+", normalized):
        normalized = normalized.split(".", 1)[0]
    return normalized


def _canonical_ecg_id(value: str | int) -> str:
    normalized = str(value).casefold()
    if re.fullmatch(r"\d+\.0+", normalized):
        normalized = normalized.split(".", 1)[0]
    return normalized


@dataclass(frozen=True)
class EvaluationPolicy:
    policy_id: str = "ECG-REG-POLICY-v0.1"
    required_test_fold: int = 10
    # Number of *positive* and *negative* cases per declared subgroup.
    min_positive_n: int = 30
    min_negative_n: int = 30
    # Independent positive and negative patient clusters per declared cohort.
    min_positive_patients: int = 30
    min_negative_patients: int = 30
    required_subgroups: tuple[str, ...] = ("ALL",)
    max_sensitivity_drop: float = 0.02
    max_critical_fn_rate: float = 0.05
    max_specificity_drop: float = 0.02


def compute_sha256(payload: Any) -> str:
    """Hash canonical UTF-8 JSON; does NOT make evidence immutable or authentic."""
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _report(
    status: str,
    reasons: list[str],
    records: Sequence[Mapping[str, Any]] | None,
    training_patient_ids: Sequence[str] | None,
    model_v1_id: str,
    model_v2_id: str,
    dataset_version: str,
    policy: EvaluationPolicy,
    is_synthetic_run: bool,
    subgroup_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Includes training split manifest to bind the patient leakage check to the evidence.
    # The order of input records is intentionally treated as significant.
    inputs = {
        "records": records,
        "training_patient_ids": sorted(training_patient_ids) if training_patient_ids is not None else None,
    }
    try:
        input_hash = compute_sha256(inputs)
    except (TypeError, ValueError):
        input_hash = None
        reasons = [*reasons, "Inputs could not be canonically serialized; input digest unavailable."]
        if status == "PASS":
            status = "NOT_MEASURED"

    core = {
        "schema_version": "medai-clinical-evidence-v0.1",
        "gate_status": status,
        "evidence_scope": "ENGINE_TEST_ONLY" if is_synthetic_run else "RESEARCH_NOT_CLINICALLY_VALIDATED",
        "is_synthetic_simulation": is_synthetic_run,
        "dataset_version": dataset_version,
        "model_comparison": {"baseline": model_v1_id, "candidate": model_v2_id},
        "policy": asdict(policy),
        "subgroup_metrics": subgroup_metrics or {},
        "reasons": reasons,
        "input_sha256": input_hash,
    }
    core["report_sha256"] = compute_sha256(core)
    return core


def evaluate_model_regression(
    records: Sequence[Mapping[str, Any]] | None,
    *,
    training_patient_ids: Sequence[str] | None,
    model_v1_id: str,
    model_v2_id: str,
    dataset_version: str = "PTB-XL-1.0.3",
    policy: EvaluationPolicy = EvaluationPolicy(),
    is_synthetic_run: bool = True,
) -> dict[str, Any]:
    """Compare two binary classifiers on a held-out set.

    `records` MUST contain only held-out test ECG records. The separately
    supplied complete list of training patient IDs is essential for checking
    patient overlap; inspecting held-out rows alone cannot detect leakage.
    """
    def finish(status: str, reasons: list[str], metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        return _report(
            status, reasons, records, training_patient_ids, model_v1_id, model_v2_id,
            dataset_version, policy, is_synthetic_run, metrics,
        )

    if not records:
        return finish("NOT_MEASURED", ["No held-out test records were provided."])

    required = {"ecg_id", "patient_id", "strat_fold", "subgroups", "y_true", "y_pred_v1", "y_pred_v2"}
    for i, record in enumerate(records):
        if not isinstance(record, Mapping) or not required.issubset(record):
            return finish("NOT_MEASURED", [f"Record {i}: missing required fields."])
        if any(record[key] is None for key in required):
            return finish("NOT_MEASURED", [f"Record {i}: a required field has no value."])
        if any(type(record[key]) is not int or record[key] not in (0, 1)
               for key in ("y_true", "y_pred_v1", "y_pred_v2")):
            return finish("NOT_MEASURED", [f"Record {i}: predictions and truth must be binary integers 0 or 1."])
        if type(record["strat_fold"]) is not int:
            return finish("NOT_MEASURED", [f"Record {i}: strat_fold must be an integer."])
        if type(record["ecg_id"]) not in (str, int) or _invalid_identifier(str(record["ecg_id"])):
            return finish("NOT_MEASURED", [f"Record {i}: ecg_id is invalid or contains whitespace."])
        if not isinstance(record["patient_id"], str) or _invalid_identifier(record["patient_id"]):
            return finish("NOT_MEASURED", [f"Record {i}: patient_id must be a nonempty string without whitespace."])
        tags = record["subgroups"]
        if (not isinstance(tags, (tuple, list)) or not tags
                or any(not isinstance(tag, str) or _invalid_identifier(tag) for tag in tags)
                or len(tags) != len(set(tags)) or "ALL" not in tags):
            return finish("NOT_MEASURED", [
                f"Record {i}: subgroups must be distinct nonempty strings and must include 'ALL'."
            ])

        # Fail closed at the evaluation API boundary, not just in EvidencePackage.
        # Unrelated legacy subgroup names (e.g. F_65_PLUS) remain supported.
        if "age" in record or "AGE75_PLUS" in tags or "AGE75_PLUS" in policy.required_subgroups:
            try:
                is_age75 = ptbxl_age75_membership(record.get("age"))
            except ValueError as exc:
                return finish("NOT_MEASURED", [
                    f"Record {i}: cannot establish AGE75_PLUS membership: {exc}."
                ])
            if is_age75 != ("AGE75_PLUS" in tags):
                return finish("INSUFFICIENT_EVIDENCE", [
                    f"Record {i}: AGE75_PLUS subgroup tags disagree with age."
                ])

    if training_patient_ids is None:
        return finish("INSUFFICIENT_EVIDENCE", ["Training patient manifest not provided; patient overlap cannot be assessed."])
    if any(not isinstance(pid, str) or _invalid_identifier(pid) for pid in training_patient_ids):
        return finish("INSUFFICIENT_EVIDENCE", ["Training patient manifest contains invalid identifiers."])

    evidence_issues: list[str] = []
    off_fold = sum(r["strat_fold"] != policy.required_test_fold for r in records)
    if off_fold:
        evidence_issues.append(f"{off_fold} test record(s) outside required fold {policy.required_test_fold}.")
    test_ids = {_canonical_patient_id(r["patient_id"]) for r in records}
    train_ids = {_canonical_patient_id(pid) for pid in training_patient_ids}
    overlaps = test_ids & train_ids
    if overlaps:
        evidence_issues.append(f"Patient leakage: {len(overlaps)} test patient(s) are also in the training manifest.")
    ecg_ids = [_canonical_ecg_id(r["ecg_id"]) for r in records]
    if len(set(ecg_ids)) != len(ecg_ids):
        evidence_issues.append("Duplicate ecg_id detected; repeated predictions must not inflate the denominators.")
    if not policy.required_subgroups or any(not sg for sg in policy.required_subgroups):
        evidence_issues.append("No valid required subgroup was declared in the evaluation policy.")
    if any(type(value) is not int or value < 1 for value in (
        policy.min_positive_n, policy.min_negative_n,
        policy.min_positive_patients, policy.min_negative_patients,
    )):
        evidence_issues.append("Minimum subgroup record and independent-patient thresholds must be positive integers.")
    if not all(0 <= t <= 1 for t in (policy.max_sensitivity_drop, policy.max_critical_fn_rate, policy.max_specificity_drop)):
        evidence_issues.append("Policy rate thresholds must lie in [0, 1].")

    # Do not calculate clinical metrics on a contaminated/ambiguous evaluation split.
    if evidence_issues:
        return finish("INSUFFICIENT_EVIDENCE", evidence_issues)

    subgroup_metrics: dict[str, Any] = {}
    insuff: list[str] = []
    failures: list[str] = []
    for sg in policy.required_subgroups:
        sg_rows = [r for r in records if sg in r["subgroups"]]
        positives = [r for r in sg_rows if r["y_true"] == 1]
        negatives = [r for r in sg_rows if r["y_true"] == 0]
        n_pos, n_neg = len(positives), len(negatives)
        n_pos_patients = len({_canonical_patient_id(r["patient_id"]) for r in positives})
        n_neg_patients = len({_canonical_patient_id(r["patient_id"]) for r in negatives})
        if (n_pos < policy.min_positive_n or n_neg < policy.min_negative_n
                or n_pos_patients < policy.min_positive_patients
                or n_neg_patients < policy.min_negative_patients):
            insuff.append(
                f"Subgroup '{sg}' has {n_pos} positive ECGs ({n_pos_patients} distinct patients) "
                f"and {n_neg} negative ECGs ({n_neg_patients} distinct patients); "
                f"requires >= {policy.min_positive_n} positive ECGs, "
                f">= {policy.min_negative_n} negative ECGs, "
                f">= {policy.min_positive_patients} distinct positive patients, "
                f">= {policy.min_negative_patients} distinct negative patients."
            )
            subgroup_metrics[sg] = {
                "n_total": len(sg_rows), "n_positive": n_pos, "n_negative": n_neg,
                "n_positive_patients": n_pos_patients,
                "n_negative_patients": n_neg_patients, "measured": False,
            }
            continue

        tp1 = sum(r["y_pred_v1"] == 1 for r in positives)
        tp2 = sum(r["y_pred_v2"] == 1 for r in positives)
        tn1 = sum(r["y_pred_v1"] == 0 for r in negatives)
        tn2 = sum(r["y_pred_v2"] == 0 for r in negatives)
        sens1, sens2 = tp1 / n_pos, tp2 / n_pos
        spec1, spec2 = tn1 / n_neg, tn2 / n_neg
        sens_drop, spec_drop = sens1 - sens2, spec1 - spec2
        fn_rate2 = (n_pos - tp2) / n_pos
        subgroup_metrics[sg] = {
            "measured": True,
            "n_total": len(sg_rows), "n_positive": n_pos, "n_negative": n_neg,
            "n_positive_patients": n_pos_patients,
            "n_negative_patients": n_neg_patients,
            "sensitivity_v1": sens1, "sensitivity_v2": sens2,
            "sensitivity_drop": sens_drop, "critical_fn_rate_v2": fn_rate2,
            "specificity_v1": spec1, "specificity_v2": spec2,
            "specificity_drop": spec_drop,
        }
        # Always compare raw floating-point measurements, never rounded display values.
        if sens_drop > policy.max_sensitivity_drop + 1e-12:
            failures.append(f"Subgroup '{sg}': sensitivity drop {sens_drop:.6f} exceeds {policy.max_sensitivity_drop:.6f}.")
        if fn_rate2 > policy.max_critical_fn_rate + 1e-12:
            failures.append(f"Subgroup '{sg}': false-negative rate {fn_rate2:.6f} exceeds {policy.max_critical_fn_rate:.6f}.")
        if spec_drop > policy.max_specificity_drop + 1e-12:
            failures.append(f"Subgroup '{sg}': specificity drop {spec_drop:.6f} exceeds {policy.max_specificity_drop:.6f}.")

    # A confirmed failure must never be hidden by insufficient evidence elsewhere.
    if failures:
        return finish("FAIL", failures + insuff, subgroup_metrics)
    if insuff:
        return finish("INSUFFICIENT_EVIDENCE", insuff, subgroup_metrics)
    return finish("PASS", ["All *declared* subgroup thresholds passed on the supplied test split."], subgroup_metrics)
