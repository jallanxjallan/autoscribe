"""One offline contract: identities, durable batches, pending index and application CAS."""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from asc import manual_client as manual, ssh_jobs as jobs, control
from asc.models.call import ClientResponse


class ManualContract(unittest.TestCase):
    def test_finite_manual_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); incoming=root/'incoming'; incoming.mkdir(); ledger=root/'ledger.sqlite'
            original=b'---\r\nslug: nte_0123456789ABCDEF\r\ntype: note\r\nplan: pln_TEST\r\n---\r\nOriginal'
            resolved=original.replace(b'Original',b'Expanded')
            sha=lambda value:hashlib.sha256(value).hexdigest()
            identity,revision=manual.revision_identity('a'*64,'pln_TEST',sha(original),sha(resolved))
            metadata=dict(schema=manual.SCHEMA,batch_id='bat_'+'b'*32,revision=revision,source='a'*64,
                source_path='Note.md',vault_id='c'*64,plan='pln_TEST',original_sha256=sha(original),
                processing_sha256=sha(resolved),slug='nte_0123456789ABCDEF',note_type='note')
            manual.validate_manifest(identity,metadata,original,resolved)
            record_id='inp_'+sha(identity.encode())[:32]
            call_id='call_'+hashlib.sha1(identity.encode()).hexdigest()
            digest='d'*64
            ready={'status':'ready','plan':'pln_TEST','source':{'slug':metadata['slug']}}
            with patch.object(jobs,'ROOT',incoming):
                jobs.initialize(ledger)
                (incoming/identity).mkdir()
                manual.retain_manifest(identity,metadata,original,resolved,{})
                partial=manual.query(ledger,[identity])['submissions'][identity]
                self.assertEqual(partial['state'],'new');self.assertEqual(partial['batch_id'],metadata['batch_id'])
                def prepare(dispatch, checksum, location, folder, control):
                    manual.retain_manifest(dispatch,metadata,original,resolved,{})
                    return json.dumps(ready)
                with patch.object(jobs,'prepare_dropbox',side_effect=prepare), \
                     patch.object(jobs,'bind_release'), \
                     patch.object(control,'plan_index',return_value=[{'plan_id':'pln_TEST'}]), \
                     patch.object(jobs,'enqueue_record',return_value=SimpleNamespace(record_id=record_id,call_id=call_id,failure=None)) as enqueue, \
                     patch.object(jobs,'launch',side_effect=lambda ledger,dispatch,digest:jobs.read_job(ledger,dispatch,digest)), \
                     patch.object(jobs,'resume',side_effect=lambda ledger,client,dispatch,digest,state:state):
                    first=jobs.command(['submit',identity,digest,'fixture'],None,ledger,object())
                    second=jobs.command(['submit',identity,digest,'fixture'],None,ledger,object())
                    self.assertEqual(enqueue.call_count,1)
                    self.assertEqual(first,second)
                # A fresh read from durable server storage recovers identity/batch;
                # no client cache or runtime Redis is consulted.
                state=manual.query(ledger,[identity])['submissions'][identity]
                self.assertEqual(state['state'],'accepted');self.assertEqual(state['batch_id'],metadata['batch_id'])
                before=ledger.read_bytes()
                self.assertEqual(manual.index(ledger)['inflight'][0]['state'],'accepted')
                self.assertEqual(ledger.read_bytes(),before)
                self.assertEqual(manual.command(['index','--inflight'],None,ledger,object())['inflight'][0]['result_id'],identity)
                jobs.update(ledger,identity,'running',started_at=1)
                self.assertEqual(manual.index(ledger)['inflight'][0]['state'],'running')
                body='Completed text' 
                response=dict(schema='autoscribe.client-response.v1',submission_id=identity,call_id=call_id,record_id=record_id,
                    source_sha256=sha(original),source={'path':'Note.md','vault_id':metadata['vault_id'],'slug':metadata['slug']},
                    metadata={},routing={'plan_id':'pln_TEST'},baggage={},status='completed',result=body,
                    result_bytes=len(body.encode()),result_sha256=sha(body.encode()),
                    terminal_step={'id':'stp_TEST','position':1,'component':'fixture'},
                    receipt_id=ClientResponse.receipt_identity(identity,call_id,record_id,'completed',sha(body.encode()),sha(original)),
                    failure=None,error=None,uncertain=False)
                typed=ClientResponse.model_validate(response)
                response_sha=jobs.response_file(incoming/identity,typed.model_dump(mode='json',by_alias=True))
                jobs.update(ledger,identity,'completed',response_sha256=response_sha,completed_at=1)
                # A second result in the same batch proves partial application
                # keeps an accurate remaining count without another execution.
                original2=original.replace(b'0123456789ABCDEF',b'1123456789ABCDEF')
                resolved2=resolved.replace(b'0123456789ABCDEF',b'1123456789ABCDEF')
                identity2,revision2=manual.revision_identity('9'*64,'pln_TEST',sha(original2),sha(resolved2))
                metadata2=dict(metadata,source='9'*64,source_path='Second.md',revision=revision2,
                    original_sha256=sha(original2),processing_sha256=sha(resolved2),slug='nte_1123456789ABCDEF')
                (incoming/identity2).mkdir()
                manual.validate_manifest(identity2,metadata2,original2,resolved2)
                manual.retain_manifest(identity2,metadata2,original2,resolved2,{})
                response2=dict(response,submission_id=identity2,call_id='call_'+hashlib.sha1(identity2.encode()).hexdigest(),
                    record_id='inp_'+sha(identity2.encode())[:32],source_sha256=sha(original2),
                    source=dict(response['source'],path='Second.md',slug=metadata2['slug']))
                response2['receipt_id']=ClientResponse.receipt_identity(identity2,response2['call_id'],response2['record_id'],'completed',response2['result_sha256'],response2['source_sha256'])
                typed2=ClientResponse.model_validate(response2)
                checksum2=jobs.response_file(incoming/identity2,typed2.model_dump(mode='json',by_alias=True))
                with sqlite3.connect(ledger) as db:
                    db.execute('INSERT INTO ssh_jobs(dispatch_id,record_id,call_id,package_sha256,state,accepted_at,response_sha256,completed_at) VALUES(?,?,?,?,?,?,?,?)',
                        (identity2,response2['record_id'],response2['call_id'],digest,'completed',1,checksum2,2))
                before=ledger.read_bytes()
                index=manual.index(ledger)
                self.assertEqual(ledger.read_bytes(),before)
                self.assertEqual(index['batches'][0]['count'],2)
                self.assertEqual(index['inflight'],[])
                fetched=manual.fetch(ledger,identity)
                self.assertEqual(fetched['response'],typed.model_dump(mode='json',by_alias=True))
                self.assertEqual(fetched['original_markdown'],original.decode())
                self.assertEqual(fetched['processing_markdown'],resolved.decode())
                # Claim remains visible until ack, and competing application modes
                # cannot both acquire ownership.
                request=dict(mode='writeback',intent='e'*64,target='f'*64,response_sha256=response_sha,receipt=None)
                manual.application(ledger,'claim',identity,request)
                self.assertEqual(manual.index(ledger)['batches'][0]['count'],2)
                with self.assertRaises(ValueError):manual.application(ledger,'claim',identity,dict(request,mode='writenew'))
                fetch2=manual.fetch(ledger,identity2)
                request['receipt']=dict(file_sha256='1'*64,git_commit='2'*40)
                def retention_failure(call_id): raise OSError('simulated retention acknowledgment interruption')
                with self.assertRaises(OSError): manual.application(ledger,'ack',identity,request,retention_failure)
                self.assertEqual(manual.index(ledger)['batches'][0]['count'],2)
                ack=manual.application(ledger,'ack',identity,request)
                self.assertEqual(manual.application(ledger,'ack',identity,request),ack)
                self.assertEqual(manual.index(ledger)['batches'][0]['count'],1)
                self.assertEqual(manual.index(ledger)['results'][0]['result_id'],identity2)
                self.assertEqual(manual.query(ledger,[identity])['submissions'][identity]['state'],'applied')
                with sqlite3.connect(ledger) as db:self.assertEqual(db.execute('SELECT state FROM ssh_jobs WHERE dispatch_id=?',(identity,)).fetchone()[0],'applied')
                # Preserve a language-neutral fixture before temporary paths vanish.
                fixture=dict(identity=identity,revision=revision,metadata=metadata,
                    response=typed.model_dump(mode='json',by_alias=True),original=original.decode(),resolved=resolved.decode(),index=index,fetches={identity:fetched,identity2:fetch2})
                Path(os.environ['AUTOSCRIBE_MANUAL_WIRE']).write_text(json.dumps(fixture)+'\n')

if __name__=='__main__':unittest.main()
