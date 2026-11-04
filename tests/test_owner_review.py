import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agentforge import owner_review, task_inbox


class TestOwnerReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'company'
        self.patch = patch.object(task_inbox, 'DATA_DIR', self.root)
        self.patch.start()
        self.task_id = 'a' * 32 + '-source-review'
        self.quote = 'A paid Excel service is advertised for local shops.'
        self.task = {'task_id':self.task_id,'status':'PROPOSED','opportunity_id':'research-aaaaaaaa','kind':'SOURCE_REVIEW','source_urls':['https://example.org/article'],'execution_authorized':False,'spending_authorized':False}
        self.candidate = {'candidate_id':'C1','source_url':'https://example.org/article','field':'paid_alternative','statement':'A business advertises a paid service','quote':self.quote,'quote_status':'MATCHED_IN_PAGE','independently_verified':False,'owner_reviewed':False,'supports':[]}
        self.handoff = {'task_id':self.task_id,'opportunity_id':'research-aaaaaaaa','status':'PENDING_OWNER_REVIEW','owner_reviewed':False,'execution_authorized':False,'spending_authorized':False,'source_review_file':f'reviews/{self.task_id}.json','candidates':[self.candidate]}
        self.report = {'task_id':self.task_id,'opportunity_id':'research-aaaaaaaa','review_status':'QUOTE_REVIEW_ONLY','execution_authorized':False,'spending_authorized':False,'source_reviews':[{'url':'https://example.org/article','status':'QUOTES_CHECKED_NOT_FACT_CHECKED','observations':[{'field':'paid_alternative','statement':self.candidate['statement'],'quote':self.quote,'quote_status':'MATCHED_IN_PAGE','independently_verified':False}]}]}
        task_inbox.task_path(self.task_id).parent.mkdir(parents=True,exist_ok=True)
        task_inbox.task_path(self.task_id).write_text(json.dumps(self.task),encoding='utf-8')
        self.hp=self.root / 'evidence_candidates' / f'{self.task_id}.json'; self.hp.parent.mkdir(parents=True,exist_ok=True)
        self.rp=self.root / 'reviews' / f'{self.task_id}.json'; self.rp.parent.mkdir(parents=True,exist_ok=True)
        self.save()
    def tearDown(self): self.patch.stop(); self.tmp.cleanup()
    def save(self):
        self.hp.write_text(json.dumps(self.handoff),encoding='utf-8')
        self.rp.write_text(json.dumps(self.report),encoding='utf-8')
    def approve(self,**kw): return owner_review.decide(self.task_id,'C1','approve','Personally checked the original page.',scope='differentiation',confirm=True,**kw)
    def test_approve_does_not_register(self):
        path=self.approve(); doc=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(doc['decision'],'APPROVED_FOR_REGISTRATION')
        self.assertEqual(doc['scope'],'differentiation')
        self.assertFalse(doc['registered'])
        self.assertFalse(doc['execution_authorized'])
        self.assertFalse(doc['spending_authorized'])
        self.assertFalse((self.root.parent/'opportunities'/'evidence_index.json').exists())
    def test_reject_has_no_scope(self):
        path=owner_review.decide(self.task_id,'C1','reject','Marketing claim is weak.')
        self.assertEqual(json.loads(path.read_text())['decision'],'REJECTED')
        self.assertIsNone(json.loads(path.read_text())['scope'])
    def test_no_approval_without_acknowledgment(self):
        with self.assertRaises(PermissionError): owner_review.decide(self.task_id,'C1','approve','Manual check performed.',scope='differentiation')
    def test_weak_quotes_cannot_prove_payment(self):
        with self.assertRaises(ValueError): owner_review.decide(self.task_id,'C1','approve','Manual check performed.',scope='willingness_to_pay',confirm=True)
        with self.assertRaises(ValueError): owner_review.decide(self.task_id,'C1','approve','Manual check performed.',scope='hard_blocker',confirm=True)
    def test_duplicate_decision_preserves_original(self):
        p=self.approve(); raw=p.read_bytes()
        with self.assertRaises(FileExistsError): self.approve()
        self.assertEqual(raw,p.read_bytes())
    def test_tampered_candidate_quote_rejected(self):
        self.candidate['quote']='This quote was invented, does not match the source.'; self.save()
        with self.assertRaises(ValueError): self.approve()
    def test_invalid_candidate_id_rejected(self):
        with self.assertRaises(ValueError): owner_review.decide(self.task_id,'../C1','reject','Untrustworthy source text')
    def test_deferred_task_rejected(self):
        self.task['status']='DEFERRED';task_inbox.task_path(self.task_id).write_text(json.dumps(self.task))
        with self.assertRaises(ValueError): self.approve()
    def test_invalid_handoff_approval_flag_rejected(self):
        self.handoff['execution_authorized']=True; self.save()
        with self.assertRaises(ValueError): self.approve()

if __name__=='__main__': unittest.main()
