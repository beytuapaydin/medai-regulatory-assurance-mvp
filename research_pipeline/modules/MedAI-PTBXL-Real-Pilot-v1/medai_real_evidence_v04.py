#!/usr/bin/env python3
"""MedAI Real Pilot Research Evidence Adapter v0.4.

Creates and independently re-verifies a RESEARCH-ONLY evidence envelope
from the PTB-XL pilot v1 and OOF-threshold outputs. No clinical PASS, no CE/MDR
claim, no fold-10 waveforms/labels/predictions, and no MedAI clinical-gate call.

Python standard library only; no pandas or WFDB imports.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA = "medai-ptbxl-research-evidence-v0.4"
REQUIRED_MODELS = ("baseline", "candidate")
SOURCE_PREFIX = "benchmark_v1/pilot_v1"
RECORD_RE = re.compile(r"records100/\d{5}/\d{5}_lr\Z", re.ASCII)
HASH_RE = re.compile(r"[a-fA-F0-9]{64}\Z", re.ASCII)
MIN_SPEC = 0.90


class EvidenceError(ValueError):
    """Fail-closed input verification failure."""


def check(condition: bool, reason: str) -> None:
    if not condition:
        raise EvidenceError(reason)


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def doc_sha(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path, cols: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        check(reader.fieldnames is not None and tuple(reader.fieldnames) == cols,
              f"Unexpected CSV schema: {path.name}")
        rows = list(reader)
    check(bool(rows) and all(set(row) == set(cols) and
                             all(row[k] is not None for k in cols) for row in rows),
          f"Empty or malformed CSV: {path.name}")
    return rows


def patient_id(value: Any) -> str:
    check(isinstance(value, str) and bool(value) and value == value.strip(),
          "Invalid patient identifier")
    check(not any(ch.isspace() or unicodedata.category(ch) in ("Cf", "Cc") for ch in value),
          "Invisible characters in patient identifier")
    lowered = value.casefold()
    if re.fullmatch(r"\d+\.0+", lowered):
        lowered = lowered.split(".")[0]
    return lowered


def ecg_id(value: Any) -> str:
    s = str(value)
    check(bool(re.fullmatch(r"[1-9]\d*", s, re.ASCII)), "Invalid ECG identifier")
    return s


def age75(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    try:
        age = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError("Invalid age value") from exc
    check(math.isfinite(age) and 0 <= age <= 300 and
          (age <= 120 or age == 300), "Invalid age field; PTB-XL 300 is >89 sentinel")
    return age >= 75


def load_split(path: Path, allowed: set[int]) -> list[dict]:
    records = json_file(path)
    check(isinstance(records, list) and bool(records), f"Empty split: {path.name}")
    seen_ecgs: set[str] = set()
    seen_patients: dict[str, int] = {}
    for r in records:
        check(isinstance(r, dict), "Malformed split record")
        check(type(r.get("strat_fold")) is int and r["strat_fold"] in allowed,
              f"Forbidden fold in {path.name}")
        check(type(r.get("y_true")) is int and r["y_true"] in (0, 1),
              "Invalid ground truth")
        eid = ecg_id(r.get("ecg_id"))
        check(eid not in seen_ecgs, f"Duplicate ECG {eid}")
        seen_ecgs.add(eid)
        pid = patient_id(r.get("patient_id"))
        if pid in seen_patients:
            check(seen_patients[pid] == r["strat_fold"],
                  "Patient appears in multiple folds")
        seen_patients[pid] = r["strat_fold"]
        check(isinstance(r.get("filename_lr"), str) and
              bool(RECORD_RE.fullmatch(r["filename_lr"])), "Unsafe waveform path")
        age75(r.get("age"))
    return records


def score(s: Any) -> float:
    try:
        value = float(s)
    except (TypeError, ValueError) as exc:
        raise EvidenceError("Invalid probability") from exc
    check(math.isfinite(value) and 0 <= value <= 1, "Probability outside [0, 1]")
    return value


def metrics(labels: list[int], probabilities: list[float], threshold: float) -> dict:
    check(bool(labels) and len(labels) == len(probabilities), "Invalid metric inputs")
    check(math.isfinite(threshold) and 0 <= threshold <= math.nextafter(1, 2),
          "Invalid decision threshold")
    tp = sum(y == 1 and p >= threshold for y, p in zip(labels, probabilities))
    fn = sum(y == 1 and p < threshold for y, p in zip(labels, probabilities))
    fp = sum(y == 0 and p >= threshold for y, p in zip(labels, probabilities))
    tn = sum(y == 0 and p < threshold for y, p in zip(labels, probabilities))
    return {"n": len(labels), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "sensitivity": tp / (tp + fn) if tp + fn else None,
            "specificity": tn / (tn + fp) if tn + fp else None}


def oof_threshold(labels: list[int], probs: list[float], min_spec: float = MIN_SPEC) -> dict:
    check(set(labels) == {0, 1} and len(labels) == len(probs),
          "OOF needs both classes")
    check(0 < min_spec <= 1, "Invalid specificity development target")
    options = sorted(set([0.0, 0.5, 1.0, math.nextafter(1.0, 2.0), *probs]))
    permitted = [metrics(labels, probs, t) | {"threshold": t} for t in options]
    eligible = [m for m in permitted if m["specificity"] is not None and
                m["specificity"] >= min_spec]
    check(bool(eligible), "No feasible OOF threshold")
    return max(eligible, key=lambda m: (m["sensitivity"], m["specificity"], m["threshold"]))


def close_metric(x: Any, y: Any) -> bool:
    if x is None or y is None:
        return x is y
    return type(x) in (int, float) and abs(x - y) <= 1e-9


def verify_metric_report(expected: dict, observed: dict, context: str) -> None:
    check(isinstance(observed, dict), f"Missing metrics in {context}")
    for key, value in expected.items():
        check(close_metric(observed.get(key), value),
              f"{context}: metric mismatch for {key}: {observed.get(key)} != {value}")


def official_hashes(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not HASH_RE.fullmatch(parts[0]):
            continue
        name = parts[1].strip().lstrip("*").replace("\\", "/")
        ix = name.find("records100/")
        if ix < 0:
            continue
        relative = name[ix:]
        check(relative not in result or result[relative] == parts[0].lower(),
              "Conflicting hashes in official sums file")
        result[relative] = parts[0].lower()
    check(bool(result), "No records100 hashes")
    return result


def verify_waveform_hashes(root: Path, rows: list[dict], hashes: dict[str, str]) -> int:
    count = 0
    for r in rows:
        relative = r["filename_lr"]
        check(bool(RECORD_RE.fullmatch(relative)), "Unsafe relative waveform path")
        for ext in (".hea", ".dat"):
            key = relative + ext
            path = root / key
            check(key in hashes and path.is_file(), f"Missing waveform/hash: {key}")
            if ext == ".dat":
                check(path.stat().st_size == 24000, f"Unexpected DAT size: {key}")
            check(file_sha(path) == hashes[key], f"Waveform SHA-256 mismatch: {key}")
            count += 1
    return count


def validate_protocol(protocol: dict) -> None:
    check(isinstance(protocol, dict) and protocol.get("schema_version") == "medai-protocol-v0.2",
          "Unsupported trusted protocol")
    check(protocol.get("demonstration_only") is True and
          isinstance(protocol.get("dataset"), dict) and
          protocol["dataset"].get("required_test_fold") == 10,
          "Not a research-only locked fold-10 demonstration protocol")
    check(protocol["dataset"].get("reference_name") == "PTB-XL" and
          protocol["dataset"].get("reference_version") == "1.0.3",
          "Wrong dataset/version in protocol")
    groups = protocol.get("required_subgroups")
    check(isinstance(groups, list) and set(groups) == {"ALL", "AGE75_PLUS"} and
          len(groups) == 2, "Unsupported required subgroups")
    rules = protocol.get("rules")
    check(isinstance(rules, dict), "Missing acceptance rules")
    for k in ("min_positive_records", "min_negative_records",
              "min_positive_patients", "min_negative_patients"):
        check(type(rules.get(k)) is int and rules[k] >= 1, f"Invalid protocol rule {k}")
    for k in ("protocol_id", "protocol_version", "clinical_claim_id", "risk_control_id"):
        check(isinstance(protocol.get(k), str) and bool(protocol[k].strip()),
              f"Missing protocol field {k}")


def group_assessment(rows: list[dict], predictions: dict[str, list[float]],
                     thresholds: dict[str, float], protocol: dict, group: str) -> dict:
    check(group in {"ALL", "AGE75_PLUS"}, "Unknown subgroup")
    indices = [i for i, r in enumerate(rows) if group == "ALL" or age75(r.get("age")) is True]
    subset = [rows[i] for i in indices]
    pos = [r for r in subset if r["y_true"] == 1]
    neg = [r for r in subset if r["y_true"] == 0]
    counts = {"n_total": len(subset), "n_positive_records": len(pos),
              "n_negative_records": len(neg),
              "n_positive_patients": len({patient_id(r["patient_id"]) for r in pos}),
              "n_negative_patients": len({patient_id(r["patient_id"]) for r in neg}),
              "n_missing_age_all_records": sum(age75(r.get("age")) is None for r in rows)}
    rules = protocol["rules"]
    requirements = {
        "n_positive_records": "min_positive_records",
        "n_negative_records": "min_negative_records",
        "n_positive_patients": "min_positive_patients",
        "n_negative_patients": "min_negative_patients",
    }
    shortfalls = [f"{k}: observed {counts[k]} < required {rules[v]}"
                  for k, v in requirements.items() if counts[k] < rules[v]]
    if group == "AGE75_PLUS" and counts["n_missing_age_all_records"]:
        shortfalls.append("Unknown ages: subgroup membership is not fully established")
    evaluation = {
        "cohort_id": group,
        "counts": counts,
        "sample_adequacy_for_demonstration_rules": "INSUFFICIENT_EVIDENCE" if shortfalls else "COUNTS_ONLY_SUFFICIENT",
        "sample_shortfalls": shortfalls,
        "diagnostic_only_previously_inspected_fold9": {},
    }
    y = [r["y_true"] for r in subset]
    for name in REQUIRED_MODELS:
        selected = [predictions[name][i] for i in indices]
        evaluation["diagnostic_only_previously_inspected_fold9"][name] = (
            metrics(y, selected, thresholds[name]) if y else None)
    return evaluation


def build(root: Path, protocol_path: Path) -> dict:
    """Recompute evidence entirely from local source inputs; fold 10 never read."""
    pilot = root / "benchmark_v1" / "pilot_v1"
    model_dir = pilot / "model_v1"
    oof_dir = pilot / "oof_thresholds_v1"
    sources = {
        "pilot_manifest": pilot / "pilot_manifest.json",
        "train_manifest": pilot / "pilot_train.json",
        "validation_manifest": pilot / "pilot_validation.json",
        "pilot_model_report": model_dir / "pilot_model_report.json",
        "models": model_dir / "models.json",
        "validation_predictions": model_dir / "validation_predictions.csv",
        "oof_report": oof_dir / "oof_threshold_development_report.json",
        "training_oof_predictions": oof_dir / "training_oof_predictions.csv",
        "official_sums": root / "SHA256SUMS.txt",
    }
    for name, path in sources.items():
        check(path.is_file(), f"Missing source {name}: {path}")
    check(protocol_path.is_file(), f"Trusted protocol unavailable: {protocol_path}")
    protocol = json_file(protocol_path)
    validate_protocol(protocol)
    train = load_split(sources["train_manifest"], set(range(1, 9)))
    val = load_split(sources["validation_manifest"], {9})
    check({patient_id(r["patient_id"]) for r in train}.isdisjoint(
          {patient_id(r["patient_id"]) for r in val}), "TRAIN/VALIDATION PATIENT LEAKAGE")
    check({ecg_id(r["ecg_id"]) for r in train}.isdisjoint(
          {ecg_id(r["ecg_id"]) for r in val}), "TRAIN/VALIDATION ECG LEAKAGE")
    check({r["strat_fold"] for r in train} == set(range(1, 9)),
          "Missing OOF training folds")
    manifest = json_file(sources["pilot_manifest"])
    check(isinstance(manifest, dict) and manifest.get("status") == "EXPLORATORY_PILOT" and
          manifest.get("patient_overlap") == 0 and
          manifest.get("selection") == "Records available after interrupted download",
          "Pilot manifest does not describe a convenience sample")
    check(manifest.get("train", {}).get("ecg") == len(train) and
          manifest.get("validation", {}).get("ecg") == len(val), "Pilot size mismatch")
    pilot_report = json_file(sources["pilot_model_report"])
    check(pilot_report.get("status") == "EXPLORATORY_VALIDATION_ONLY_NOT_A_CLINICAL_GATE" and
          pilot_report.get("fold_10_used") is False and
          pilot_report.get("medai_gate_status") == "NOT_EVALUATED" and
          pilot_report.get("clinical_validity") == "NOT_ESTABLISHED" and
          pilot_report.get("patient_overlap") == 0, "Pilot report not research-only")
    check(pilot_report.get("raw_waveform_files_sha256_checked") == 2 * (len(train) + len(val)) and
          pilot_report.get("real_waveforms_used") is True and
          pilot_report.get("train_records") == len(train) and
          pilot_report.get("validation_records") == len(val), "Pilot report counts inconsistent")
    check(pilot_report.get("train_mi_positive") == sum(r["y_true"] for r in train) and
          pilot_report.get("validation_mi_positive") == sum(r["y_true"] for r in val),
          "Pilot report label totals inconsistent")
    check(pilot_report.get("validation_age75_plus_mi_positive") ==
          sum(r["y_true"] for r in val if age75(r.get("age")) is True),
          "Pilot age75 count inconsistent")
    expected_original_hashes = {
        "manifest_sha256": "pilot_manifest",
        "train_list_sha256": "train_manifest",
        "validation_list_sha256": "validation_manifest",
        "models_sha256": "models",
        "validation_predictions_sha256": "validation_predictions",
        "official_sums_file_sha256": "official_sums",
    }
    for report_key, source_key in expected_original_hashes.items():
        check(pilot_report.get(report_key) == file_sha(sources[source_key]),
              f"Original pilot report SHA mismatch: {report_key}")
    model_definitions = json_file(sources["models"])
    check(isinstance(model_definitions, dict) and set(model_definitions) == set(REQUIRED_MODELS),
          "Model names inconsistent")
    for name in REQUIRED_MODELS:
        check(model_definitions[name].get("type") == "l2_logistic_regression" and
              model_definitions[name].get("decision_threshold") == 0.5,
              "Unexpected base model specification")
    oof_report = json_file(sources["oof_report"])
    check(oof_report.get("status") == "OOF_TRAIN_ONLY_THRESHOLD_DEVELOPMENT_NOT_CLINICAL_VALIDATION" and
          oof_report.get("fold10_used") is False and
          oof_report.get("fold9_was_previously_inspected") is True and
          oof_report.get("medai_clinical_gate") == "NOT_EVALUATED" and
          oof_report.get("clinical_validity") == "NOT_ESTABLISHED" and
          oof_report.get("thresholds_not_clinically_qualified") is True and
          oof_report.get("specificity_development_target") == MIN_SPEC and
          oof_report.get("train_count") == len(train) and
          oof_report.get("validation_count") == len(val), "OOF report not research-only")
    expected_oof_hashes = {
        "original_pilot_report_sha256": "pilot_model_report",
        "original_validation_predictions_sha256": "validation_predictions",
        "training_manifest_sha256": "train_manifest",
        "training_oof_predictions_sha256": "training_oof_predictions",
    }
    for report_key, source_key in expected_oof_hashes.items():
        check(oof_report.get(report_key) == file_sha(sources[source_key]),
              f"OOF report SHA mismatch: {report_key}")
    check(set(oof_report.get("models", {})) == set(REQUIRED_MODELS), "OOF model mismatch")

    val_columns = ("ecg_id", "patient_id", "strat_fold", "age", "y_true", "baseline_probability",
                   "baseline_pred", "candidate_probability", "candidate_pred")
    oof_columns = ("ecg_id", "strat_fold", "y_true", "baseline_probability", "candidate_probability")
    val_csv = read_csv(sources["validation_predictions"], val_columns)
    oof_csv = read_csv(sources["training_oof_predictions"], oof_columns)
    check(len(val_csv) == len(val) and len(oof_csv) == len(train),
          "CSV row counts inconsistent")
    val_scores = {k: [] for k in REQUIRED_MODELS}
    oof_scores = {k: [] for k in REQUIRED_MODELS}
    for line, row in zip(val_csv, val):
        check(line["ecg_id"] == ecg_id(row["ecg_id"]) and
              patient_id(line["patient_id"]) == patient_id(row["patient_id"]) and
              line["strat_fold"] == "9" and
              line["y_true"] == str(row["y_true"]) and
              line["age"] == str(row.get("age", "")),
              "Validation manifest/prediction identity mismatch")
        for model in REQUIRED_MODELS:
            p = score(line[model + "_probability"])
            val_scores[model].append(p)
            check(line[model + "_pred"] == str(int(p >= 0.5)),
                  f"Original fixed 0.5 prediction mismatch: {model}")
    for line, row in zip(oof_csv, train):
        check(line["ecg_id"] == ecg_id(row["ecg_id"]) and
              line["strat_fold"] == str(row["strat_fold"]) and
              line["y_true"] == str(row["y_true"]),
              "Training OOF manifest/CSV identity mismatch")
        for model in REQUIRED_MODELS:
            oof_scores[model].append(score(line[model + "_probability"]))

    train_labels = [r["y_true"] for r in train]
    val_labels = [r["y_true"] for r in val]
    check(pilot_report.get("validation_metrics") is not None, "Missing pilot validation metrics")
    thresholds: dict[str, float] = {}
    model_diagnostics: dict[str, dict] = {}
    for name in REQUIRED_MODELS:
        fixed = metrics(val_labels, val_scores[name], 0.5)
        verify_metric_report({"n": len(val), "tp": fixed["tp"], "tn": fixed["tn"],
                              "fp": fixed["fp"], "fn": fixed["fn"],
                              "sensitivity": fixed["sensitivity"],
                              "specificity": fixed["specificity"]},
                             pilot_report["validation_metrics"].get(name), name + " original")
        selected = oof_threshold(train_labels, oof_scores[name])
        audit = oof_report["models"][name]
        check(isinstance(audit, dict), f"Malformed OOF report: {name}")
        check(close_metric(audit.get("threshold_from_training_oof_only"), selected["threshold"]),
              f"OOF threshold changed: {name}")
        verify_metric_report(selected, audit.get("train_oof_selection_metrics_development_only"),
                             f"{name} train OOF")
        check(len(audit.get("oof_fold_audit", [])) == 8 and
              {a.get("heldout_fold") for a in audit["oof_fold_audit"]} == set(range(1, 9)),
              f"OOF fold audit incomplete: {name}")
        thresholds[name] = selected["threshold"]
        developmental = metrics(val_labels, val_scores[name], selected["threshold"])
        verify_metric_report(developmental,
                             audit.get("fold9_previously_inspected_development_diagnostic"),
                             f"{name} fold9")
        model_diagnostics[name] = {"oof_training_selection": selected,
                                   "fold9_development_only": developmental,
                                   "original_fixed_050": fixed,
                                   "method": "L2 regularized logistic regression on 72 ECG features"}

    official = official_hashes(sources["official_sums"])
    n_verified = verify_waveform_hashes(root, train + val, official)
    check(n_verified == pilot_report["raw_waveform_files_sha256_checked"],
          "Waveform verification count mismatch")
    cohorts = [group_assessment(val, val_scores, thresholds, protocol, group)
               for group in protocol["required_subgroups"]]
    evidence_insufficient = any(cohort["sample_adequacy_for_demonstration_rules"] ==
                                "INSUFFICIENT_EVIDENCE" for cohort in cohorts)
    # Fold 9 is development data irrespective of cohort counts. Never return clinical PASS.
    result = {
        "schema_version": SCHEMA,
        "status": "RESEARCH_EVIDENCE_ONLY",
        "dataset": {"name": "PTB-XL", "version": "1.0.3",
                    "sample_selection": "NON_RANDOM_INTERRUPTED_DOWNLOAD_CONVENIENCE_SAMPLE",
                    "development_folds": "1-8 OOF + previously inspected fold 9",
                    "test_fold_10": "NOT_ACCESSED_BY_THIS_ADAPTER"},
        "trusted_protocol": {"id": protocol["protocol_id"],
                             "version": protocol["protocol_version"],
                             "sha256_raw_file": file_sha(protocol_path),
                             "sha256_canonical_json": doc_sha(protocol),
                             "claim_id": protocol["clinical_claim_id"],
                             "risk_control_id": protocol["risk_control_id"],
                             "required_subgroups": protocol["required_subgroups"],
                             "demonstration_only": True},
        "source_integrity": {"hash_algorithm": "SHA-256",
                             "files": {key: {"relative_path": str(path.relative_to(root)).replace("\\", "/"),
                                             "sha256": file_sha(path)}
                                       for key, path in sources.items()},
                             "waveform_files_checked": n_verified,
                             "waveform_records_checked": len(train) + len(val),
                             "origin_authentication": "NOT_ESTABLISHED_BY_HASHES"},
        "sample": {"training_records": len(train), "validation_records": len(val),
                   "training_mi_positive": sum(train_labels),
                   "validation_mi_positive": sum(val_labels),
                   "train_validation_patient_overlap": 0},
        "models": model_diagnostics,
        "subgroups": cohorts,
        "evidence_adequacy": "INSUFFICIENT_EVIDENCE" if evidence_insufficient else
                             "NOT_ASSESSED_FOR_INDEPENDENT_VALIDATION",
        "clinical_gate": "NOT_EVALUATED",
        "real_ptbxl_independent_clinical_validation": False,
        "release_decision": "OUTSIDE_PLATFORM_SCOPE",
        "reasons": [
            "Fold 9 was used for development and repeatedly inspected; not independent validation.",
            "Fold 10 was not accessed for evaluation.",
            "Model thresholds developed on training OOF, not clinically qualified.",
            "Pilot data is a non-random interrupted-download convenience sample.",
            "Patient-cluster confidence intervals and statistical multiplicity not evaluated.",
            "Sample sufficiency is checked against a demonstration-only protocol; not clinical qualification.",
        ] + [f"{c['cohort_id']}: {reason}" for c in cohorts for reason in c["sample_shortfalls"]],
        "human_review": {"status": "REQUIRED_FOR_INTERPRETATION", "can_override_technical_result": False},
    }
    result["artifact_sha256"] = doc_sha(result)
    return result


def verify(package: dict, root: Path, protocol_path: Path) -> None:
    check(isinstance(package, dict) and package.get("schema_version") == SCHEMA,
          "Unsupported research package")
    provided = package.get("artifact_sha256")
    check(isinstance(provided, str) and HASH_RE.fullmatch(provided) is not None,
          "Missing research artifact SHA256")
    check(doc_sha({k: v for k, v in package.items() if k != "artifact_sha256"}) == provided,
          "Research artifact hash does not match")
    rebuilt = build(root, protocol_path)
    check(package == rebuilt,
          "Research evidence no longer matches locked protocol, source files or recomputed metrics")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "verify"))
    parser.add_argument("--data-dir", type=Path, default=Path.home() / "Documents/MedAI-Data/ptb-xl-1.0.3")
    parser.add_argument("--protocol", type=Path, required=True,
                        help="Independently supplied locked PTB-XL demo protocol JSON")
    parser.add_argument("--package", type=Path, help="Explicit research evidence package path for verify")
    args = parser.parse_args()
    root = args.data_dir.resolve()
    if args.mode == "build":
        output = root / "benchmark_v1" / "pilot_v1" / "real_evidence_v04" / "research_evidence.json"
        evidence = build(root, args.protocol.resolve())
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(evidence, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        verify(json_file(output), root, args.protocol.resolve())
        print("RESEARCH EVIDENCE PACKAGE: CREATED AND REVERIFIED")
        print("SOURCE SHA256 CHECKS: PASS")
        print("TRAIN/VALIDATION PATIENT OVERLAP: 0")
        for cohort in evidence["subgroups"]:
            counts = cohort["counts"]
            print(f"{cohort['cohort_id']}: positive_patients={counts['n_positive_patients']} "
                  f"negative_patients={counts['n_negative_patients']} "
                  f"sample_adequacy={cohort['sample_adequacy_for_demonstration_rules']}")
        print("CLINICAL GATE: NOT_EVALUATED")
        print("FOLD 10: NOT ACCESSED BY ADAPTER")
        print("OUTPUT:", output)
    else:
        check(args.package is not None, "verify requires --package")
        package = json_file(args.package.resolve())
        verify(package, root, args.protocol.resolve())
        print("RESEARCH PACKAGE VERIFICATION: OK")
        print("SOURCE FILES + LOCKED PROTOCOL + DERIVED METRICS: CONSISTENT")
        print("CLINICAL GATE: NOT_EVALUATED")
        print("RELEASE DECISION: OUTSIDE_PLATFORM_SCOPE")


if __name__ == "__main__":
    try:
        main()
    except (EvidenceError, FileNotFoundError, KeyError, TypeError, ValueError,
            OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"RESEARCH EVIDENCE VERIFICATION FAILED: {exc}") from exc
