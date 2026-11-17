"""Adversarial bootstrap-policy regression tests (synthetic evidence only)."""
import json
from pathlib import Path
import pytest
from medai_unified_v0_3 import core
from medai_unified_v0_3.make_fixture import make_fixture

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "clinical_benchmark_v0_2/protocols/ptbxl_mi_demo_protocol.json"


def build(tmp_path, scenario="pass"):
    core._legacy_modules()
    from src.clinical_validation.demo_runner import synthetic_fixture
    from src.clinical_validation.protocol_loader import load_protocol
    from src.clinical_validation.evidence_package_writer import build_evidence_package
    make_fixture(tmp_path)
    rows, train = synthetic_fixture(scenario)
    evidence = build_evidence_package(
        load_protocol(PROTOCOL), rows, training_patient_ids=train,
        model_v1_id="BASE", model_v2_id="CAND",
    )
    cpath = tmp_path / "clinical.json"
    cpath.write_text(json.dumps(evidence), encoding="utf-8", newline="\n")
    apath = tmp_path / "regulatory_assessment_SYNTHETIC.json"
    return core.build_unified(apath, cpath), apath, cpath


def rehash_and_rebuild(u, apath, cpath):
    """Rehash the clinical JSON and rebuild input-file bindings as an attacker could."""
    c = u["clinical_evidence"]
    c["artifact_sha256"] = core._sha_json({k: v for k, v in c.items() if k != "artifact_sha256"})
    cpath.write_text(json.dumps(c), encoding="utf-8", newline="\n")
    return core.build_unified(apath, cpath)


@pytest.mark.parametrize("field,value", [
    ("confidence_level", 0.50),
    ("replicates_requested", 200),
    ("seed", 99999),
    ("one_sided_non_inferiority_alpha", 0.25),
    ("replicates_valid", 2),
    ("method", "UNVERIFIED_BOOTSTRAP"),
])
def test_rehashed_bootstrap_changes_rejected_even_with_matching_source_files(tmp_path, field, value):
    u, apath, cpath = build(tmp_path)
    ci = u["clinical_evidence"]["cohort_evaluations"][0]["paired_sensitivity_delta_ci"]
    ci[field] = value
    forged = rehash_and_rebuild(u, apath, cpath)
    with pytest.raises(ValueError, match="bootstrap"):
        core.verify_unified(
            forged, assessment_path=apath, clinical_path=cpath,
            protocol_path=PROTOCOL, require_protocol_lock=True,
        )


@pytest.mark.parametrize("scenario,expected", [("pass", "PASS"), ("fail", "FAIL")])
def test_valid_synthetic_gate_and_protocol_lock_unaffected(tmp_path, scenario, expected):
    u, apath, cpath = build(tmp_path, scenario)
    assert u["clinical_evidence"]["overall_gate_status"] == expected
    assert core.verify_unified(
        u, assessment_path=apath, clinical_path=cpath,
        protocol_path=PROTOCOL, require_protocol_lock=True,
    ) == "PROTOCOL_AND_INPUT_FILES_LOCKED"
