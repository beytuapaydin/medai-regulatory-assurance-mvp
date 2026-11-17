from pathlib import Path
from types import SimpleNamespace
import hashlib,json,sys,pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gonogo_v1 as g

def test_hash_fixed():
    assert g.EXPECTED['freeze_manifest.json']=='53FFD3AE20CC6347B2969DF5C334F17052A650F8CAD71779DC11445C86CEDD61'

def test_threshold():assert g.THRESHOLD==0.3795860831201651

def test_digest(tmp_path):
    p=tmp_path/'x';p.write_bytes(b'test');assert g.digest(p)==hashlib.sha256(b'test').hexdigest().upper()

def test_missing(tmp_path):
    with pytest.raises(g.AuditError):g.verify_one(tmp_path/'missing','x')

def test_tamper(tmp_path):
    p=tmp_path/'a';p.write_text('hello');expected=g.digest(p);p.write_text('HELLO')
    with pytest.raises(g.AuditError):g.verify_one(p,expected)

def test_verified(tmp_path):
    p=tmp_path/'a';p.write_text('hello');rec=g.verify_one(p,g.digest(p));assert rec['bytes']==5

def test_output_exclusive(tmp_path):
    p=tmp_path/'a';g.write_json_new(p,{'a':1})
    with pytest.raises(FileExistsError):g.write_json_new(p,{'a':2})

def test_no_real_holdout_interface():
    src=Path(g.__file__).read_text()
    assert 'records500' not in src and 'filename_lr' not in src

def test_pending_no_go(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(g,'review',lambda a:[{'name':'dummy','sha256':'X','bytes':2}])
    a=SimpleNamespace(output_dir=tmp_path/'new',docs=tmp_path,freeze_dir=tmp_path/'freeze',model_dir=tmp_path/'model',plan_dir=tmp_path/'plan')
    g.execute(a)
    obj=json.loads((a.output_dir/'go_nogo_decision.json').read_text())
    assert obj['decision']=='NO_GO' and obj['holdout_authorized'] is False
    assert all(x['status'] in ('PENDING','NOT_AUTHORIZED') for x in obj['review_items'])
    assert (a.output_dir/'go_nogo_manifest.json').exists()

def test_existing_output_fails(tmp_path,monkeypatch):
    monkeypatch.setattr(g,'review',lambda a:[])
    a=SimpleNamespace(output_dir=tmp_path,docs=tmp_path,freeze_dir=tmp_path/'freeze',model_dir=tmp_path/'model',plan_dir=tmp_path/'plan')
    with pytest.raises(g.AuditError):g.execute(a)

def test_protected_location_fails(tmp_path,monkeypatch):
    monkeypatch.setattr(g,'review',lambda a:[])
    a=SimpleNamespace(output_dir=tmp_path/'freeze'/'sub',docs=tmp_path,freeze_dir=tmp_path/'freeze',model_dir=tmp_path/'model',plan_dir=tmp_path/'plan')
    with pytest.raises(g.AuditError):g.execute(a)
