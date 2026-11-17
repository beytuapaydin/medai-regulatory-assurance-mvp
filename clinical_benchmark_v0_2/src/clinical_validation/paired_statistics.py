"""Illustrative paired patient-cluster bootstrap; NOT an approved clinical test."""
from __future__ import annotations
from collections import defaultdict
import random
from typing import Any, Mapping, Sequence
from .clinical_eval_runner import _canonical_patient_id


def _quantile(values: list[float], quantile: float) -> float:
    """Linear interpolation of the sorted empirical bootstrap distribution."""
    values = sorted(values)
    position = (len(values) - 1) * quantile
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def patient_cluster_paired_sensitivity_ci(
    rows: Sequence[Mapping[str, Any]], *, confidence_level: float, replicates: int, seed: int
) -> dict[str, Any] | None:
    """Paired v2-v1 sensitivity CI with resampling at patient cluster level.

    This is an exploratory percentile-bootstrap CI, not proof of clinical
    non-inferiority. It retains all records from each resampled patient.
    """
    # A sensitivity CI is conditional on y_true == 1. Resampling all
    # patients would randomly change the positive cluster count and inflate
    # apparent N with negative-only patients.
    positives = [r for r in rows if r["y_true"] == 1]
    if not positives:
        return None
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in positives:
        groups[_canonical_patient_id(str(row["patient_id"]))].append(row)
    patient_keys = sorted(groups)
    if not patient_keys:
        return None
    def difference(sample: Sequence[Mapping[str, Any]]) -> float | None:
        pos = [r for r in sample if r["y_true"] == 1]
        if not pos:
            return None
        return sum(r["y_pred_v2"] - r["y_pred_v1"] for r in pos) / len(pos)
    point = difference(rows)
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(replicates):
        sample = [r for _i in range(len(patient_keys))
                  for r in groups[patient_keys[rng.randrange(len(patient_keys))]]]
        estimate = difference(sample)
        if estimate is not None:
            estimates.append(estimate)
    if len(estimates) < max(200, int(replicates * 0.95)):
        return None
    alpha = 1 - confidence_level
    return {
        "method": "paired_positive_patient_cluster_bootstrap_percentile_exploratory",
        "point_delta_v2_minus_v1": point,
        "ci_lower": _quantile(estimates, alpha / 2),
        "ci_upper": _quantile(estimates, 1 - alpha / 2),
        "confidence_level": confidence_level,
        "replicates_requested": replicates,
        "replicates_valid": len(estimates),
        "seed": seed,
        "unique_patient_clusters": len(groups),
        "unique_positive_patient_clusters": len(groups),
        "one_sided_non_inferiority_alpha": (1 - confidence_level) / 2,
        "interpretation_note": "Exploratory percentile CI; assumptions, margin and operating characteristics require clinical/statistical justification."
    }
