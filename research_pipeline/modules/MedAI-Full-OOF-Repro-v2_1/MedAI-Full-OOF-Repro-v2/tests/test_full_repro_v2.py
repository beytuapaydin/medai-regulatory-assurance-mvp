import importlib.util
from pathlib import Path
import types
import pytest

P = Path(__file__).resolve().parents[1] / 'verify_full_oof_v2.py'
spec = importlib.util.spec_from_file_location('repro', P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def data():
    rows = [{'ecg_id':str(i),'patient_id':str(i),'fold':i,'y_true':i%2} for i in range(1,9)]
    features = [[i/10] for i in range(1,9)]
    expected = {str(i):(i,i%2,i/10,i/10) for i in range(1,9)}
    model = types.SimpleNamespace(MODEL_CONFIGS=(('baseline',1.0),('candidate',.1)),
                                  train_logistic=lambda features,labels,l2: 'model',
                                  predict=lambda model,features: features[0])
    return rows,features,expected,model


def test_exact_replay(monkeypatch):
    monkeypatch.setattr(m,'EXPECTED_ROWS',8)
    r,x,e,model=data()
    worst,compared,audits=m.score_replay(r,x,e,model,logger=lambda _:None)
    assert worst == {'baseline':0.,'candidate':0.}
    assert compared == {'baseline':8,'candidate':8}
    assert len(audits)==16


def test_tampered_probability_fails(monkeypatch):
    monkeypatch.setattr(m,'EXPECTED_ROWS',8)
    r,x,e,model=data()
    e['1']=(1,1,.9,.1)
    with pytest.raises(ValueError,match='Prediction mismatch'):
        m.score_replay(r,x,e,model,logger=lambda _:None)


def test_patient_overlap_fails(monkeypatch):
    monkeypatch.setattr(m,'EXPECTED_ROWS',8)
    r,x,e,model=data()
    r[1]['patient_id']=r[0]['patient_id']
    with pytest.raises(ValueError,match='patient-disjoint'):
        m.score_replay(r,x,e,model,logger=lambda _:None)


def test_wrong_predictions_count_fails(monkeypatch):
    monkeypatch.setattr(m,'EXPECTED_ROWS',9)
    r,x,e,model=data()
    with pytest.raises(ValueError,match='Replay incomplete'):
        m.score_replay(r,x,e,model,logger=lambda _:None)


def test_canonical_id():
    assert m.canonical_id('15709.0') == '15709'
    assert m.canonical_id('001') == '1'
    with pytest.raises(ValueError):m.canonical_id('1.5')
    with pytest.raises(ValueError):m.canonical_id('-1')


def test_input_sha_protects_training_file(tmp_path):
    (tmp_path/'ptbxl_pilot_train.py').write_text('print("tampered")')
    with pytest.raises(ValueError,match='SHA-256 mismatch'):
        m.load_training(tmp_path)


def test_existing_report_protected(tmp_path):
    report=tmp_path/'existing.json'
    report.write_text('immutable')
    with pytest.raises(ValueError,match='overwrite'):
        m.execute(tmp_path,tmp_path,tmp_path,report)
    assert report.read_text()=='immutable'


def test_bad_tolerance_rejected(tmp_path):
    with pytest.raises(ValueError,match='tolerance'):
        m.execute(tmp_path,tmp_path,tmp_path,tmp_path/'report.json',tolerance=1.0)


def test_locked_evidence_hashes_are_complete():
    for digest in (m.EXPECTED_OOF_SHA,m.EXPECTED_REPORT_SHA,m.EXPECTED_MANIFEST_SHA,m.EXPECTED_AUDIT_SHA):
        assert len(digest) == 64
        assert all(c in '0123456789abcdef' for c in digest)
    assert m.EXPECTED_MANIFEST_SHA.upper() == 'CE779FC76ECFC203FEF105761AAF64A619A1A534F185A86BFDEB26DDFDD237CE'
