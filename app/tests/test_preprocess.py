"""Real Pandoc regression checks; no model/network calls."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from autoscribe.preprocess import prepare, reader_for


def document(body='Body\n', *, metadata=None, source=None, submission='sub_TEST'):
    return {'schema':'autoscribe.document.v1','document':body,
            'submission_id':submission,'call_source':'test_origin',
            'metadata':{'plan':'pln_TEST',**(metadata or {})},'source':source or {},
            'baggage':{'custom':{'unicode':'café 東京','nested':[1,False,None], 'markdown':'*raw* [x](y)'}}}


class PreprocessTests(unittest.TestCase):
    def test_identity_matrix_and_original_bytes(self):
        cases=[('---\r\nslug: psg_test\r\n---\r\n# **Café** — 東京!\r\nBody\r\n',{'path':'Notes/original.md'},'slug','psg_test'),
               ('---\nslug: psg_test\n---\nBody',{},'slug','psg_test'),
               ('Body',{'path':'Notes/original.md'},'filename','Notes/original.md'),
               ('# **Café** — 東京!\nBody',{},'heading','Café — 東京!'),
               ('## Second level\nBody',{},'heading','Second level'),
               ('Plain *body* — 東京',{},'content','Plain body — 東京'),
               ('',{},'fallback','Untitled document')]
        for raw,source,kind,hint in cases:
            with self.subTest(kind=kind,source=source):
                incoming=document(raw,source=source);original=copy.deepcopy(incoming)
                out=prepare(incoming)
                self.assertEqual(out['content'].encode(),raw.encode())
                self.assertEqual(incoming,original)
                self.assertEqual(out['baggage']['custom'],incoming['baggage']['custom'])
                identity=out['baggage']['autoscribe_ingest']['source']
                self.assertEqual(identity['hint_kind'],kind)
                self.assertEqual(identity['hint'],hint)
                self.assertEqual('path' in out['source'],'path' in source)
                self.assertEqual(out['status'],'failed' if not raw else 'ready',out)
                if kind=='slug' and source:
                    self.assertEqual(identity['original_filename'],source['path'])
                    self.assertEqual(identity['path'],source['path'])
                if kind!='slug':self.assertNotIn('slug',out['source'])

    def test_native_reader_boundary_and_no_staging_provenance(self):
        self.assertEqual(reader_for('html'),'html')
        self.assertEqual(reader_for('docx'),'docx')
        value=document('# Heading',source={'original_filename':'Original.md'})
        out=prepare(value,work_dir=Path('/tmp/staging-document'))
        identity=out['baggage']['autoscribe_ingest']['source']
        self.assertEqual(identity['original_filename'],'Original.md')
        self.assertNotIn('path',out['source'])
        self.assertNotIn('staging',json.dumps(out))
        value['source_format']='html'
        self.assertEqual(prepare(value)['failure']['code'],'unsupported_representation')
        value['source_format']='invented'
        self.assertEqual(prepare(value)['status'],'failed')

    def test_plans_conflicts_and_malformed_slugs(self):
        missing=document();missing['metadata']={}
        self.assertEqual(prepare(missing)['failure']['code'],'missing_plan')
        for plan in ('bad plan','pln_',[],False):
            with self.subTest(plan=plan):
                self.assertEqual(prepare(document(metadata={'plan':plan}))['status'],'failed')
        conflict=document('---\nplan: pln_OTHER\n---\nBody')
        self.assertEqual(prepare(conflict)['failure']['code'],'metadata_conflict')
        for slug in ('""','[]','bad slug','éclair','a'*161):
            self.assertEqual(prepare(document('---\nslug: '+slug+'\n---\nBody'))['failure']['code'],'invalid_slug')
        value=document('---\nslug: psg_a\n---\nBody',source={'slug':'psg_b'})
        self.assertEqual(prepare(value)['failure']['code'],'metadata_conflict')

    def test_unicode_bound_and_ast_heading(self):
        out=prepare(document('```md\n# Not a heading\n```\n\n### '+('東京🙂'*100)))
        identity=out['baggage']['autoscribe_ingest']['source']
        self.assertLessEqual(len(identity['hint']),160)
        self.assertTrue(identity['heading'].startswith('東京🙂'))
        self.assertEqual(out,prepare(document('```md\n# Not a heading\n```\n\n### '+('東京🙂'*100))))

    def test_document_cannot_replace_transport_coordination(self):
        value=document('---\nplan: pln_TEST\nautoscribe_transport: malicious\nsource: invented/path.md\ncall_source: invented\n---\nBody',source={'path':'Original.md'})
        out=prepare(value)
        self.assertEqual(out['status'],'ready',out)
        self.assertEqual(out['source']['path'],'Original.md')
        self.assertEqual(out['call_source'],'test_origin')
        value['metadata']['custom_sidecar']='Supplementary value'
        self.assertEqual(prepare(value)['metadata']['custom_sidecar'],'Supplementary value')

    def test_retry_and_distinct_submission_identity(self):
        value=document('Identical body')
        first=prepare(value);again=prepare(value)
        self.assertEqual(first['call_id'],again['call_id'])
        value['document']='Changed body'
        self.assertEqual(first['call_id'],prepare(value)['call_id'])
        value['document']='Identical body';value['submission_id']='sub_DISTINCT'
        self.assertNotEqual(first['call_id'],prepare(value)['call_id'])
        self.assertEqual(first['call_source'],'test_origin')
        self.assertEqual(first['plan'],'pln_TEST')

    def test_one_invocation_and_defaults_order(self):
        real_run=subprocess.run
        captured=[]
        def capture(*args,**kwargs):
            completed=real_run(*args,**kwargs);captured.append(completed);return completed
        with patch('autoscribe.preprocess.subprocess.run',side_effect=capture) as run:
            out=prepare(document())
        self.assertEqual(out['status'],'ready',out)
        self.assertEqual(run.call_count,1)
        args=run.call_args.args[0]
        self.assertIn('--defaults',args)
        self.assertNotIn('--lua-filter',args)
        parsed=json.loads(captured[0].stdout)
        self.assertEqual(parsed['trace'],['metadata','hint','call','prepare'])

    def test_structured_failures_retain_source_and_content(self):
        value=document('Original bytes\r\n',source={'path':'Notes/original.md'})
        with patch('autoscribe.preprocess.subprocess.run',side_effect=OSError('Pandoc unavailable')):
            out=prepare(value)
        self.assertEqual(out['failure']['code'],'pandoc_execution')
        self.assertEqual(out['content'],value['document'])
        self.assertEqual(out['source'],value['source'])
        self.assertEqual(out['baggage'],value['baggage'])
        self.assertEqual(out['submission_id'],value['submission_id'])
        self.assertTrue(out['call_id'].startswith('failed_'))
        value['source']['path']='../escape'
        self.assertEqual(prepare(value)['failure']['code'],'invalid_envelope')
        malformed=document('---\nnot: [valid\n---\nBody')
        self.assertEqual(prepare(malformed)['failure']['code'],'pandoc_execution')
        with patch('autoscribe.preprocess.subprocess.run',return_value=subprocess.CompletedProcess([],0,b'{}',b'')):
            self.assertEqual(prepare(document())['failure']['code'],'serialization')


if __name__=='__main__':unittest.main()
