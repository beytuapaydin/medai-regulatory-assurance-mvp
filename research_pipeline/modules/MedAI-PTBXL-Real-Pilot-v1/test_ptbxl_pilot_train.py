import array
import csv
import json
from pathlib import Path
import re
import sys

import pytest

import ptbxl_pilot_train as p


def fake_wave(root: Path, n: int, positive: bool = True, tamper: bool = False):
    rel = f"records100/00000/{n:05d}_lr"
    name = f"{n:05d}_lr"
    folder = root / "records100" / "00000"
    folder.mkdir(parents=True, exist_ok=True)
    lead_lines = []
    for lead in p.LEADS:
        lead_lines.append(f"{name}.dat 16 1000(10)/mV 16 10 0 0 0 {lead}")
    (folder / f"{name}.hea").write_text(f"{name} 12 100 1000\n" + "\n".join(lead_lines) + "\n", encoding="ascii")
    values = array.array("h")
    for t in range(1000):
        for k in range(12):
            # Positive/negative demo waveform patterns; NOT a medically realistic ECG.
            value = (10 + (250 if positive else 35) * (1 if t % 100 < 10 else 0)
                     + (k % 3) * (4 if positive else 2))
            values.append(value)
    if sys.byteorder != "little":
        values.byteswap()
    data = values.tobytes()
    if tamper:
        data += b"\x00"
    (folder / f"{name}.dat").write_bytes(data)
    return rel


def test_wfdb16_reader_converts_digital_to_mv(tmp_path):
    rel = fake_wave(tmp_path, 1, positive=True)
    features = p.read_features(tmp_path, rel)
    assert len(features) == 72
    assert abs(features[0] - 0.025) < 1e-12  # 10/100 frames * 250 ADC / 1000 = .025 mV
    assert features[1] > 0.0


def test_wfdb16_reader_rejects_corrupt_wave(tmp_path):
    rel = fake_wave(tmp_path, 1, tamper=True)
    with pytest.raises(ValueError, match="Wrong WFDB binary length"):
        p.read_features(tmp_path, rel)


def test_wfdb16_reader_rejects_unsupported_format(tmp_path):
    rel = fake_wave(tmp_path, 1)
    hea = tmp_path / (rel + ".hea")
    hea.write_text(hea.read_text().replace(".dat 16 ", ".dat 212 "), encoding="ascii")
    with pytest.raises(ValueError, match="Unsupported WFDB encoding"):
        p.read_features(tmp_path, rel)


def test_sha256_verifier_detects_tamper(tmp_path):
    rel = fake_wave(tmp_path, 1)
    hashes = {rel + ".hea": p.digest(tmp_path / (rel + ".hea")),
              rel + ".dat": p.digest(tmp_path / (rel + ".dat"))}
    p.verify_record_files(tmp_path, rel, hashes)
    (tmp_path / (rel + ".dat")).write_bytes(b"0" * 24000)
    with pytest.raises(ValueError, match="Checksum mismatch"):
        p.verify_record_files(tmp_path, rel, hashes)


def test_fixed_threshold_metrics_and_auc():
    m = p.calculate_metrics([0, 0, 1, 1], [0.1, 0.7, 0.8, 0.2])
    assert (m["tp"], m["tn"], m["fp"], m["fn"]) == (1, 1, 1, 1)
    assert m["auroc"] == 0.75


def test_l2_training_is_deterministic():
    X = [[0.0, 1], [0.5, 1], [1.0, 1], [2.0, 1], [3.0, 1], [4.0, 1]]
    y = [0, 0, 0, 1, 1, 1]
    a = p.train_logistic(X, y, 0.1)
    b = p.train_logistic(X, y, 0.1)
    assert a == b
    assert p.predict(a, X[0]) < p.predict(a, X[-1])


def test_fold10_rejected_during_loading(tmp_path):
    path = tmp_path / "train.json"
    path.write_text(json.dumps([{"strat_fold": 10, "patient_id": "1", "y_true": 1,
                                 "filename_lr": "records100/00000/00001_lr", "ecg_id": "1"}]))
    with pytest.raises(ValueError, match="Illegal fold"):
        p.load_split(path, set(range(1, 9)))


def test_miniature_end_to_end_cannot_use_fold10(tmp_path, monkeypatch, capsys):
    pilot = tmp_path / "benchmark_v1" / "pilot_v1"
    pilot.mkdir(parents=True)
    train, val, hashes = [], [], {}
    for n in range(1, 15):
        pos = n % 3 == 0
        rel = fake_wave(tmp_path, n, pos)
        for ext in (".hea", ".dat"):
            hashes[rel+ext] = p.digest(tmp_path / (rel+ext))
        row = {"ecg_id": str(n), "patient_id": f"P{n}", "strat_fold": 1 if n <= 10 else 9,
               "age": "80" if n % 2 else "50", "y_true": int(pos), "filename_lr": rel}
        (train if n <= 10 else val).append(row)
    (tmp_path / "SHA256SUMS.txt").write_text("".join(f"{h}  {rel}\n" for rel, h in hashes.items()), encoding="utf-8")
    (pilot / "pilot_train.json").write_text(json.dumps(train))
    (pilot / "pilot_validation.json").write_text(json.dumps(val))
    (pilot / "pilot_manifest.json").write_text(json.dumps({"status": "EXPLORATORY_PILOT", "patient_overlap": 0}))
    monkeypatch.setattr(sys, "argv", ["ptbxl_pilot_train.py", "--data-dir", str(tmp_path)])
    p.main()
    report = json.loads((pilot / "model_v1/pilot_model_report.json").read_text())
    assert report["fold_10_used"] is False
    assert report["medai_gate_status"] == "NOT_EVALUATED"
    assert report["train_records"] == 10
    assert report["validation_records"] == 4
    assert report["raw_waveform_files_sha256_checked"] == 28
    assert (pilot / "model_v1/validation_predictions.csv").is_file()


def test_hidden_unicode_identifier_rejected():
    with pytest.raises(ValueError, match="Malformed"):
        p.canonical_patient_id("P1\u200b")


def test_patient_identifier_case_and_numeric_suffix():
    assert p.canonical_patient_id("pat_1") == p.canonical_patient_id("PAT_1")
    assert p.canonical_patient_id("123.0") == "123"
