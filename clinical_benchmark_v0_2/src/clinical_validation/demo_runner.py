"""Standalone research demo. Example: python -m src.clinical_validation.demo_runner --scenario fail"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .protocol_loader import load_protocol
from .evidence_package_writer import build_evidence_package, write_evidence_files


def synthetic_fixture(scenario: str) -> tuple[list[dict], list[str]]:
    """Fake PTB-XL-shaped rows; intentionally NO real ECG or learned predictions."""
    if scenario not in {"pass", "fail", "insufficient", "not_measured"}:
        raise ValueError("Unsupported demo scenario")
    records: list[dict] = []
    age_positive = 10 if scenario == "insufficient" else 70
    for y, total in ((1, 140), (0, 140)):
        for i in range(total):
            age = 78 if i < (age_positive if y else 70) else 48
            ecg_id = f"SYNTH-{y}-{i:03d}"
            model2 = y
            if scenario == "fail" and y == 1 and i < 14:
                model2 = 0
            records.append({
                "ecg_id": ecg_id, "patient_id": f"PATIENT-{y}-{i:03d}",
                "strat_fold": 10, "age": age,
                "subgroups": ["ALL"] + (["AGE75_PLUS"] if age >= 75 else []),
                "y_true": y, "y_pred_v1": y, "y_pred_v2": model2,
            })
    if scenario == "not_measured":
        records[0]["y_pred_v2"] = None
    return records, ["TRAIN-SYNTH-1", "TRAIN-SYNTH-2"]


def run() -> None:
    parser = argparse.ArgumentParser(description="MedAI Assurance local research-only benchmark")
    parser.add_argument("--protocol", default="protocols/ptbxl_mi_demo_protocol.json")
    parser.add_argument("--scenario", choices=["pass", "fail", "insufficient", "not_measured"], default="pass")
    parser.add_argument("--records-json", type=Path, help="Optional user-provided held-out prediction rows (JSON array)")
    parser.add_argument("--train-manifest-json", type=Path, help="Optional JSON array with training patient IDs")
    parser.add_argument("--output", default="reports/demo")
    args = parser.parse_args()
    protocol = load_protocol(args.protocol)
    if args.records_json:
        records = json.loads(args.records_json.read_text(encoding="utf-8"))
        train_ids = json.loads(args.train_manifest_json.read_text(encoding="utf-8")) if args.train_manifest_json else None
        source_type = "USER_SUPPLIED_UNVERIFIED"
    else:
        records, train_ids = synthetic_fixture(args.scenario)
        source_type = "SYNTHETIC_ENGINE_TEST"
    result = build_evidence_package(protocol, records, training_patient_ids=train_ids,
                                    model_v1_id="DEMO-V1-UNVERIFIED", model_v2_id="DEMO-V2-UNVERIFIED",
                                    source_type=source_type)
    json_path, html_path = write_evidence_files(result, args.output)
    print(f"{result['overall_gate_status']} / {source_type} | {json_path} | {html_path}")


if __name__ == "__main__":
    run()
