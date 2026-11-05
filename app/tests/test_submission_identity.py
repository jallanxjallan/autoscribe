"""Submission-only identity regression tests; no external execution."""
import copy
import hashlib
import unittest
import uuid
from unittest.mock import patch

from autoscribe.ids import new_submission_id, validate_submission_id
from autoscribe.preprocess import prepare
from autoscribe.enqueue import validate_input_record, EnqueueError
from test_preprocess import document


class SubmissionIdentityTests(unittest.TestCase):
    def test_new_operations_generate_opaque_random_uuid4(self):
        identifiers=[new_submission_id() for _ in range(128)]
        self.assertEqual(len(set(identifiers)),128)
        for value in identifiers:
            parsed=uuid.UUID(value)
            self.assertEqual(parsed.version,4)
            self.assertEqual(parsed.variant,uuid.RFC_4122)
            self.assertEqual(validate_submission_id(value),value)

    def test_only_top_level_canonical_uuid4_is_accepted(self):
        for invalid in (None,'counter-1','00000000-0000-0000-0000-000000000000',
                        str(uuid.uuid1()),'AFFFFFFF-FFFF-4FFF-8FFF-FFFFFFFFFFFF',str(uuid.uuid4()).replace('-','')):
            with self.subTest(invalid=invalid):
                value=document();value['submission_id']=invalid
                out=prepare(value)
                self.assertEqual(out['schema'],'autoscribe.ingest-error.v1')
                self.assertNotIn('call_id',out)
                self.assertNotIn('record_id',out)
        value=document();identifier=value.pop('submission_id')
        value['baggage']['client']={'submission_id':identifier}
        self.assertNotIn('call_id',prepare(value))

    def test_provenance_does_not_participate_in_call_or_failure_identity(self):
        value=document();identifier=value['submission_id']
        value['baggage']['client']={'source':'first-client','description':'*opaque* 東京'}
        first=prepare(value)
        value['baggage']['client']['source']='other-client'
        second=prepare(value)
        self.assertEqual(first['call_id'],'call_'+hashlib.sha1(identifier.encode()).hexdigest())
        self.assertEqual(first['call_id'],second['call_id'])
        self.assertEqual(first['record_id'],second['record_id'])
        self.assertEqual(second['baggage']['client'],value['baggage']['client'])
        self.assertNotIn('call_source',second)
        self.assertNotIn('call_source',second['baggage']['autoscribe_ingest'])
        with patch('autoscribe.preprocess.subprocess.run',side_effect=OSError('unavailable')):
            failed=prepare(value)
            value['baggage']['client']['source']='another-client'
            repeated=prepare(value)
        self.assertEqual(failed['call_id'],'failed_'+hashlib.sha256(identifier.encode()).hexdigest())
        self.assertEqual(failed['call_id'],repeated['call_id'])

    def test_enqueue_rejects_call_identity_not_derived_from_submission(self):
        value=prepare(document())
        value['call_id']='call_'+'0'*40
        with self.assertRaisesRegex(EnqueueError,'call_id does not identify submission'):
            validate_input_record(value)

    def test_prepared_contract_rejects_retired_origin_field(self):
        value=prepare(document())
        validate_input_record(value)
        value['call_source']='obsolete'
        with self.assertRaisesRegex(EnqueueError,'call_source'):
            validate_input_record(value)


if __name__=='__main__':unittest.main()
