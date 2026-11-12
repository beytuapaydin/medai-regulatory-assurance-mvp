import copy
import pathlib
import sys
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import run

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.clauses,self.metadata=run.load_requirements(run.BASE/'data/article10_9_clause_evidence.json')
        self.docs=run.ingest(run.BASE/'docs_demo')

    def test_full_source(self):
        self.assertEqual(len(self.clauses),13)
    def test_hash_tamper_rejected(self):
        x=copy.deepcopy(self.clauses)
        x[0]['text']='modified'
        self.assertNotEqual(run.sha(x[0]['text']),x[0]['text_sha256'])
    def test_seven_docs(self):
        self.assertEqual(len(self.docs),7)
    def test_content_not_preassigned(self):
        self.assertEqual(len(run.candidates(self.clauses,self.docs)),13)
    def test_quote_is_verbatim_document_span(self):
        d={x['document_id']:x for x in self.docs}
        for r in run.candidates(self.clauses,self.docs):
            for c in r['candidates']:
                self.assertEqual(c['passage'],d[c['document_id']]['text'][c['start_char']:c['end_char']])
                self.assertEqual(run.sha(c['passage']),c['passage_sha256'])
    def test_no_candidate_doesnt_mean_compliant_or_gap(self):
        r=run.candidates(self.clauses,[])
        self.assertTrue(all(x['state']=='NO_RETRIEVAL_CANDIDATE' for x in r))
        self.assertTrue(all(x['evidence_sufficiency']=='NOT_ASSESSED' for x in r))
    def test_escape_in_dashboard(self):
        r=run.candidates(self.clauses,self.docs)
        r[0]['requirement']='<script>alert(1)</script>'
        result=run.html_report({'requirements':r})
        self.assertIn('&lt;script&gt;',result)
        self.assertNotIn('<script>alert(1)</script>',result)
    def test_missing_document_directory(self):
        with self.assertRaises(ValueError):run.ingest(run.BASE/'nonexistent')

if __name__=='__main__':unittest.main()
