#!/usr/bin/env python3
"""Train-only, patient-fold OOF decision-threshold development for PTB-XL pilot.

Research engineering only. Does NOT access fold 10 or create a clinical PASS.
Fold 9 was already examined post-hoc and is now a development-only diagnostic.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from ptbxl_pilot_train import (
    MODEL_CONFIGS, THRESHOLD,
    canonical_patient_id, digest, load_split, official_hashes,
    read_features, train_logistic, predict, verify_record_files,
)

TARGET_SPECIFICITY = 0.90
DEVELOPMENT_FOLDS = tuple(range(1, 9))


def performance(labels: list[int], scores: list[float], threshold: float) -> dict:
    if not labels or len(labels) != len(scores):
        raise ValueError("Labels and scores required, equal length")
    if any(type(y) is not int or y not in (0, 1) for y in labels):
        raise ValueError("Invalid binary labels")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in scores):
        raise ValueError("Invalid model scores")
    tp = sum(y == 1 and p >= threshold for y, p in zip(labels, scores))
    fn = sum(y == 1 and p < threshold for y, p in zip(labels, scores))
    fp = sum(y == 0 and p >= threshold for y, p in zip(labels, scores))
    tn = sum(y == 0 and p < threshold for y, p in zip(labels, scores))
    return {"threshold": threshold, "n": len(labels), "tp": tp, "fn": fn, "fp": fp,
            "tn": tn, "sensitivity": tp / (tp + fn) if tp + fn else None,
            "specificity": tn / (tn + fp) if tn + fp else None}


def select_train_only_threshold(labels: list[int], scores: list[float], minimum_specificity: float = TARGET_SPECIFICITY) -> dict:
    """Choose maximum observed OOF sensitivity with OOF specificity >= target.

    Tie-breaking: higher specificity, then higher threshold. Not a clinical policy.
    Threshold is drawn only from OOF scores. No fold-9 input permitted.
    """
    if not 0 < minimum_specificity <= 1:
        raise ValueError("Invalid specificity constraint")
    if set(labels) != {0, 1}:
        raise ValueError("Both classes required")
    options = sorted(set([0.0, 0.5, 1.0, math.nextafter(1.0, 2.0), *scores]))
    candidates = [performance(labels, scores, t) for t in options]
    eligible = [m for m in candidates if m["specificity"] >= minimum_specificity]
    if not eligible:
        raise RuntimeError("No threshold meets OOF specificity constraint")
    return max(eligible, key=lambda m: (m["sensitivity"], m["specificity"], m["threshold"]))


def oof_predict(X: list[list[float]], y: list[int], folds: list[int], l2: float) -> tuple[list[float], list[dict]]:
    if not X or len(X) != len(y) or len(y) != len(folds):
        raise ValueError("Inconsistent OOF data lengths")
    if set(folds) != set(DEVELOPMENT_FOLDS):
        raise ValueError("All eight development folds required")
    oof: list[float | None] = [None] * len(y)
    audit = []
    for holdout in DEVELOPMENT_FOLDS:
        train_idx = [i for i, fold in enumerate(folds) if fold != holdout]
        heldout_idx = [i for i, fold in enumerate(folds) if fold == holdout]
        assert train_idx and heldout_idx
        model = train_logistic([X[i] for i in train_idx], [y[i] for i in train_idx], l2)
        for i in heldout_idx:
            if oof[i] is not None:
                raise AssertionError("OOF prediction written twice")
            oof[i] = predict(model, X[i])
        audit.append({"heldout_fold": holdout, "training_records": len(train_idx),
                      "heldout_records": len(heldout_idx),
                      "train_positive": sum(y[i] for i in train_idx),
                      "heldout_positive": sum(y[i] for i in heldout_idx)})
    if any(p is None for p in oof):
        raise AssertionError("Incomplete OOF predictions")
    return [float(p) for p in oof], audit


def write_json(path: Path, obj: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(obj, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path,
                        default=Path.home() / "Documents/MedAI-Data/ptb-xl-1.0.3")
    args = parser.parse_args()
    root = args.data_dir.resolve()
    pilot = root / "benchmark_v1" / "pilot_v1"
    train_file = pilot / "pilot_train.json"
    val_file = pilot / "pilot_validation.json"
    manifest_file = pilot / "pilot_manifest.json"
    model_file = pilot / "model_v1" / "models.json"
    report_file = pilot / "model_v1" / "pilot_model_report.json"
    pred_file = pilot / "model_v1" / "validation_predictions.csv"

    train = load_split(train_file, set(DEVELOPMENT_FOLDS))
    val = load_split(val_file, {9})
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("status") != "EXPLORATORY_PILOT" or manifest.get("patient_overlap") != 0:
        raise ValueError("Unexpected pilot manifest")
    if len(train) != manifest["train"]["ecg"] or len(val) != manifest["validation"]["ecg"]:
        raise ValueError("Pilot manifests have inconsistent counts")
    patient_train = {canonical_patient_id(row["patient_id"]): int(row["strat_fold"]) for row in train}
    patient_val = {canonical_patient_id(row["patient_id"]) for row in val}
    if patient_val & patient_train.keys():
        raise ValueError("Patient overlap with fold-9 validation")
    for row in train:
        if patient_train[canonical_patient_id(row["patient_id"])] != int(row["strat_fold"]):
            raise ValueError("Patient appears in multiple development folds")
    ecg_train = {str(r["ecg_id"]) for r in train}
    if ecg_train & {str(r["ecg_id"]) for r in val}:
        raise ValueError("ECG overlap with validation")
    original_report = json.loads(report_file.read_text(encoding="utf-8"))
    if (original_report.get("status") != "EXPLORATORY_VALIDATION_ONLY_NOT_A_CLINICAL_GATE"
            or original_report.get("fold_10_used") is not False):
        raise ValueError("Expected research pilot report")
    for recorded, path in (("manifest_sha256", manifest_file),
                           ("train_list_sha256", train_file),
                           ("validation_list_sha256", val_file),
                           ("models_sha256", model_file),
                           ("validation_predictions_sha256", pred_file)):
        if original_report.get(recorded) != digest(path):
            raise ValueError(f"Original research evidence changed: {recorded}")
    models = json.loads(model_file.read_text(encoding="utf-8"))
    if set(models) != {name for name, _ in MODEL_CONFIGS}:
        raise ValueError("Unexpected model set")
    for name, l2 in MODEL_CONFIGS:
        if models[name].get("l2_penalty") != l2 or models[name].get("decision_threshold") != THRESHOLD:
            raise ValueError(f"Unexpected model configuration: {name}")

    with pred_file.open("r", encoding="utf-8-sig", newline="") as stream:
        prior_val_predictions = list(csv.DictReader(stream))
    if len(prior_val_predictions) != len(val):
        raise ValueError("Original validation prediction count changed")
    for a, b in zip(prior_val_predictions, val):
        if (a["ecg_id"] != str(b["ecg_id"]) or
                a["patient_id"] != str(b["patient_id"]) or
                a["strat_fold"] != "9" or a["y_true"] != str(b["y_true"])):
            raise ValueError("Validation CSV/manifest alignment mismatch")

    hashes = official_hashes(root / "SHA256SUMS.txt")
    X, y, folds = [], [], []
    for i, row in enumerate(train, 1):
        verify_record_files(root, row["filename_lr"], hashes)
        X.append(read_features(root, row["filename_lr"]))
        y.append(row["y_true"])
        folds.append(int(row["strat_fold"]))
        if i % 200 == 0 or i == len(train):
            print(f"TRAIN OOF features verified: {i}/{len(train)}", flush=True)

    # Original validation scores are already known and were already examined.
    # They cannot be used for selecting a threshold or model hyperparameter.
    y_val = [r["y_true"] for r in val]
    dest = pilot / "oof_thresholds_v1"
    dest.mkdir(exist_ok=True)
    results = {}
    oof_by_model = {}
    for name, l2 in MODEL_CONFIGS:
        probs, audit = oof_predict(X, y, folds, l2)
        selected = select_train_only_threshold(y, probs)
        val_probs = [float(row[f"{name}_probability"]) for row in prior_val_predictions]
        if any(not math.isfinite(p) or p < 0 or p > 1 for p in val_probs):
            raise ValueError("Invalid original validation score")
        dev_val = performance(y_val, val_probs, selected["threshold"])
        results[name] = {
            "l2_penalty": l2,
            "threshold_from_training_oof_only": selected["threshold"],
            "train_oof_selection_metrics_development_only": selected,
            "fold9_previously_inspected_development_diagnostic": dev_val,
            "oof_fold_audit": audit,
        }
        oof_by_model[name] = probs
        print(f"{name.upper()} train OOF: threshold={selected['threshold']:.6f} "
              f"sensitivity={selected['sensitivity']:.3f} specificity={selected['specificity']:.3f}", flush=True)
        print(f"{name.upper()} fold-9 development diagnostic: "
              f"sensitivity={dev_val['sensitivity']:.3f} "
              f"specificity={dev_val['specificity']:.3f} "
              f"TP={dev_val['tp']} FN={dev_val['fn']} "
              f"FP={dev_val['fp']} TN={dev_val['tn']}", flush=True)

    oof_file = dest / "training_oof_predictions.csv"
    with oof_file.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("ecg_id", "strat_fold", "y_true", "baseline_probability", "candidate_probability"))
        for i, row in enumerate(train):
            writer.writerow((row["ecg_id"], row["strat_fold"], row["y_true"],
                             format(oof_by_model["baseline"][i], ".17g"),
                             format(oof_by_model["candidate"][i], ".17g")))
    report = {
        "status": "OOF_TRAIN_ONLY_THRESHOLD_DEVELOPMENT_NOT_CLINICAL_VALIDATION",
        "dataset": "PTB-XL v1.0.3 interrupted-download convenience sample",
        "split_policy": "8-fold leave-one-strat_fold-out OOF on folds 1-8",
        "specificity_development_target": TARGET_SPECIFICITY,
        "threshold_selection_rule": "Max train-OOF sensitivity subject to train-OOF specificity >= 0.90; tie: specificity then higher threshold",
        "fold9_was_previously_inspected": True,
        "fold9_status": "CONTAMINATED_DEVELOPMENT_DIAGNOSTIC_NOT_INDEPENDENT",
        "fold10_used": False,
        "medai_clinical_gate": "NOT_EVALUATED",
        "clinical_validity": "NOT_ESTABLISHED",
        "thresholds_not_clinically_qualified": True,
        "train_count": len(train), "validation_count": len(val),
        "train_mi_positive": sum(y), "validation_mi_positive": sum(y_val),
        "original_pilot_report_sha256": digest(report_file),
        "training_manifest_sha256": digest(train_file),
        "original_validation_predictions_sha256": digest(pred_file),
        "training_oof_predictions_sha256": digest(oof_file),
        "models": results,
    }
    write_json(dest / "oof_threshold_development_report.json", report)
    print("\nMODEL THRESHOLDS: TRAIN OOF ONLY / RESEARCH", flush=True)
    print("FOLD 9: ALREADY INSPECTED / NOT INDEPENDENT", flush=True)
    print("FOLD 10: NOT ACCESSED", flush=True)
    print("MEDAI CLINICAL GATE: NOT_EVALUATED", flush=True)
    print("OOF THRESHOLD DEVELOPMENT: COMPLETE", flush=True)
    print("OUTPUT:", dest, flush=True)


if __name__ == "__main__":
    main()
