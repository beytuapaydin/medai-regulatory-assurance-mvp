"""Generate fake MDR-shaped inputs. DO NOT call these genuine regulatory evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import hashlib


def sha(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()


def make_fixture(target: str | Path):
    root = Path(target)
    root.mkdir(parents=True, exist_ok=True)
    requirements = []
    for i in range(1, 14):
        requirement_text = f"SYNTHETIC NOT LEGALLY VERIFIED — QA evidence requirement placeholder {i}."
        candidates = []
        if i == 1:
            passage = "SYNTHETIC QA candidate evidence. No implementation or MDR conformance claim."
            candidates.append({
                "document_id": "SYNTHETIC-DOC-01", "filename": "synthetic_demo_document.txt",
                "passage": passage, "passage_sha256": sha(passage),
                "retrieval_score": 0.50,
            })
        requirements.append({"requirement_id": f"DEMO-REQ-{i:02d}",
                             "requirement": requirement_text,
                             "requirement_sha256": sha(requirement_text),
                             "source_review": "SYNTHETIC_UNVERIFIED", "candidates": candidates})
    path = root / "regulatory_assessment_SYNTHETIC.json"
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps({"requirements": requirements, "source_pdf_sha256": None,
                                "synthetic_fixture": True}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"SYNTHETIC regulatory assessment: {path}")


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output", default="unified_demo_inputs")
    args=parser.parse_args()
    make_fixture(args.output)
