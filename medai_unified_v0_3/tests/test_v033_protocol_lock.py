"""Adversarial regression tests for P0-1 protocol-locked verification & P1 cross-checks."""
import json
from pathlib import Path
import pytest
from medai_unified_v0_3 import core
from medai_unified_v0_3.make_fixture import make_fixture

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "clinical_benchmark_v0_2" / "protocols" / "ptbxl_mi_demo_protocol.json"


def _build(tmp_path, scenario="fail"):
    core._legacy_modules()
    from src.clinical_validation.demo_runner import synthetic_fixture
    from src.clinical_validation.protocol_loader import load_protocol
    from src.clinical_validation.evidence_package_writer import build_evidence_package

    make_fixture(tmp_path)
    rows, train = synthetic_fixture(scenario)
    protocol = load_protocol(PROTOCOL_PATH)
    ev = build_evidence_package(
        protocol, rows, training_patient_ids=train,
        model_v1_id="BASE", model_v2_id="CAND",
    )
    cpath = tmp_path / f"clinical_{scenario}.json"
    cpath.write_text(json.dumps(ev), encoding="utf-8", newline="\n")
    apath = tmp_path / "regulatory_assessment_SYNTHETIC.json"
    return core.build_unified(apath, cpath), apath, cpath


def _rehash(u):
    c = u["clinical_evidence"]
    c["artifact_sha256"] = core._sha_json({k: v for k, v in c.items() if k != "artifact_sha256"})
    u["package_sha256"] = core._sha_json({k: v for k, v in u.items() if k != "package_sha256"})
    return u


def test_protocol_locked_verification_succeeds_on_authentic_package(tmp_path):
    u, apath, cpath = _build(tmp_path, "pass")
    scope = core.verify_unified(
        u, assessment_path=apath, clinical_path=cpath,
        protocol_path=PROTOCOL_PATH, require_protocol_lock=True,
    )
    assert scope == "PROTOCOL_AND_INPUT_FILES_LOCKED"


def test_fail_closed_when_protocol_lock_required_but_protocol_missing(tmp_path):
    u, apath, cpath = _build(tmp_path, "pass")
    with pytest.raises(ValueError, match="requires a trusted --protocol"):
        core.verify_unified(u, assessment_path=apath, clinical_path=cpath, require_protocol_lock=True)
    with pytest.raises(ValueError, match="Trusted protocol file missing"):
        core.verify_unified(
            u, assessment_path=apath, clinical_path=cpath,
            protocol_path=tmp_path / "nonexistent_protocol.json", require_protocol_lock=True,
        )


def test_protocol_lock_blocks_relaxed_acceptance_rules_false_pass(tmp_path):
    u, apath, cpath = _build(tmp_path, "fail")
    c = u["clinical_evidence"]
    c["acceptance_rules"]["max_sensitivity_drop"] = 0.50
    c["acceptance_rules"]["max_critical_fn_rate"] = 0.50
    c["acceptance_rules"]["non_inferiority_margin_sensitivity_delta"] = -0.50
    c["technical_gate"]["status"] = "PASS"
    c["technical_gate"]["reasons"] = ["Forged pass"]
    c["statistical_findings"]["confirmed_demo_threshold_failures"] = []
    c["overall_gate_status"] = "PASS"
    _rehash(u)
    cpath.write_text(json.dumps(c), encoding="utf-8", newline="\n")
    forged = core.build_unified(apath, cpath)
    with pytest.raises(ValueError, match="acceptance_rules|locked protocol"):
        core.verify_unified(forged, assessment_path=apath, clinical_path=cpath, protocol_path=PROTOCOL_PATH)


def test_protocol_lock_blocks_altered_required_subgroups(tmp_path):
    u, apath, cpath = _build(tmp_path, "fail")
    c = u["clinical_evidence"]
    c["acceptance_rules"]["required_subgroups"] = ["ALL"]
    c["cohort_evaluations"] = [x for x in c["cohort_evaluations"] if x["cohort_id"] == "ALL"]
    c["acceptance_rules"]["max_sensitivity_drop"] = 0.25
    c["acceptance_rules"]["non_inferiority_margin_sensitivity_delta"] = -0.25
    c["technical_gate"]["status"] = "PASS"
    c["technical_gate"]["reasons"] = []
    c["statistical_findings"]["confirmed_demo_threshold_failures"] = []
    c["overall_gate_status"] = "PASS"
    _rehash(u)
    with pytest.raises(ValueError, match="acceptance_rules|required_subgroups|locked protocol"):
        core.verify_unified(u, protocol_path=PROTOCOL_PATH)


def test_internal_protocol_hash_mismatch_rejected_without_external_file(tmp_path):
    u, _, _ = _build(tmp_path, "pass")
    u["clinical_evidence"]["protocol"]["sha256"] = "0" * 64
    _rehash(u)
    with pytest.raises(ValueError, match="protocol SHA-256 mismatch"):
        core.verify_unified(u)


def test_tampered_protocol_hash_rejected_against_locked_protocol(tmp_path):
    u, _, _ = _build(tmp_path, "pass")
    fake_sha = "a" * 64
    u["clinical_evidence"]["protocol"]["sha256"] = fake_sha
    u["clinical_evidence"]["integrity"]["protocol_sha256"] = fake_sha
    _rehash(u)
    with pytest.raises(ValueError, match="does not match locked protocol"):
        core.verify_unified(u, protocol_path=PROTOCOL_PATH)


def test_cohort_summary_patient_count_desync_rejected(tmp_path):
    u, _, _ = _build(tmp_path, "pass")
    u["clinical_evidence"]["cohort_evaluations"][0]["n_distinct_positive_patients"] = 999
    _rehash(u)
    with pytest.raises(ValueError, match="Inconsistent cohort summary vs basic_metrics patient counts"):
        core.verify_unified(u)


def test_bootstrap_cluster_count_desync_rejected(tmp_path):
    u, _, _ = _build(tmp_path, "pass")
    u["clinical_evidence"]["cohort_evaluations"][0]["paired_sensitivity_delta_ci"]["unique_positive_patient_clusters"] = 999
    _rehash(u)
    with pytest.raises(ValueError, match="Inconsistent bootstrap cluster count"):
        core.verify_unified(u)


def test_regenerated_synthetic_demo_artifact_verifies_cleanly(tmp_path):
    # Generated demonstration outputs are not tracked in the clean Git checkout.
    # Build fresh synthetic evidence rather than depending on developer-local files.
    pkg, _, _ = _build(tmp_path, "fail")
    scope = core.verify_unified(
        pkg, protocol_path=PROTOCOL_PATH, require_protocol_lock=True
    )
    assert scope == "PROTOCOL_LOCKED"

