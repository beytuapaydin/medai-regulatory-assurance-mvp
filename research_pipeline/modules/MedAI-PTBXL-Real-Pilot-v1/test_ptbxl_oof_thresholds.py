import json
from pathlib import Path
import pytest
from ptbxl_oof_thresholds import performance, select_train_only_threshold, oof_predict


def test_performance_counts():
    result = performance([1, 1, 0, 0], [0.8, 0.1, 0.7, 0.2], 0.5)
    assert (result['tp'], result['fn'], result['fp'], result['tn']) == (1, 1, 1, 1)
    assert result['sensitivity'] == 0.5
    assert result['specificity'] == 0.5


def test_threshold_from_oof_only_at_spec_target():
    labels = [1, 1, 0, 0, 0, 0]
    scores = [0.9, 0.4, 0.8, 0.3, 0.2, 0.1]
    result = select_train_only_threshold(labels, scores, 0.75)
    assert result['threshold'] == 0.4
    assert result['tp'] == 2
    assert result['fp'] == 1


def test_ties_deterministic():
    result = select_train_only_threshold([1, 0], [0.1, 0.1], 1.0)
    assert result['tp'] == 0
    assert result['fp'] == 0
    assert result['specificity'] == 1


def test_requires_both_classes():
    with pytest.raises(ValueError):
        select_train_only_threshold([0, 0], [0.3, 0.4])


def test_rejects_invalid_scores():
    with pytest.raises(ValueError):
        select_train_only_threshold([0, 1], [0.2, float('nan')])


def test_requires_all_eight_folds():
    with pytest.raises(ValueError):
        oof_predict([[1], [2]], [0, 1], [1, 2], 1.0)


def test_true_out_of_fold_predictions():
    X, y, folds = [], [], []
    for fold in range(1, 9):
        for j in range(4):
            X.append([float(fold), float(j)])
            y.append(j % 2)
            folds.append(fold)
    probs, audit = oof_predict(X, y, folds, 0.1)
    assert len(probs) == len(y)
    assert len(audit) == 8
    assert all(0 <= p <= 1 for p in probs)
    assert [r['heldout_fold'] for r in audit] == list(range(1, 9))
    assert all(r['training_records'] == 28 and r['heldout_records'] == 4 for r in audit)


def test_full_oof_pipeline_uses_train_only_and_keeps_fold10_sealed(tmp_path, monkeypatch):
    import sys
    import ptbxl_pilot_train as orig
    import ptbxl_oof_thresholds as oof
    from test_ptbxl_pilot_train import fake_wave
    pilot = tmp_path / 'benchmark_v1' / 'pilot_v1'
    pilot.mkdir(parents=True)
    train, validation, hashes = [], [], {}
    for n in range(1, 28):
        positive = n % 3 == 0
        rel = fake_wave(tmp_path, n, positive)
        for ext in ('.hea', '.dat'):
            hashes[rel + ext] = orig.digest(tmp_path / (rel + ext))
        fold = (n - 1) // 3 + 1 if n <= 24 else 9
        row = dict(ecg_id=str(n), patient_id=f'p{n}', strat_fold=fold,
                   age='80', y_true=int(positive), filename_lr=rel)
        (train if n <= 24 else validation).append(row)
    (tmp_path / 'SHA256SUMS.txt').write_text(
        ''.join(f'{h}  {rel}\n' for rel, h in hashes.items()), encoding='utf-8')
    (pilot / 'pilot_train.json').write_text(json.dumps(train))
    (pilot / 'pilot_validation.json').write_text(json.dumps(validation))
    (pilot / 'pilot_manifest.json').write_text(json.dumps({
        'status': 'EXPLORATORY_PILOT', 'patient_overlap': 0,
        'train': {'ecg': 24}, 'validation': {'ecg': 3}
    }))
    monkeypatch.setattr(sys, 'argv', ['ptbxl_pilot_train.py', '--data-dir', str(tmp_path)])
    orig.main()
    monkeypatch.setattr(sys, 'argv', ['ptbxl_oof_thresholds.py', '--data-dir', str(tmp_path)])
    oof.main()
    report = json.loads((pilot / 'oof_thresholds_v1/oof_threshold_development_report.json').read_text())
    assert report['fold10_used'] is False
    assert report['fold9_was_previously_inspected'] is True
    assert report['train_count'] == 24
    assert report['medai_clinical_gate'] == 'NOT_EVALUATED'
    for model in ('baseline', 'candidate'):
        assert len(report['models'][model]['oof_fold_audit']) == 8
        assert report['models'][model]['train_oof_selection_metrics_development_only']['specificity'] >= .9
    assert not (tmp_path / 'records100/00000/00028_lr.dat').exists()
