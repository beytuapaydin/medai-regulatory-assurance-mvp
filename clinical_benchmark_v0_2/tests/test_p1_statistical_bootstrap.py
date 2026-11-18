"""Exploratory bootstrap statistical bug regression tests; fabricated data only."""
from src.clinical_validation.paired_statistics import patient_cluster_paired_sensitivity_ci


def test_negative_patients_cannot_inflate_sensitivity_cluster_count():
    rows = [
        {'patient_id': f'POS-{i}', 'y_true': 1, 'y_pred_v1': 1, 'y_pred_v2': 1}
        for i in range(40)
    ]
    rows += [
        {'patient_id': f'NEG-{i}', 'y_true': 0, 'y_pred_v1': 0, 'y_pred_v2': 0}
        for i in range(300)
    ]
    stat = patient_cluster_paired_sensitivity_ci(rows, confidence_level=0.95,
                                                  replicates=300, seed=1701)
    assert stat['unique_patient_clusters'] == 40
    assert stat['unique_positive_patient_clusters'] == 40
    assert stat['replicates_valid'] == 300
    assert stat['point_delta_v2_minus_v1'] == 0
    assert stat['ci_lower'] == 0 and stat['ci_upper'] == 0


def test_repeat_ecgs_keep_one_patient_cluster():
    rows = [
        {'patient_id': 'POS-ONE', 'y_true': 1, 'y_pred_v1': 1, 'y_pred_v2': 0}
        for i in range(100)
    ]
    rows += [
        {'patient_id': f'NEG-{i}', 'y_true': 0, 'y_pred_v1': 0, 'y_pred_v2': 0}
        for i in range(200)
    ]
    stat = patient_cluster_paired_sensitivity_ci(rows, confidence_level=0.95,
                                                  replicates=300, seed=8)
    assert stat is None
