"""One typed component invocation path; provider authority remains in Common."""
from __future__ import annotations
import base64
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

import biznet_common
from biznet_common.llm import LLMError, respond
from .settings import release_identity
from .models.call import (Call, Invocation, StepExecution, StepResult, ProviderRequest,
                          ProviderResponse, ErrorInfo, InvalidRecord, RuntimeRecordError)


def load_registry(path: Path) -> dict[str, Path]:
    raw=json.loads(path.read_text())
    if not isinstance(raw,dict):raise InvalidRecord('Executable registry must be an object')
    result={}
    for name,target in raw.items():
        if not isinstance(name,str) or not name or any(c.isspace() for c in name) or not isinstance(target,str) or not Path(target).is_absolute():
            raise InvalidRecord('Invalid registered executable')
        result[name]=Path(target)
    return result


def run_extension(executable: Path, invocation: Invocation, timeout: float) -> StepResult:
    if not executable.is_file() or not os.access(executable,os.X_OK):raise InvalidRecord('Registered component is not executable')
    roots=dict.fromkeys((str(Path(__file__).resolve().parents[1]),str(Path(biznet_common.__file__).resolve().parents[1])))
    env=dict(os.environ,PYTHONPATH=os.pathsep.join(roots),
             PATH=str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH','/usr/bin:/bin'))
    process=subprocess.run([str(executable)],input=invocation.model_dump_json()+'\n',text=True,
        capture_output=True,check=False,timeout=timeout,close_fds=True,env=env)
    if process.returncode:raise InvalidRecord(f'Component exited {process.returncode}: {process.stderr.strip()}')
    if process.stderr:logging.getLogger(__name__).info('Component %s diagnostic: %s',invocation.context.component,process.stderr.strip())
    if len(process.stdout.encode('utf-8'))>4_194_304:raise InvalidRecord('Component result exceeds protocol limit')
    try:return StepResult.model_validate_json(process.stdout)
    except ValueError as exc:raise InvalidRecord('Component stdout must be one asc.step-result.v1 JSON result') from exc


def run_llm(invocation: Invocation, timeout: float, client) -> StepResult:
    context=invocation.context
    if context.engine!='chatgpt':raise InvalidRecord('Unsupported LLM engine')
    call=context.load_call(client)
    step=next(s for s in call.plan.steps if s.position==context.position)
    images=[]
    for asset in invocation.input.assets:
        if asset.uri:
            images.append((asset.uri,'auto'));continue
        original=next((a for a in call.source.assets if a.path==asset.path and a.sha256==asset.sha256),None)
        if original is None:raise InvalidRecord('Input asset is not in the accepted call')
        if invocation.input.text is None or f']({asset.path})' not in invocation.input.text:continue
        types={'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','webp':'image/webp','gif':'image/gif'}
        suffix=Path(asset.path).suffix.lower().lstrip('.')
        if suffix not in types:raise InvalidRecord('Unsupported provider image format')
        images.append((f'data:{types[suffix]};base64,'+base64.b64encode(bytes.fromhex(original.content_hex)).decode(),'auto'))
    def assembled(payload):
        current=Call.load(context.call_id,client)
        state=current.steps[str(context.position)]
        current.with_step(context.position,StepExecution(invocation=state.invocation,
            request=ProviderRequest(payload=payload,timeout_seconds=timeout))).save(client)
    content=invocation.input.text
    if content is None:content=json.dumps(invocation.input.data,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    response=respond('autoscribe-worker',context.component,content,
        instructions='\n\n'.join(i.body.strip() for i in step.instructions if i.body.strip()),
        images=images,timeout=timeout,parameters=context.configuration,on_request=assembled)
    provider=ProviderResponse(provider=response.provider,model=response.model,status=response.status,
        response_id=response.response_id,request_id=response.request_id,usage=response.usage)
    if response.status!='completed':
        return invocation.result(status='failed',text=response.text,provider=provider,
            error=ErrorInfo(code='provider_incomplete',message='Provider did not complete the request',stage='llm',uncertain=response.status in ('queued','in_progress')))
    return invocation.result(text=response.text,provider=provider)


def execute(invocation: Invocation, client, registry: dict[str, Path], *, script_timeout=30.0,llm_timeout=120.0) -> StepResult:
    if invocation.context.release_id!=release_identity():raise InvalidRecord('Component belongs to a different immutable release')
    call=invocation.context.load_call(client)
    position=invocation.context.position
    if str(position) in call.steps:raise InvalidRecord('Step has already started; no automatic replay')
    call.with_step(position,StepExecution(invocation=invocation)).save(client)
    try:
        if invocation.context.engine_kind=='llm':result=run_llm(invocation,llm_timeout,client)
        elif invocation.context.engine_kind=='script':
            executable=registry.get(invocation.context.component)
            if executable is None:raise InvalidRecord('Unregistered component')
            result=run_extension(executable,invocation,script_timeout)
        else:raise InvalidRecord('RAG execution is not implemented')
        expected=invocation.context
        if (result.call_id,result.step_id,result.position,result.component,result.release_id)!=(expected.call_id,expected.step_id,expected.position,expected.component,expected.release_id):
            raise InvalidRecord('Component result ownership mismatch')
    except (LLMError,InvalidRecord,subprocess.TimeoutExpired,OSError) as exc:
        result=invocation.result(status='failed',error=ErrorInfo(code=exc.category if isinstance(exc,LLMError) else type(exc).__name__,
            message=str(exc) or type(exc).__name__,stage=invocation.context.engine_kind,
            uncertain=isinstance(exc,subprocess.TimeoutExpired) or isinstance(exc,LLMError) and exc.category in ('timeout','connection_failure','provider_error','provider_failure','invalid_response')))
    current=Call.load(call.identity,client)
    state=current.steps[str(position)]
    current.with_step(position,StepExecution(invocation=state.invocation,request=state.request,result=result)).save(client)
    return result
