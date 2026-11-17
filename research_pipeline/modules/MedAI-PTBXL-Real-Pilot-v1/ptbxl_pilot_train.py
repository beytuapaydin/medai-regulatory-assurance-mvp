#!/usr/bin/env python3
"""PTB-XL research-only pilot: fixed train/validation splits, standard-library WFDB format-16 reader.

This script never reads fold-10 waveforms, labels, or metadata; it is NOT clinical validation.
"""
from __future__ import annotations

import argparse
from array import array
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
import sys
from typing import Sequence

LEADS = ("I", "II", "III", "AVR", "AVL", "AVF", "V1", "V2", "V3", "V4", "V5", "V6")
RECORD_RE = re.compile(r"records100/\d{5}/\d{5}_lr\Z", re.ASCII)
GAIN_RE = re.compile(r"(?P<gain>\d+(?:\.\d+)?)(?:\((?P<baseline>-?\d+)\))?/(?P<unit>[A-Za-z]+)\Z", re.ASCII)
FEATURES_PER_LEAD = ("mean", "std", "p05_centered", "p95_centered", "mean_abs_diff", "peak_to_peak")
MODEL_CONFIGS = (("baseline", 1.0), ("candidate", 0.1))
MODEL_EPOCHS = 200
MODEL_LEARNING_RATE = 0.25
THRESHOLD = 0.5


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def official_hashes(sums_path: Path) -> dict[str, str]:
    if not sums_path.is_file():
        raise FileNotFoundError(f"Missing official checksum manifest: {sums_path}")
    hashes: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            continue
        raw = parts[1].strip().lstrip("*").replace("\\", "/")
        ix = raw.find("records100/")
        if ix >= 0:
            rel = raw[ix:]
            if ".." in Path(rel).parts or rel in hashes and hashes[rel] != parts[0].lower():
                raise ValueError(f"Malformed/duplicate checksum entry: {rel}")
            hashes[rel] = parts[0].lower()
    if not hashes:
        raise ValueError("Official checksum manifest has no records100 entries")
    return hashes


def verify_record_files(root: Path, relative: str, hashes: dict[str, str]) -> None:
    if not RECORD_RE.fullmatch(relative):
        raise ValueError(f"Unsafe or unsupported record name: {relative!r}")
    for suffix in (".hea", ".dat"):
        rel = relative + suffix
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"Missing waveform file: {path}")
        if rel not in hashes:
            raise ValueError(f"No official checksum for {rel}")
        if suffix == ".dat" and path.stat().st_size != 24000:
            raise ValueError(f"Wrong waveform byte count: {rel}")
        if digest(path) != hashes[rel]:
            raise ValueError(f"Checksum mismatch: {rel}")


def read_features(root: Path, relative: str) -> list[float]:
    """Strict PTB-XL 100-Hz, 12-lead, single-file WFDB-16 subset.

    Digital-to-physical conversion is (digital - baseline)/gain, in mV.
    Rejects unsupported WFDB variants rather than guessing calibration.
    """
    if not RECORD_RE.fullmatch(relative):
        raise ValueError(f"Unsafe or unsupported waveform path: {relative!r}")
    base = root / relative
    hea = Path(str(base) + ".hea")
    dat = Path(str(base) + ".dat")
    lines = [line.strip() for line in hea.read_text(encoding="ascii").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) < 13:
        raise ValueError(f"Incomplete WFDB header: {relative}")
    head = lines[0].split()
    if len(head) < 4 or head[0] != base.name or head[1] != "12" or float(head[2]) != 100 or head[3] != "1000":
        raise ValueError(f"Unsupported record descriptor: {relative}")
    channels = [line.split() for line in lines[1:13]]
    if any(len(ch) < 9 for ch in channels):
        raise ValueError(f"Incomplete signal descriptors: {relative}")
    if tuple(ch[-1].upper() for ch in channels) != LEADS:
        raise ValueError(f"Unexpected leads/order: {relative}")
    datname = base.name + ".dat"
    if any(ch[0] != datname or ch[1] != "16" for ch in channels):
        raise ValueError(f"Unsupported WFDB encoding/storage: {relative}")
    gains = []
    baselines = []
    for ch in channels:
        match = GAIN_RE.fullmatch(ch[2])
        if match is None or match.group("unit").lower() != "mv":
            raise ValueError(f"Unsupported WFDB units/calibration: {relative}")
        gain = float(match.group("gain"))
        if not math.isfinite(gain) or gain <= 0:
            raise ValueError(f"Invalid ADC gain: {relative}")
        adc_zero = int(ch[4])
        baseline = int(match.group("baseline")) if match.group("baseline") is not None else adc_zero
        gains.append(gain)
        baselines.append(baseline)
    raw = dat.read_bytes()
    if len(raw) != 24000:
        raise ValueError(f"Wrong WFDB binary length: {relative}")
    values = array("h")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) != 12000:
        raise ValueError(f"Incorrect sample count: {relative}")
    if -32768 in values:
        raise ValueError(f"Missing-value sentinel detected in waveform: {relative}")
    features: list[float] = []
    for j in range(12):
        series = [(int(d) - baselines[j]) / gains[j] for d in values[j::12]]
        ordered = sorted(series)
        mu = sum(series) / len(series)
        std = math.sqrt(sum((x - mu) ** 2 for x in series) / len(series))
        median = (ordered[499] + ordered[500]) / 2
        features.extend((
            mu, std, ordered[50] - median, ordered[949] - median,
            sum(abs(a-b) for a, b in zip(series[1:], series[:-1])) / 999,
            ordered[-1] - ordered[0],
        ))
    if len(features) != 72 or not all(math.isfinite(v) for v in features):
        raise ValueError(f"Invalid extracted features: {relative}")
    return features


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def train_logistic(features: Sequence[Sequence[float]], labels: Sequence[int], l2: float,
                   epochs: int = MODEL_EPOCHS, lr: float = MODEL_LEARNING_RATE) -> dict:
    if not features or len(features) != len(labels):
        raise ValueError("Invalid training features/labels")
    if set(labels) != {0, 1}:
        raise ValueError("Both classes required for training")
    count = len(features)
    dim = len(features[0])
    if dim == 0 or any(len(x) != dim for x in features):
        raise ValueError("Nonrectangular feature matrix")
    means = [sum(x[j] for x in features) / count for j in range(dim)]
    stds = [max(math.sqrt(sum((x[j] - means[j]) ** 2 for x in features) / count), 1e-8)
            for j in range(dim)]
    X = [[(x[j] - means[j]) / stds[j] for j in range(dim)] for x in features]
    n_pos = sum(labels)
    weights = [0.0] * dim
    bias = math.log(n_pos / (count - n_pos))
    for _ in range(epochs):
        grad = [0.0] * dim
        grad_b = 0.0
        for x, y in zip(X, labels):
            prob = sigmoid(sum(w*v for w, v in zip(weights, x)) + bias)
            delta = prob - y
            grad_b += delta
            for j, v in enumerate(x):
                grad[j] += delta * v
        bias -= lr * grad_b / count
        for j in range(dim):
            weights[j] -= lr * (grad[j] / count + l2 * weights[j])
    if not all(math.isfinite(x) for x in [bias, *weights]):
        raise ValueError("Non-finite model")
    return {"type": "l2_logistic_regression", "intercept": bias,
            "weights": weights, "feature_mean": means, "feature_std": stds,
            "l2_penalty": l2, "epochs": epochs, "learning_rate": lr,
            "decision_threshold": THRESHOLD, "features_per_lead": list(FEATURES_PER_LEAD),
            "lead_order": list(LEADS)}


def predict(model: dict, features: Sequence[float]) -> float:
    if len(features) != len(model["weights"]):
        raise ValueError("Wrong model feature dimension")
    z = model["intercept"] + sum(
        w * (x - mean) / std for w, x, mean, std in zip(
            model["weights"], features, model["feature_mean"], model["feature_std"])
    )
    return sigmoid(z)


def calculate_metrics(labels: Sequence[int], probabilities: Sequence[float]) -> dict:
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("Missing validation predictions")
    tp = tn = fp = fn = 0
    for y, p in zip(labels, probabilities):
        if y not in (0, 1) or not math.isfinite(p) or not 0.0 <= p <= 1.0:
            raise ValueError("Invalid validation label/probability")
        pred = int(p >= THRESHOLD)
        if y == 1 and pred == 1: tp += 1
        elif y == 1: fn += 1
        elif pred == 0: tn += 1
        else: fp += 1
    npos, nneg = tp+fn, tn+fp
    positives = [p for p, y in zip(probabilities, labels) if y == 1]
    negatives = [p for p, y in zip(probabilities, labels) if y == 0]
    auroc = None
    if positives and negatives:
        wins = sum((p > n) + 0.5*(p == n) for p in positives for n in negatives)
        auroc = wins / (len(positives)*len(negatives))
    return {"n": len(labels), "positive": npos, "negative": nneg,
            "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "sensitivity": tp/npos if npos else None,
            "specificity": tn/nneg if nneg else None,
            "accuracy": (tp+tn)/len(labels),
            "balanced_accuracy": ((tp/npos)+(tn/nneg))/2 if npos and nneg else None,
            "auroc": auroc}


def canonical_patient_id(value: str) -> str:
    if (not isinstance(value, str) or not value or value != value.strip()
            or any(ch.isspace() or unicodedata.category(ch) in ("Cf", "Cc") for ch in value)):
        raise ValueError("Malformed or invisible-character patient identifier")
    lowered = value.casefold()
    return re.sub(r"(?<=\d)\.0+\Z", "", lowered) if re.fullmatch(r"\d+\.0+", lowered) else lowered


def load_split(path: Path, allowed_folds: set[int]) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Missing split records: {path}")
    seen_ecgs: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or int(row["strat_fold"]) not in allowed_folds:
            raise ValueError(f"Illegal fold in {path}")
        if row.get("y_true") not in (0, 1) or type(row["y_true"]) is not int:
            raise ValueError(f"Illegal MI ground truth in {path}")
        canonical_patient_id(row.get("patient_id"))
        rel = row.get("filename_lr")
        if not isinstance(rel, str) or not RECORD_RE.fullmatch(rel):
            raise ValueError(f"Unsafe record path in {path}")
        ecg = str(row["ecg_id"])
        if ecg in seen_ecgs:
            raise ValueError(f"Duplicate ECG ID in {path}: {ecg}")
        seen_ecgs.add(ecg)
    return rows


def output_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path.home() / "Documents/MedAI-Data/ptb-xl-1.0.3")
    args = parser.parse_args()
    root = args.data_dir.resolve()
    pilot = root / "benchmark_v1" / "pilot_v1"
    train_path, val_path = pilot / "pilot_train.json", pilot / "pilot_validation.json"
    train_rows = load_split(train_path, set(range(1, 9)))
    val_rows = load_split(val_path, {9})
    manifest = json.loads((pilot / "pilot_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "EXPLORATORY_PILOT" or manifest.get("patient_overlap") != 0:
        raise ValueError("Expected an exploratory pilot with zero patient overlap")
    train_ids = {canonical_patient_id(row["patient_id"]) for row in train_rows}
    val_ids = {canonical_patient_id(row["patient_id"]) for row in val_rows}
    if train_ids & val_ids:
        raise ValueError("Patient leakage between training and validation")
    print(f"Pilot: train={len(train_rows)}, validation={len(val_rows)}; fold 10 NOT accessed", flush=True)
    hashes = official_hashes(root / "SHA256SUMS.txt")
    X_train, y_train = [], []
    X_val, y_val = [], []
    for label, rows, X, Y in (("TRAIN", train_rows, X_train, y_train), ("VALIDATION", val_rows, X_val, y_val)):
        for i, row in enumerate(rows, 1):
            rel = row["filename_lr"]
            verify_record_files(root, rel, hashes)
            X.append(read_features(root, rel))
            Y.append(row["y_true"])
            if i % 200 == 0 or i == len(rows):
                print(f"{label}: verified and calibrated {i}/{len(rows)} EKG", flush=True)
    outdir = pilot / "model_v1"
    outdir.mkdir(exist_ok=True)
    predictions: dict[str, list[float]] = {}
    models: dict[str, dict] = {}
    scores: dict[str, dict] = {}
    for name, l2 in MODEL_CONFIGS:
        model = train_logistic(X_train, y_train, l2)
        p = [predict(model, x) for x in X_val]
        models[name] = model
        predictions[name] = p
        scores[name] = calculate_metrics(y_val, p)
    with (outdir / "validation_predictions.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("ecg_id", "patient_id", "strat_fold", "age", "y_true", "baseline_probability", "baseline_pred", "candidate_probability", "candidate_pred"))
        for i, row in enumerate(val_rows):
            p1, p2 = predictions["baseline"][i], predictions["candidate"][i]
            writer.writerow((row["ecg_id"], row["patient_id"], 9, row["age"], row["y_true"],
                             format(p1, ".12g"), int(p1 >= THRESHOLD), format(p2, ".12g"), int(p2 >= THRESHOLD)))
    model_path = outdir / "models.json"
    output_json(model_path, {"baseline": models["baseline"], "candidate": models["candidate"]})
    report = {
        "status": "EXPLORATORY_VALIDATION_ONLY_NOT_A_CLINICAL_GATE",
        "dataset": "PTB-XL v1.0.3 / non-random interrupted-download subset",
        "real_waveforms_used": True,
        "raw_waveform_files_sha256_checked": 2*(len(train_rows)+len(val_rows)),
        "physical_calibration": "WFDB format 16; mV = (digital-baseline)/gain",
        "train_records": len(train_rows), "validation_records": len(val_rows),
        "train_mi_positive": sum(y_train), "validation_mi_positive": sum(y_val),
        "train_patient_count": len(train_ids), "validation_patient_count": len(val_ids),
        "patient_overlap": 0,
        "fold_10_used": False,
        "validation_age75_plus_mi_positive": sum(int(r["y_true"] == 1 and bool(r["age"]) and float(r["age"]) >= 75) for r in val_rows),
        "required_age75_plus_positive_patients_for_medai_gate": 30,
        "medai_gate_status": "NOT_EVALUATED",
        "clinical_validity": "NOT_ESTABLISHED",
        "selection_bias": "Training/validation subsets are convenience samples from interrupted sequential downloads; no external performance inference",
        "training": {"algorithm": "deterministic full-batch L2 logistic regression", "features": "72 lead-wise signal summary features", "epochs": MODEL_EPOCHS, "learning_rate": MODEL_LEARNING_RATE, "threshold": THRESHOLD, "candidate_policy": "Prespecified different L2 strength, not selected using validation"},
        "validation_metrics": scores,
        "manifest_sha256": digest(pilot / "pilot_manifest.json"),
        "train_list_sha256": digest(train_path),
        "validation_list_sha256": digest(val_path),
        "official_sums_file_sha256": digest(root / "SHA256SUMS.txt"),
        "models_sha256": digest(model_path),
        "validation_predictions_sha256": digest(outdir / "validation_predictions.csv"),
    }
    output_json(outdir / "pilot_model_report.json", report)
    print("\nEXPLORATORY REAL-EKG VALIDATION ONLY (not MedAI PASS):")
    for name in ("baseline", "candidate"):
        m = scores[name]
        print(f"{name}: sensitivity={m['sensitivity']:.3f}, specificity={m['specificity']:.3f}, "
              f"AUROC={m['auroc']:.3f}, TP={m['tp']}, FN={m['fn']}, FP={m['fp']}, TN={m['tn']}")
    print("MEDAI CLINICAL GATE: NOT_EVALUATED")
    print("FOLD 10: UNTOUCHED")
    print("PILOT REAL SIGNAL TRAINING: COMPLETE")
    print("OUTPUT:", outdir)


if __name__ == "__main__":
    main()
