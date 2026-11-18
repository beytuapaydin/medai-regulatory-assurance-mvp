"""Regression tests for assessment-scoped reviews and spreadsheet-safe exports."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import review_workflow as rw


class ReviewScopeTests(unittest.TestCase):
    def setUp(self):
        self.data = {'requirements': [
            {'requirement_id': f'MDR-10-9-{i}', 'requirement': f'Requirement {i}',
             'requirement_sha256': f'hash-{i}',
             'candidates': [{'document_id': f'doc-{i}', 'filename': 'demo.txt',
                             'passage': 'synthetic evidence', 'passage_sha256': 'demo'}]}
            for i in range(13)
        ]}
        self.source_sha = 'current-assessment'
        self.event = {
            'requirement_id': 'MDR-10-9-0',
            'source_assessment_sha256': self.source_sha,
            'requirement_sha256': 'hash-0',
            'candidate_id': 'doc-0',
            'reviewer': 'QA Reviewer',
            'relevance': 'RELEVANT',
            'evidence_sufficiency_review': 'PARTIAL',
            'rationale': 'Synthetic reviewer note',
            'gap_or_follow_up': '',
            'timestamp_utc': '2026-11-18T00:00:00+00:00',
            'event_sha256': 'synthetic-hash'
        }

    def test_stale_source_is_excluded_from_page_and_csv(self):
        stale = dict(self.event, source_assessment_sha256='outdated-assessment')
        self.assertEqual(rw.current_reviews(self.data,[stale],self.source_sha), {})
        html = rw.page(self.data,[stale],self.source_sha,'test-csrf')
        self.assertIn('0/13 requirements reviewed',html)
        self.assertIn('Pending human review',html)
        self.assertNotIn('Latest review: RELEVANT',html)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(rw,'OUT',Path(directory)):
                csv_path=rw.export(self.data,[stale],self.source_sha)
                with csv_path.open(encoding='utf-8-sig',newline='') as stream:
                    rows=list(csv.DictReader(stream))
        self.assertEqual(rows[0]['review_state'],'PENDING')
        self.assertEqual(rows[0]['reviewer'],'')

    def test_current_event_remains_visible(self):
        reviews=rw.current_reviews(self.data,[self.event],self.source_sha)
        self.assertIn('MDR-10-9-0', reviews)
        html=rw.page(self.data,[self.event],self.source_sha,'test-csrf')
        self.assertIn('1/13 requirements reviewed',html)
        self.assertIn('Latest review: RELEVANT',html)
        self.assertIn('name="source_sha" value="current-assessment"',html)

    def test_newer_stale_event_does_not_replace_current_review(self):
        stale=dict(self.event,source_assessment_sha256='other',reviewer='Old reviewer')
        reviews=rw.current_reviews(self.data,[self.event,stale],self.source_sha)
        self.assertEqual(reviews['MDR-10-9-0']['reviewer'],'QA Reviewer')

    def test_mismatched_requirement_or_candidate_is_not_current(self):
        bad_hash=dict(self.event,requirement_sha256='incorrect')
        bad_candidate=dict(self.event,candidate_id='removed-doc')
        self.assertEqual(rw.current_reviews(self.data,[bad_hash],self.source_sha),{})
        self.assertEqual(rw.current_reviews(self.data,[bad_candidate],self.source_sha),{})

    def test_formula_cells_are_escaped_in_review_csv(self):
        malicious=dict(self.event,reviewer='=1+1',
                       rationale='  +HYPERLINK("https://example.invalid")',
                       gap_or_follow_up='\t@SUM(1,2)')
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(rw,'OUT',Path(directory)):
                csv_path=rw.export(self.data,[malicious],self.source_sha)
                with csv_path.open(encoding='utf-8-sig',newline='') as stream:
                    row=next(csv.DictReader(stream))
        self.assertEqual(row['review_state'],'REVIEWED')
        self.assertEqual(row['reviewer'],"'=1+1")
        self.assertTrue(row['rationale'].startswith("'  +"))
        self.assertTrue(row['gap_or_follow_up'].startswith("'\t@"))
        self.assertEqual(rw.safe_csv_cell('-1+1'),"'-1+1")
        self.assertEqual(rw.safe_csv_cell('@SUM(A1)'),"'@SUM(A1)")
        self.assertEqual(rw.safe_csv_cell('Normal text'),'Normal text')


if __name__=='__main__':
    unittest.main()
