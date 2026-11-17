import importlib.util
import json
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'tools'/'verify_release_evidence.py'
spec=importlib.util.spec_from_file_location('rcverifier',path)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def registry_item(name,content,folder):
    f=folder/name
    f.parent.mkdir(parents=True,exist_ok=True)
    f.write_bytes(content)
    return {'id':name,'relative_path':name,'sha256':m.sha256(f)}

def test_registry_has_fifteen_and_no_go():
    r=json.loads(m.REGISTRY.read_text(encoding='utf-8'))
    assert len(r['evidence'])==15
    assert r['holdout_authorized'] is False

def test_documentation_package_has_no_holdout_code():
    root=Path(__file__).resolve().parents[1]
    assert not list(root.rglob('*.dat'))
    assert not list(root.rglob('*.hea'))
    assert not list(root.rglob('candidate_model.json'))

def test_sha256_is_stable(tmp_path):
    f=tmp_path/'a'
    f.write_bytes(b'abc')
    assert m.sha256(f)=='BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD'

def test_bad_path_rejected():
    for val in ('../secret', '/tmp/foo', '', 'C:/secret', 'C:secret', '//server/share', r'folder\secret', 'a/../b', './foo', 'folder//file', 'folder/file.', 'folder/file ', 'folder/', 'a:b'):
        with pytest.raises(m.AuditFailure):m.validate_relative_path(val)

def test_valid_path():
    assert m.validate_relative_path('folder/file.txt').as_posix()=='folder/file.txt'

def test_missing_record_fails(tmp_path):
    r={'status':'RESEARCH_RELEASE_CANDIDATE_NO_GO','holdout_authorized':False,'evidence':[{'id':str(i),'relative_path':'missing','sha256':'A'*64} for i in range(15)]}
    with pytest.raises(m.AuditFailure):m.verify_entries(tmp_path,r)

def test_duplicate_record_fails(tmp_path):
    a=registry_item('file',b'ok',tmp_path)
    r={'status':'RESEARCH_RELEASE_CANDIDATE_NO_GO','holdout_authorized':False,'evidence':[a]*15}
    with pytest.raises(m.AuditFailure):m.verify_entries(tmp_path,r)

def test_tamper_fails(tmp_path):
    entries=[]
    for i in range(15):entries.append(registry_item('e'+str(i),str(i).encode(),tmp_path))
    (tmp_path/'e8').write_bytes(b'tampered')
    r={'status':'RESEARCH_RELEASE_CANDIDATE_NO_GO','holdout_authorized':False,'evidence':entries}
    with pytest.raises(m.AuditFailure,match='mismatch'):m.verify_entries(tmp_path,r)

def test_valid_synthetic_evidence(tmp_path):
    entries=[registry_item('e'+str(i),str(i).encode(),tmp_path) for i in range(15)]
    r={'status':'RESEARCH_RELEASE_CANDIDATE_NO_GO','holdout_authorized':False,'evidence':entries}
    assert len(m.verify_entries(tmp_path,r))==15

def test_status_change_fails(tmp_path):
    r={'status':'HOLDOUT_AUTHORIZED','holdout_authorized':True,'evidence':[]}
    with pytest.raises(m.AuditFailure):m.verify_entries(tmp_path,r)


def test_valid_nested_path_cross_platform(tmp_path):
    rel = m.validate_relative_path('a/b/c.txt')
    assert rel.as_posix() == 'a/b/c.txt'
    assert str(tmp_path / rel).endswith(str(Path('a') / 'b' / 'c.txt'))
