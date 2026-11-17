import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('readiness',Path(__file__).parents[1]/'readiness_review.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_sha(tmp_path):
    x=tmp_path/'x';x.write_bytes(b'abc');assert m.sha(x)=='BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD'
def test_verify_fails_on_modified_file(tmp_path):
    x=tmp_path/'x';x.write_bytes(b'abc')
    with pytest.raises(ValueError):m.verify(tmp_path,{'x':'0'*64})
def test_verify_fails_on_missing_file(tmp_path):
    with pytest.raises(ValueError):m.verify(tmp_path,{'notexist':'0'*64})
def test_verify_succeeds(tmp_path):
    x=tmp_path/'x';x.write_bytes(b'abc');v=m.verify(tmp_path,{'x':m.sha(x)});assert v['x']['bytes']==3
def test_threshold_locked():assert m.THRESHOLD==0.3795860831201651
def test_model_hash_length():assert len(m.MODEL['candidate_model.json'])==64
def test_freeze_hash_length():assert all(len(s)==64 for s in m.FREEZE.values())
def test_replay_hash_length():assert len(m.REPLAY)==64
