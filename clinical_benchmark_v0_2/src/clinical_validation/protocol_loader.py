"""Strict, non-executable protocol configuration for research ECG regression."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from .clinical_eval_runner import EvaluationPolicy, compute_sha256

ALLOWED_SUBGROUPS = {"ALL", "AGE75_PLUS"}


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class LockedProtocol:
    data: dict[str, Any]
    sha256: str
    engine_policy: EvaluationPolicy


def load_protocol(path: str | Path) -> LockedProtocol:
    """Load a constrained JSON protocol. Never eval() a cohort expression."""
    raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != "medai-protocol-v0.2":
        raise ProtocolError("Unsupported protocol schema")
    if data.get("demonstration_only") is not True:
        raise ProtocolError("v0.2 supports demonstration-only policy, not clinical use")
    for key in ("protocol_id", "protocol_version", "clinical_claim_id", "risk_control_id", "claim_scope", "risk_control_scope"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ProtocolError(f"Missing/invalid {key}")
    dataset = data.get("dataset")
    if not isinstance(dataset, dict) or dataset.get("required_test_fold") != 10:
        raise ProtocolError("Only fold 10 test evaluation supported by this demo")
    tags = data.get("required_subgroups")
    if not isinstance(tags, list) or len(tags) != len(set(tags)) or not tags or set(tags) - ALLOWED_SUBGROUPS or "ALL" not in tags:
        raise ProtocolError("Subgroups must be distinct, declared, recognized, and include ALL")
    rules = data.get("rules")
    if not isinstance(rules, dict):
        raise ProtocolError("No rules")
    for name in ("min_positive_records", "min_negative_records", "min_positive_patients", "min_negative_patients", "bootstrap_replicates", "bootstrap_seed"):
        val = rules.get(name)
        if type(val) is not int or (val < 1 if name != "bootstrap_seed" else val < 0):
            raise ProtocolError(f"{name} must be integer >= 1 (seed >= 0)")
    if rules["bootstrap_replicates"] < 200:
        raise ProtocolError("bootstrap_replicates too small for demo CI")
    for name in ("max_sensitivity_drop", "max_critical_fn_rate", "max_specificity_drop", "bootstrap_confidence_level"):
        val = rules.get(name)
        if type(val) not in (float, int) or not 0 < val < 1:
            raise ProtocolError(f"{name} must be strictly between 0 and 1")
    margin = rules.get("non_inferiority_margin_sensitivity_delta")
    if type(margin) not in (float, int) or not -1 < margin < 0:
        raise ProtocolError("non-inferiority margin must be a negative proportion")
    policy = EvaluationPolicy(
        policy_id=data["protocol_id"] + "/" + data["protocol_version"],
        required_test_fold=10,
        min_positive_n=rules["min_positive_records"],
        min_negative_n=rules["min_negative_records"],
        min_positive_patients=rules["min_positive_patients"],
        min_negative_patients=rules["min_negative_patients"],
        required_subgroups=tuple(tags),
        max_sensitivity_drop=rules["max_sensitivity_drop"],
        max_critical_fn_rate=rules["max_critical_fn_rate"],
        max_specificity_drop=rules["max_specificity_drop"],
    )
    return LockedProtocol(data=data, sha256=compute_sha256(data), engine_policy=policy)
