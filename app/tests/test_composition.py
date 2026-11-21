"""Package C acceptance: registered executables, real MM ranking, synthetic embeddings."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from unittest.mock import patch

from test_runtime import RuntimeCase
from asc.models.call import Call, InvalidRecord, RetrievalResult


class CompositionTests(RuntimeCase):
    def setUp(self):
        super().setUp()
        self.candidate='candidate_'+'1'*32
        self.service=self.root/'train-candidate.py'
        # Execute the authoritative MM source, substituting only paid embeddings
        # and the disposable database. No ranking or filtering substitute.
        source=Path(os.environ['MM_CANDIDATE_SOURCE']).resolve()
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),os.environ['MM_CANDIDATE_SHA256'])
        self.service.write_text('''import argparse,runpy,sqlite3,json,sys
from pathlib import Path
module=runpy.run_path(SOURCE)
module['retrieve'].__globals__['embed']=lambda *a,**k:[[1.,0.]]
p=argparse.ArgumentParser();p.add_argument('op');p.add_argument('candidate');p.add_argument('query');p.add_argument('--top',type=int);p.add_argument('--tag',action='append',default=[])
a=p.parse_args()
with sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True) as db:
 print(json.dumps(module['retrieve'](db,a),ensure_ascii=False,allow_nan=False))
'''.replace('SOURCE',repr(str(source))).replace('DB',f'Path({str(self.root/"candidate.sqlite")!r})'))
        self.config={'service':str(self.service),'service_sha256':hashlib.sha256(self.service.read_bytes()).hexdigest(),
                     'candidate_id':self.candidate,'mode':'semantic','top':5,'tags':[]}
        self.make_candidate(source)
        self.inspect=self.root/'component-inspector.py'
        self.inspect.write_text('''#!/usr/bin/env python3
import sys
from asc.models.call import Invocation,RetrievalResult
inv=Invocation.model_validate_json(sys.stdin.read());call=inv.context.load_call()
retrievals={p:RetrievalResult.model_validate(s.result.data).model_dump(mode='json') for p,s in call.steps.items() if s.result and s.invocation.context.engine_kind=='rag'}
providers={p:{'request':s.request.model_dump(mode='json'),'response':s.result.model_dump(mode='json')} for p,s in call.steps.items() if s.result and s.request}
print(inv.result(text='Transformed: '+(inv.input.text or ''),data={'original':call.source.original_text,'retrievals':retrievals,'providers':providers,'context':inv.context.model_dump(mode='json')}).model_dump_json())
''');self.inspect.chmod(0o755)
        self.registry.write_text(json.dumps({'model-management-rag':str(Path(os.environ['EXTENSIONS_ROOT'])/'scripts/model-management-rag.py'),'unknown-inspector':str(self.inspect)}))

    def make_candidate(self,source):
        import runpy
        mm=runpy.run_path(str(source));canonical=mm['canonical'];sha=mm['sha']
        rows=[];chunks=[]
        for i,(text,tags,vector) in enumerate([('A synthetic harbor passage.',['harbor'],[1.,0.]),('A synthetic mountain passage.',['mountain'],[0.,1.])]):
            chunk={'chunk_id':str(i+1)*64,'slug':'synthetic_'+str(i),'receipt':str(i+3)*64,'uri':'test://source/'+str(i),
                   'tags':tags,'ordinal':0,'start':0,'end':len(text),'content_sha256':sha(text)}
            chunks.append(chunk);rows.append((self.candidate,chunk['chunk_id'],chunk['receipt'],canonical(dict(chunk,passage=text)),canonical(vector)))
        manifest=canonical({'schema':1,'embedding':{'provider':'OpenAI','model':'synthetic','dimensions':2},'chunks':chunks,'vector_sha256':[sha(r[4]) for r in rows]})
        with closing(sqlite3.connect(self.root/'candidate.sqlite')) as db,db:
            db.execute('CREATE TABLE training_input(receipt TEXT PRIMARY KEY)');db.executescript(mm['SCHEMA'])
            db.execute('INSERT INTO retrieval_candidate VALUES (?,?,?,?)',(self.candidate,'ready',manifest,sha(manifest)))
            db.executemany('INSERT INTO retrieval_chunk VALUES (?,?,?,?,?)',rows)
        self.candidate_checksum=hashlib.sha256((self.root/'candidate.sqlite').read_bytes()).hexdigest()

    def plan(self,kinds):
        with closing(sqlite3.connect(self.control)) as db,db:
            db.execute('DELETE FROM step_instructions');db.execute('DELETE FROM plan_steps');db.execute('DELETE FROM steps')
            for position,kind in enumerate(kinds,1):
                component={'rag':'model-management-rag','llm':'luna','script':'unknown-inspector'}[kind]
                db.execute('INSERT INTO steps VALUES (?,?,?,?,?,?,?,?,?,?)',(f'stp_{position}','Step',kind,'chatgpt' if kind=='llm' else 'extension',component if kind=='llm' else None,component if kind=='script' else None,component if kind=='rag' else None,json.dumps(self.config if kind=='rag' else {}),'d'*40,'a'*64))
                db.execute('INSERT INTO plan_steps VALUES (?,?,?)',('pln_TEST',f'stp_{position}',position))
                if kind=='llm':db.execute('INSERT INTO step_instructions VALUES (?,?,?,?)',(f'stp_{position}','rol_1','role',1))

    def run_plan(self,kinds):
        self.plan(kinds);self.accept();self.execute();return Call.load(self.call_id,self.client)

    def test_real_semantic_retrieval_and_llm_script(self):
        call=self.run_plan(['rag','llm','script'])
        self.assertIsNone(call.error,call.error)
        retrieval=RetrievalResult.model_validate(call.result(1).data)
        self.assertEqual([r.slug for r in retrieval.results],['synthetic_0','synthetic_1'])
        self.assertNotEqual(retrieval.results[0].passage,self.raw)
        request=call.steps['2'].request
        self.assertEqual(request.payload,self.api.responses.create.call_args.kwargs)
        self.assertTrue(request.payload['instructions'].startswith('Use deliberately generic prose.\n\nRetrieved context'))
        self.assertIn('A synthetic harbor passage.',request.payload['instructions'])
        self.assertEqual(request.baseline.input.text,call.source.processing_text)
        self.assertEqual(request.retrieval_positions,(1,))
        self.assertEqual(call.final_result.data['original'],self.raw)
        self.assertEqual(call.final_result.data['retrievals']['1'],call.result(1).data)
        self.assertEqual(call.final_result.data['providers']['2']['request']['payload'],request.payload)
        self.assertEqual(call.final_result.data['context']['input_position'],2)
        self.assertEqual(self.api.responses.create.call_count,1)
        self.assertEqual(hashlib.sha256((self.root/'candidate.sqlite').read_bytes()).hexdigest(),self.candidate_checksum)
        with self.assertRaises(InvalidRecord):
            call.evolve(steps={}).save(self.client)

    def test_tagged_mode(self):
        self.config.update(mode='tagged',tags=['mountain'])
        call=self.run_plan(['rag','llm'])
        self.assertIsNone(call.error,call.error)
        self.assertEqual([r['tags'] for r in call.result(1).data['results']],[['mountain']])
        self.assertEqual(call.result(1).data['selection']['candidate_id'],self.candidate)

    def test_repeated_rag_and_llm(self):
        call=self.run_plan(['rag','llm','rag','llm','script'])
        self.assertIsNone(call.error,call.error)
        self.assertEqual(call.steps['4'].request.retrieval_positions,(3,))
        self.assertEqual(call.result(3).data['query'],call.result(2).text)
        self.assertEqual(call.steps['2'].request.payload,self.api.responses.create.call_args_list[0].kwargs)
        self.assertEqual(call.steps['4'].request.payload,self.api.responses.create.call_args_list[1].kwargs)
        self.assertEqual(self.api.responses.create.call_count,2)
        self.assertEqual(call.result(2).provider.response_id,'response-id')
        changed=call.steps['2'].request.model_copy(update={'payload':{'changed':True}})
        with self.assertRaisesRegex(InvalidRecord,'immutable'):
            call.with_step(2,call.steps['2'].model_copy(update={'request':changed})).save(self.client)

    def test_llm_script_llm(self):
        call=self.run_plan(['llm','script','llm'])
        self.assertIsNone(call.error,call.error)
        self.assertEqual(call.steps['3'].request.baseline.input.text,'Transformed: Generic generated prose.')
        self.assertEqual(call.steps['3'].request.retrieval_positions,())
        self.assertEqual(self.api.responses.create.call_count,2)

    def test_empty_retrieval_is_success(self):
        self.config.update(mode='tagged',tags=['absent'])
        call=self.run_plan(['rag','llm'])
        self.assertIsNone(call.error,call.error)
        self.assertEqual(call.result(1).data['results'],[])
        self.assertEqual(self.api.responses.create.call_count,1)

    def test_missing_candidate_fails_without_provider_or_retry(self):
        self.config['candidate_id']='candidate_'+'f'*32
        call=self.run_plan(['rag','llm'])
        self.assertEqual(call.error.code,'retrieval_service')
        self.assertIn('Unknown candidate',call.error.message)
        self.assertEqual(self.api.responses.create.call_count,0)
        self.execute();self.assertEqual(self.api.responses.create.call_count,0)

    def test_invalid_configuration(self):
        self.config['mode']='invalid'
        call=self.run_plan(['rag','llm'])
        self.assertEqual(call.error.code,'retrieval_configuration')
        self.assertEqual(self.api.responses.create.call_count,0)

    def test_unavailable_service(self):
        self.service.unlink()
        call=self.run_plan(['rag','llm'])
        self.assertEqual(call.error.code,'retrieval_unavailable')
        self.assertEqual(self.api.responses.create.call_count,0)

    def test_malformed_response(self):
        self.service.write_text('print("{}")')
        self.config['service_sha256']=hashlib.sha256(self.service.read_bytes()).hexdigest()
        call=self.run_plan(['rag','llm'])
        self.assertEqual(call.error.code,'retrieval_response')
        self.assertEqual(self.api.responses.create.call_count,0)

    def test_changed_service_checksum(self):
        self.service.write_text('raise RuntimeError("must not execute")')
        call=self.run_plan(['rag','llm'])
        self.assertEqual(call.error.code,'retrieval_response')
        self.assertIn('checksum mismatch',call.error.message)
        self.assertEqual(self.api.responses.create.call_count,0)

    def test_tagged_query_and_accepted_selection_are_pinned(self):
        self.config.update(mode='tagged',tags=['mountain'])
        self.plan(['rag','llm']);self.accept()
        with closing(sqlite3.connect(self.control)) as db,db:
            db.execute("UPDATE steps SET args_json='{}' WHERE engine_kind='rag'")
        self.execute();call=Call.load(self.call_id,self.client)
        self.assertIsNone(call.error,call.error)
        self.assertEqual(call.result(1).data['query'],call.source.processing_text)
        self.assertEqual(call.result(1).data['selection']['tags'],['mountain'])

    def test_ordered_baseline_instructions_precede_retrieval(self):
        self.plan(['rag','llm'])
        with closing(sqlite3.connect(self.control)) as db,db:
            for component,body in [('task','Perform the accepted task.'),('context','Use the accepted context.')]:
                identity='ins_'+component
                db.execute('INSERT INTO instructions VALUES (?,?,?,?,?,?)',(identity,component,component,body,'d'*40,'b'*64))
                db.execute('INSERT INTO step_instructions VALUES (?,?,?,?)',('stp_2',identity,component,1))
        self.accept();self.execute();call=Call.load(self.call_id,self.client)
        self.assertIsNone(call.error,call.error)
        request=call.steps['2'].request
        self.assertEqual(request.baseline.instructions,'Use deliberately generic prose.\n\nUse the accepted context.\n\nPerform the accepted task.')
        self.assertTrue(request.payload['instructions'].startswith(request.baseline.instructions+'\n\nRetrieved context'))
