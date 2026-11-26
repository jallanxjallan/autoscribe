"""One typed component invocation path; provider authority remains in Common."""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

import biznet_common
from .settings import release_identity
from .models.call import (Call, Invocation, StepExecution, StepResult,
                          ErrorInfo, InvalidRecord, RetrievalResult, RetrievalConfiguration)


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
    model_step = invocation.context.engine_kind == 'llm'
    if model_step:
        env['AUTOSCRIBE_LLM_TIMEOUT_SECONDS'] = str(timeout)
    process=subprocess.run([str(executable)],input=invocation.model_dump_json()+'\n',text=True,
        capture_output=True,check=False,timeout=timeout + 5.0 if model_step else timeout,close_fds=True,env=env)
    if process.returncode:raise InvalidRecord(f'Component exited {process.returncode}: {process.stderr.strip()}')
    if process.stderr:logging.getLogger(__name__).info('Component %s diagnostic: %s',invocation.context.component,process.stderr.strip())
    if len(process.stdout.encode('utf-8'))>4_194_304:raise InvalidRecord('Component result exceeds protocol limit')
    try:return StepResult.model_validate_json(process.stdout)
    except ValueError as exc:raise InvalidRecord('Component stdout must be one asc.step-result.v1 JSON result') from exc


def execute(invocation: Invocation, client, registry: dict[str, Path], *, script_timeout=30.0,llm_timeout=120.0) -> StepResult:
    if invocation.context.release_id!=release_identity():raise InvalidRecord('Component belongs to a different immutable release')
    call=invocation.context.load_call(client)
    position=invocation.context.position
    if str(position) in call.steps:raise InvalidRecord('Step has already started; no automatic replay')
    call.with_step(position,StepExecution(invocation=invocation)).save(client)
    try:
        executable=registry.get(invocation.context.component)
        if executable is None:raise InvalidRecord('Unregistered component')
        timeout = llm_timeout if invocation.context.engine_kind == 'llm' else script_timeout
        result=run_extension(executable,invocation,timeout)
        if invocation.context.engine_kind=='rag' and result.status=='completed':
            try:retrieval=RetrievalResult.model_validate(result.data)
            except ValueError as exc:raise InvalidRecord('Malformed canonical retrieval result') from exc
            if retrieval.selection != RetrievalConfiguration.model_validate(invocation.context.configuration):
                raise InvalidRecord('Retrieval selection differs from accepted configuration')
            if retrieval.query!=invocation.input.text or result.text!=invocation.input.text:
                raise InvalidRecord('Retrieval must preserve its predecessor processing text')
        expected=invocation.context
        if (result.call_id,result.step_id,result.position,result.component,result.release_id)!=(expected.call_id,expected.step_id,expected.position,expected.component,expected.release_id):
            raise InvalidRecord('Component result ownership mismatch')
    except (InvalidRecord,ValueError,subprocess.TimeoutExpired,OSError) as exc:
        result=invocation.result(status='failed',error=ErrorInfo(code=type(exc).__name__,
            message=str(exc) or type(exc).__name__,stage=invocation.context.engine_kind,
            uncertain=isinstance(exc,subprocess.TimeoutExpired)))
    current=Call.load(call.identity,client)
    state=current.steps[str(position)]
    current.with_step(position,StepExecution(invocation=state.invocation,request=state.request,result=result)).save(client)
    return result
