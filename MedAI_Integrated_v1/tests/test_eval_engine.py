import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eval_engine import ValidationError, validate_annotations, extract_predictions, evaluate, markdown_report


def row(req,doc,rel='IRRELEVANT',status='EXPERT_VALIDATED'):
    return {'requirement_id':req,'document_id':doc,'relevance':rel,
            'evidence_polarity':'INSUFFICIENT_CONTEXT','sufficiency':'NOT_ASSESSABLE',
            'annotation_status':status,'annotator':'qualified-reviewer' if status!='UNLABELED' else None,
            'rationale':'Reviewed the complete synthetic document.' if status!='UNLABELED' else None}

class TestEvaluation(unittest.TestCase):
    def test_empty_labels_produce_no_scores(self):
        r=row('A','a','UNLABELED','UNLABELED')
        r['evidence_polarity']='UNLABELED';r['sufficiency']='UNLABELED'
        result=evaluate([r],{'A':['a']})
        self.assertEqual(result['benchmark_status'],'NOT_MEASURED')
        self.assertIsNone(result['metrics']['k=1']['recall_micro'])
    def test_provisional_excluded(self):
        x=row('A','a','DIRECTLY_RELEVANT','PROVISIONAL')
        self.assertEqual(evaluate([x],{'A':['a']})['benchmark_status'],'NOT_MEASURED')
    def test_correct_recall_precision_fnr(self):
        gold=[row('A','a','DIRECTLY_RELEVANT'),row('A','b'),row('A','c','TOPICALLY_RELATED')]
        r=evaluate(gold,{'A':['b','a']},ks=(1,2))
        self.assertEqual(r['metrics']['k=1']['recall_micro'],0)
        self.assertEqual(r['metrics']['k=1']['precision_micro'],0)
        self.assertEqual(r['metrics']['k=2']['recall_micro'],0.5)
        self.assertEqual(r['metrics']['k=2']['precision_micro'],0.5)
        self.assertEqual(r['metrics']['k=2']['false_negative_rate'],0.5)
    def test_partial_gold_does_not_shift_rank(self):
        gold=[row('A','a','DIRECTLY_RELEVANT'),row('A','b','UNLABELED','UNLABELED')]
        gold[1]['evidence_polarity']='UNLABELED';gold[1]['sufficiency']='UNLABELED'
        result=evaluate(gold,{'A':['b','a']})
        self.assertEqual(result['benchmark_status'],'NOT_MEASURED')
    def test_duplicate_rejected(self):
        x=row('A','a')
        with self.assertRaises(ValidationError):validate_annotations([x,x])
    def test_missing_rationale_rejected(self):
        x=row('A','a');x['rationale']=''
        with self.assertRaises(ValidationError):validate_annotations([x])
    def test_invalid_category_rejected(self):
        x=row('A','a');x['relevance']=2
        with self.assertRaises(ValidationError):validate_annotations([x])
    def test_ai_draft_cannot_be_expert_validated(self):
        x=row('A','a');x['annotator']='AI_ASSISTED_DRAFT'
        with self.assertRaises(ValidationError):validate_annotations([x])
    def test_prediction_order_by_score(self):
        x={'requirements':[{'requirement_id':'A','candidates':[{'document_id':'b','retrieval_score':0.2},{'document_id':'a','retrieval_score':0.8}]}]}
        self.assertEqual(extract_predictions(x)['A'],['a','b'])
    def test_markdown_not_measured(self):
        x=row('A','a','UNLABELED','UNLABELED');x['evidence_polarity']='UNLABELED';x['sufficiency']='UNLABELED'
        self.assertIn('NOT MEASURED',markdown_report(evaluate([x],{'A':[]})))

if __name__=='__main__':unittest.main()
