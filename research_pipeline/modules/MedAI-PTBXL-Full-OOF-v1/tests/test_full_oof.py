import importlib.util
from pathlib import Path
import random
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import full_oof_train_v1 as m

class ToyTrain:
    MODEL_CONFIGS = (('baseline', 1.0), ('candidate', .1))
    def train_logistic(self, X, y, l2):
        return {'bias': sum(y)/len(y), 'l2': l2}
    def predict(self, model, x):
        return min(1.0, max(0.0, .2 + x[0]/20 + model['bias']/4 + model['l2']/50))

def sample(n_per_fold=4):
    rows = []
    features = []
    for fold in range(1, 9):
        for j in range(n_per_fold):
            i = len(rows)
            rows.append({'ecg_id': str(i + 1), 'fold': fold,
                         'patient_id': f'P{fold}_{j}', 'y_true': j % 2})
            features.append([i / 10])
    return rows, features


def test_full_oof_has_exact_8_audits_and_paired_complete_scores():
    rows, X = sample()
    results, audit = m.produce_oof(rows, X, ToyTrain(), progress=lambda *_: None)
    assert len(audit) == 16
    assert all(len(v) == 32 and all(0 <= x <= 1 for x in v) for v in results.values())
    assert all(x['patient_overlap'] == 0 for x in audit.values())


def test_patient_fold_leak_rejected_before_training():
    rows, X = sample()
    rows[4]['patient_id'] = rows[0]['patient_id']
    with pytest.raises(ValueError, match='Patient leakage'):
        m.produce_oof(rows, X, ToyTrain(), progress=lambda *_: None)


def test_fold9_and_fold10_rejected():
    for fold in (9, 10):
        rows, X = sample()
        rows[0]['fold'] = fold
        with pytest.raises(ValueError, match='exclusively fold 1-8'):
            m.produce_oof(rows, X, ToyTrain(), progress=lambda *_: None)


def test_incomplete_folds_rejected():
    rows, X = sample()
    keep = [i for i, r in enumerate(rows) if r['fold'] != 8]
    with pytest.raises(ValueError, match='eight folds'):
        m.produce_oof([rows[i] for i in keep], [X[i] for i in keep], ToyTrain(), progress=lambda *_: None)


def test_fast_threshold_agrees_with_v2_slow_for_many_ties():
    v2path = Path(__file__).resolve().parents[2] / 'MedAI-PTBXL-OOF-v2' / 'ptbxl_patient_oof_v2.py'
    if not v2path.is_file():
        pytest.skip('Original OOF v2 sibling source unavailable')
    spec = importlib.util.spec_from_file_location('independent_oof_v2', v2path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rng = random.Random(99)
    for count in [10, 21, 73]:
        rows = []
        scores = []
        for i in range(count):
            label = i % 2
            p = f'P{i%11}'
            val = rng.choice([0., .1, .4, .5, .5, .7, .9, 1.])
            rows.append({'patient_id': p, 'y_true': label, 'baseline': val})
            scores.append(val)
        a = m.fast_threshold(rows, scores)
        b = mod.select_threshold(rows, 'baseline')
        assert a['threshold'] == b['threshold']
        assert abs(a['sensitivity'] - b['sensitivity']) < 1e-10
        assert abs(a['specificity'] - b['specificity']) < 1e-10


def test_fast_threshold_rejects_nonfinite():
    rows, _ = sample()
    with pytest.raises(ValueError, match='label/score'):
        m.fast_threshold(rows, [.1] * (len(rows) - 1) + [float('nan')])


def test_fast_threshold_rejects_missing_class():
    rows, _ = sample()
    for r in rows:
        r['y_true'] = 1
    with pytest.raises(ValueError, match='Missing class'):
        m.fast_threshold(rows, [.5] * len(rows))


def test_hash_locked_sources(tmp_path):
    src = tmp_path / 'src'; src.mkdir()
    oof = tmp_path / 'oof'; oof.mkdir()
    (src / 'ptbxl_pilot_train.py').write_text('print(1)')
    (oof / 'ptbxl_patient_oof_v2.py').write_text('print(1)')
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        m.load_locked_modules(src, oof)


def test_duplicate_output_refused_before_source_access(tmp_path):
    output = tmp_path / 'exists'; output.mkdir()
    with pytest.raises(FileExistsError, match='already exists'):
        m.execute(tmp_path, tmp_path, tmp_path, output)


def test_path_restriction(tmp_path):
    output = tmp_path / 'benchmark_v1' / 'output'
    with pytest.raises(ValueError, match='cannot reside'):
        m.execute(tmp_path, tmp_path, tmp_path, output)
