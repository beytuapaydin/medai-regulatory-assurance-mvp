#!/usr/bin/env python3
"""Research-only, post-hoc threshold diagnostics for PTB-XL fold-9 pilot.

Reads existing predictions only. Does not train models, select a locked
threshold, create a clinical EvidencePackage, or touch fold 10.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Sequence

MODEL_COLS = {
    "baseline": ("baseline_probability", "baseline_pred"),
    "candidate": ("candidate_probability", "candidate_pred"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_predictions(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"ecg_id", "patient_id", "strat_fold", "age", "y_true"}
        for prob_col, pred_col in MODEL_COLS.values():
            required.update((prob_col, pred_col))
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("Missing required prediction CSV columns")
        rows = list(reader)
    if not rows:
        raise ValueError("No validation predictions")
    seen = set()
    for row in rows:
        if row["strat_fold"] != "9":
            raise ValueError("Only fold 9 predictions allowed; fold 10 is out of scope")
        if not row["ecg_id"] or row["ecg_id"] in seen:
            raise ValueError("Missing/duplicate ECG ID")
        seen.add(row["ecg_id"])
        if row["y_true"] not in ("0", "1"):
            raise ValueError("Invalid ground-truth label")
        for prob_col, pred_col in MODEL_COLS.values():
            value = float(row[prob_col])
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Invalid probability")
            if row[pred_col] not in ("0", "1"):
                raise ValueError("Invalid original prediction")
            if int(row[pred_col]) != int(value >= 0.5):
                # CSV serializes p to 12 significant digits. Boundary ambiguity
                # at exact 0.5 is refused instead of silently changing output.
                raise ValueError("Original prediction inconsistent with threshold 0.5")
    return rows


def score(labels: Sequence[int], probs: Sequence[float], threshold: float) -> dict:
    if len(labels) != len(probs) or not labels:
        raise ValueError("Mismatched labels/probabilities")
    tp = fp = tn = fn = 0
    for y, p in zip(labels, probs):
        predicted = p >= threshold
        if y == 1:
            if predicted: tp += 1
            else: fn += 1
        else:
            if predicted: fp += 1
            else: tn += 1
    sens = tp / (tp + fn) if tp + fn else None
    spec = tn / (tn + fp) if tn + fp else None
    precision = tp / (tp + fp) if tp + fp else None
    return {
        "threshold": threshold, "n": len(labels),
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "sensitivity": sens, "specificity": spec,
        "precision": precision,
        "balanced_accuracy": (sens + spec) / 2 if sens is not None and spec is not None else None,
    }


def threshold_sweep(labels: Sequence[int], probs: Sequence[float]) -> list[dict]:
    # Every distinct probability changes predictions only at a unique boundary.
    thresholds = sorted(set([0.0, 0.5, 1.0, math.nextafter(1.0, 2.0), *probs]))
    return [score(labels, probs, thr) for thr in thresholds]


def best_at_specificity(sweep: list[dict], minimum: float) -> dict | None:
    subset = [s for s in sweep if s["specificity"] is not None and
              s["sensitivity"] is not None and s["specificity"] >= minimum]
    if not subset:
        return None
    # Transparent ranking, not a clinically qualified threshold-locking rule.
    return max(subset, key=lambda s: (s["sensitivity"], s["specificity"], s["threshold"]))


def quantiles(values: Sequence[float]) -> dict:
    if not values:
        return {"min": None, "median": None, "max": None}
    x = sorted(values)
    n = len(x)
    mid = x[n // 2] if n % 2 else (x[n // 2 - 1] + x[n // 2]) / 2
    return {"min": x[0], "median": mid, "max": x[-1]}


def main():
    root = Path.home() / "Documents" / "MedAI-Data" / "ptb-xl-1.0.3"
    output = root / "benchmark_v1" / "pilot_v1" / "model_v1"
    pred = output / "validation_predictions.csv"
    rows = read_predictions(pred)
    labels = [int(r["y_true"]) for r in rows]
    if not (0 < sum(labels) < len(labels)):
        raise ValueError("Both classes required")
    report = {
        "status": "POST_HOC_EXPLORATORY_DIAGNOSTICS_ONLY",
        "scope": "existing fold-9 convenience subset",
        "independent_validation": False,
        "threshold_selection_for_deployment": False,
        "clinical_gate": "NOT_EVALUATED",
        "fold_10_accessed": False,
        "predictions_file_sha256": sha256(pred),
        "validation_n": len(rows),
        "validation_mi": sum(labels),
        "models": {},
    }
    print("EXPLORATORY FOLD-9 THRESHOLD DIAGNOSTICS (NOT CLINICAL VALIDATION)")
    print(f"Validation: n={len(rows)}, MI={sum(labels)}, non-MI={len(rows)-sum(labels)}")
    for name, (prob_col, _) in MODEL_COLS.items():
        probs = [float(r[prob_col]) for r in rows]
        sweep = threshold_sweep(labels, probs)
        fixed = score(labels, probs, 0.5)
        at_90_spec = best_at_specificity(sweep, 0.9)
        at_95_spec = best_at_specificity(sweep, 0.95)
        pos_dist = quantiles([p for y, p in zip(labels, probs) if y])
        neg_dist = quantiles([p for y, p in zip(labels, probs) if not y])
        report["models"][name] = {
            "fixed_0_5": fixed,
            "posthoc_best_sensitivity_at_spec_gte_0_90": at_90_spec,
            "posthoc_best_sensitivity_at_spec_gte_0_95": at_95_spec,
            "positive_probability_distribution": pos_dist,
            "negative_probability_distribution": neg_dist,
            "threshold_sweep": sweep,
        }
        print(f"\n{name.upper()}")
        print(f"  Fixed threshold 0.50: TP={fixed['tp']} FN={fixed['fn']} "
              f"FP={fixed['fp']} TN={fixed['tn']} "
              f"sensitivity={fixed['sensitivity']:.3f} specificity={fixed['specificity']:.3f}")
        for min_spec, best in ((0.90, at_90_spec), (0.95, at_95_spec)):
            if best:
                print(f"  POST-HOC spec >= {min_spec:.0%}: threshold={best['threshold']:.6g}, "
                      f"sensitivity={best['sensitivity']:.3f}, specificity={best['specificity']:.3f}, "
                      f"TP={best['tp']} FP={best['fp']}")
        print(f"  Positive scores: {pos_dist}")
        print(f"  Negative scores: {neg_dist}")
    path = output / "threshold_diagnostics_exploratory.json"
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    print("\nWARNING: Post-hoc thresholds are optimistic; do not lock them or report as independent performance.")
    print("FOLD 10: UNTOUCHED")
    print("RESULT:", path)


if __name__ == "__main__":
    main()
