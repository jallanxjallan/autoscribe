"""The canonical call, component protocol and model-owned runtime persistence.

One aggregate per immutable call identity. SQLite never hydrates this record.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, PrivateAttr, ValidationError, model_validator
from biznet_common.redis import RedisClient, RedisError


IDENTITY_PATTERN = r'^(?:call_[0-9a-f]{40}|failed_[0-9a-f]{64})$'


class RuntimeRecordError(RuntimeError):
    """Base error for a canonical runtime boundary."""

class MissingRecord(RuntimeRecordError):
    """Missing or expired runtime data; never recover it from the ledger."""

class InvalidRecord(RuntimeRecordError):
    pass

class ConcurrentUpdate(RuntimeRecordError):
    pass

class StorageUnavailable(RuntimeRecordError):
    pass


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()



class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, populate_by_name=True, allow_inf_nan=False)


class ErrorInfo(Model):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    stage: str
    uncertain: bool = False


class Asset(Model):
    path: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    uri: str | None = None


class InlineAsset(Model):
    path: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    content_hex: str = Field(pattern=r'^(?:[a-fA-F0-9]{2})+$')

    @model_validator(mode='after')
    def integrity(self) -> Self:
        try:
            data=bytes.fromhex(self.content_hex)
        except ValueError as exc:
            raise ValueError('Invalid inline asset bytes') from exc
        if not data or hashlib.sha256(data).hexdigest()!=self.sha256:
            raise ValueError('Inline asset checksum mismatch')
        return self


class Source(Model):
    original_text: str | None
    original_sha256: str | None
    processing_text: str
    processing_sha256: str
    identity: str | None = None
    format: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    coordination: dict[str, JsonValue] = Field(default_factory=dict)
    assets: tuple[InlineAsset, ...] = ()
    resources: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode='after')
    def integrity(self) -> Self:
        if self.original_sha256 != (digest(self.original_text) if self.original_text is not None else None):
            raise ValueError('Original source checksum mismatch')
        if self.identity!=self.coordination.get('slug'):
            raise ValueError('Source identity differs from coordination slug')
        if digest(self.processing_text)!=self.processing_sha256:
            raise ValueError('Processing content checksum mismatch')
        return self


class Instruction(Model):
    component: str
    position: int = Field(ge=1)
    id: str
    label: str
    kind: str
    body: str
    source_commit: str
    content_sha256: str


class Step(Model):
    position: int = Field(ge=1)
    id: str = Field(min_length=1)
    label: str
    engine_kind: Literal['llm','script','rag']
    engine: str = Field(min_length=1)
    model: str | None = None
    script: str | None = None
    rag_profile: str | None = None
    args: dict[str, JsonValue] = Field(default_factory=dict)
    instructions: tuple[Instruction, ...] = ()
    source_commit: str
    content_sha256: str

    @model_validator(mode='after')
    def entrypoint(self) -> Self:
        if not {'llm':self.model,'script':self.script,'rag':self.rag_profile}[self.engine_kind]:
            raise ValueError('Step has no component entrypoint')
        return self

    @property
    def component(self) -> str:
        return {'llm':self.model,'script':self.script,'rag':self.rag_profile}[self.engine_kind]


class Plan(Model):
    id: str
    label: str
    description: str
    scope: str | None = None
    revision: str
    steps: tuple[Step, ...]

    @model_validator(mode='after')
    def unique_steps(self) -> Self:
        if not self.steps or len({s.position for s in self.steps})!=len(self.steps) or len({s.id for s in self.steps})!=len(self.steps):
            raise ValueError('Plan must have nonempty unique step identities and positions')
        return self

    @property
    def snapshot_sha256(self) -> str:
        return digest(json.dumps(self.model_dump(mode='json'),sort_keys=True,separators=(',',':')))

    @property
    def ordered_steps(self) -> tuple[Step, ...]:
        return tuple(sorted(self.steps,key=lambda s:s.position))


class StepInput(Model):
    text: str | None = None
    data: JsonValue = None
    assets: tuple[Asset, ...] = ()


class ComponentContext(Model):
    call_id: str = Field(pattern=IDENTITY_PATTERN)
    plan_id: str
    plan_revision: str
    plan_snapshot_sha256: str
    step_id: str
    position: int = Field(ge=1)
    engine_kind: Literal['llm','script','rag']
    engine: str
    component: str
    configuration: dict[str, JsonValue]
    input_position: int | None = None
    release_id: str

    def load_call(self, client: RedisClient | None = None) -> Call:
        call=Call.load(self.call_id,client)
        if self != call.invocation(self.position).context:
            raise InvalidRecord('Component context differs from the accepted call snapshot')
        return call


class Invocation(Model):
    protocol: Literal['asc.component.v1'] = 'asc.component.v1'
    context: ComponentContext
    input: StepInput

    def result(self, **values) -> StepResult:
        c=self.context
        return StepResult(call_id=c.call_id,step_id=c.step_id,position=c.position,
                          component=c.component,release_id=c.release_id,**values)


class RetrievalConfiguration(Model):
    service: str
    service_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    candidate_id: str = Field(pattern=r'^candidate_[0-9a-f]{32}$')
    mode: Literal['semantic', 'tagged']
    top: int = Field(default=5, ge=1, le=100, strict=True)
    tags: tuple[str, ...] = ()

    @model_validator(mode='after')
    def selection(self) -> Self:
        from pathlib import Path
        if not Path(self.service).is_absolute() or Path(self.service).name != 'train-candidate.py':
            raise ValueError('Expected absolute Model Management train-candidate.py interface')
        if any(not tag.strip() for tag in self.tags) or len(set(self.tags)) != len(self.tags):
            raise ValueError('Invalid tag filters')
        if (self.mode == 'tagged') != bool(self.tags):
            raise ValueError('Tagged mode requires tags; semantic mode does not accept tags')
        return self


class RetrievedPassage(Model):
    chunk_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    passage: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    receipt: str = Field(pattern=r'^[0-9a-f]{64}$')
    uri: str = Field(min_length=1)
    tags: tuple[str, ...]
    ordinal: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    content_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    rank: int = Field(ge=1)
    score: float = Field(ge=-1.0000001, le=1.0000001)

    @model_validator(mode='after')
    def integrity(self) -> Self:
        if digest(self.passage) != self.content_sha256 or self.end-self.start != len(self.passage):
            raise ValueError('Retrieved passage checksum or range mismatch')
        return self


class RetrievalResult(Model):
    schema_version: Literal['asc.retrieval.v1'] = 'asc.retrieval.v1'
    selection: RetrievalConfiguration
    query: str = Field(min_length=1)
    results: tuple[RetrievedPassage, ...]

    @model_validator(mode='after')
    def integrity(self) -> Self:
        if len(self.results)>self.selection.top or len({r.chunk_id for r in self.results})!=len(self.results):
            raise ValueError('Duplicate or excessive retrieved passages')
        if [r.rank for r in self.results]!=list(range(1,len(self.results)+1)):
            raise ValueError('Invalid retrieval ranks')
        if any(not set(self.selection.tags).issubset(r.tags) for r in self.results):
            raise ValueError('Retrieval response violates selected tag filters')
        if any(a.score<b.score for a,b in zip(self.results,self.results[1:])):
            raise ValueError('Retrieval response is not score ordered')
        return self


class BaselineRequest(Model):
    instructions: str
    input: StepInput


class ProviderRequest(Model):
    provider: Literal['OpenAI'] = 'OpenAI'
    payload: dict[str, JsonValue]
    timeout_seconds: float = Field(gt=0)
    baseline: BaselineRequest | None = None
    retrieval_positions: tuple[int, ...] = ()


class ProviderResponse(Model):
    provider: str
    model: str
    status: str
    response_id: str | None
    request_id: str | None
    usage: dict[str, JsonValue] | None


class StepResult(Model):
    protocol: Literal['asc.step-result.v1'] = 'asc.step-result.v1'
    call_id: str = Field(pattern=IDENTITY_PATTERN)
    step_id: str
    position: int = Field(ge=1)
    component: str
    release_id: str
    status: Literal['completed','failed'] = 'completed'
    text: str | None = None
    data: JsonValue = None
    assets: tuple[Asset, ...] = ()
    provider: ProviderResponse | None = None
    error: ErrorInfo | None = None

    @model_validator(mode='after')
    def outcome(self) -> Self:
        if (self.status=='failed') != (self.error is not None):
            raise ValueError('Result status and error disagree')
        if self.status=='completed' and self.text is None and self.data is None and not self.assets:
            raise ValueError('Completed result must contain processing output')
        return self

    @property
    def output(self) -> StepInput:
        return StepInput(text=self.text,data=self.data,assets=self.assets)

    @property
    def delivery_text(self) -> str:
        if self.text is not None:return self.text
        return json.dumps(self.data if self.data is not None else [a.model_dump() for a in self.assets],ensure_ascii=False,sort_keys=True,separators=(',',':'))


class StepExecution(Model):
    invocation: Invocation
    request: ProviderRequest | None = None
    result: StepResult | None = None


class Receipt(Model):
    kind: str
    target: str
    checksum: str
    details: dict[str, JsonValue] = Field(default_factory=dict)


class Call(Model):
    schema_version: Literal['asc.call.v1'] = Field(default='asc.call.v1', alias='schema')
    identity: str = Field(pattern=IDENTITY_PATTERN)
    submission_id: str
    record_id: str
    release_id: str = Field(min_length=1)
    fingerprint: str
    requested_plan_id: str | None
    source: Source
    plan: Plan | None
    baggage: dict[str, JsonValue]
    steps: dict[str, StepExecution] = Field(default_factory=dict)
    final_position: int | None = None
    error: ErrorInfo | None = None
    receipt: Receipt | None = None
    retention_period_seconds: int = Field(gt=0)
    retention_deadline: int | None = None
    _snapshot: str | None = PrivateAttr(default=None)

    @model_validator(mode='after')
    def integrity(self) -> Self:
        from asc.ids import validate_submission_id
        validate_submission_id(self.submission_id)
        expected='failed_'+digest(self.submission_id) if self.identity.startswith('failed_') else 'call_'+hashlib.sha1(self.submission_id.encode()).hexdigest()
        if self.identity!=expected or self.record_id!='inp_'+digest(self.submission_id)[:32]:
            raise ValueError('Call identity does not match immutable submission')
        if not self.error and (self.plan is None or self.source.original_text is None):
            raise ValueError('Executable call requires original source and a plan')
        if self.plan is not None and self.plan.id!=self.requested_plan_id:raise ValueError('Requested plan identity mismatch')
        for position,state in self.steps.items():
            context=state.invocation.context
            if str(context.position)!=position or context.call_id!=self.identity or context.release_id!=self.release_id:
                raise ValueError('Step ownership mismatch')
            if self.plan is None or context.plan_snapshot_sha256!=self.plan.snapshot_sha256 or context.plan_id!=self.plan.id or context.plan_revision!=self.plan.revision:
                raise ValueError('Step plan provenance mismatch')
            step=next((s for s in self.plan.steps if s.position==context.position),None)
            if step is None or (context.step_id,context.engine_kind,context.engine,context.component,context.configuration)!=(step.id,step.engine_kind,step.engine,step.component,step.args):
                raise ValueError('Step component differs from plan snapshot')
            try:expected=self.invocation(context.position)
            except RuntimeRecordError as exc:raise ValueError('Step input reference is unavailable') from exc
            if state.invocation!=expected:raise ValueError('Step input differs from the canonical previous output')
            if state.result:
                result=state.result
                if (result.call_id,result.step_id,result.position,result.component,result.release_id)!=(self.identity,step.id,step.position,step.component,self.release_id):
                    raise ValueError('Result ownership mismatch')
        if self.final_position is not None and (str(self.final_position) not in self.steps or self.steps[str(self.final_position)].result is None):
            raise ValueError('Final result reference is missing')
        if self.retention_deadline is not None and (self.receipt is None or not self.terminal):
            raise ValueError('Retention requires terminal acknowledged delivery')
        return self

    @property
    def terminal(self) -> bool:
        return self.error is not None or self.final_position is not None

    @property
    def final_result(self) -> StepResult:
        if self.final_position is None:raise MissingRecord('Call has no final processing result')
        return self.result(self.final_position)

    def result(self, position: int) -> StepResult:
        state=self.steps.get(str(position))
        if state is None or state.result is None:raise MissingRecord(f'Call {self.identity} has no result at position {position}')
        return state.result

    def invocation(self, position: int) -> Invocation:
        if self.plan is None:raise InvalidRecord('Call has no executable plan')
        ordered=self.plan.ordered_steps
        step=next((s for s in ordered if s.position==position),None)
        if step is None:raise InvalidRecord('Step is not in the accepted plan')
        prior=[s.position for s in ordered if s.position<position]
        previous=max(prior) if prior else None
        if previous is not None and self.result(previous).status!='completed':raise InvalidRecord('Previous component failed')
        value=self.result(previous).output if previous is not None else StepInput(text=self.source.processing_text,assets=tuple(Asset(path=a.path,sha256=a.sha256) for a in self.source.assets))
        return Invocation(context=ComponentContext(call_id=self.identity,plan_id=self.plan.id,plan_revision=self.plan.revision,
            plan_snapshot_sha256=self.plan.snapshot_sha256,step_id=step.id,position=position,engine_kind=step.engine_kind,
            engine=step.engine,component=step.component,configuration=step.args,input_position=previous,release_id=self.release_id),input=value)

    def evolve(self, **values) -> Call:
        data=self.model_dump(mode='json',by_alias=True);data.update(values)
        try:call=Call.model_validate(data)
        except ValidationError as exc:raise InvalidRecord(str(exc)) from exc
        call._snapshot=self._snapshot
        return call

    def with_step(self, position: int, execution: StepExecution) -> Call:
        values=dict(self.steps);values[str(position)]=execution
        return self.evolve(steps={k:v.model_dump(mode='json') for k,v in values.items()})

    @classmethod
    def load(cls, identity: str, client: RedisClient | None = None) -> Call:
        return RuntimeStore(client).load(identity)

    def save(self, client: RedisClient | None = None) -> Call:
        RuntimeStore(client).save(self)
        return self

    def retain_after_cleanup(self, client: RedisClient | None = None, *, now: int | None = None) -> Call:
        if self.retention_deadline is not None:return self
        if not self.terminal or self.receipt is None:raise InvalidRecord('Cleanup retention requires terminal delivery receipt')
        return self.evolve(retention_deadline=(int(time.time()) if now is None else now)+self.retention_period_seconds).save(client)

    def response_record(self, *, client_protocol: bool = False) -> dict:
        text='' if self.error else self.final_result.delivery_text
        record={'schema':'autoscribe.client-response.v1' if client_protocol else 'autoscribe.response.v1',
                'submission_id':self.submission_id,'call_id':self.identity,'status':'failed' if self.error else 'completed',
                'result' if client_protocol else 'content':text,'baggage':self.baggage}
        if client_protocol:
            record.update(result_bytes=len(text.encode('utf-8')),result_sha256=digest(text),source=self.source.coordination,
                          routing={'plan_id':self.requested_plan_id},metadata=self.source.metadata)
        if self.error:record.update(failure=self.error.code,error=self.error.message)
        return record


class RuntimeStore:
    """Single key owner; aggregate CAS writes and lifecycle expiry are atomic."""
    def __init__(self, client: RedisClient | None = None):
        self.client=client if client is not None else RedisClient(os.environ.get('AUTOSCRIBE_REDIS_HOST','127.0.0.1'),int(os.environ.get('AUTOSCRIBE_REDIS_PORT','6379')))

    @staticmethod
    def key(identity: str) -> str:
        if not re.fullmatch(IDENTITY_PATTERN,identity):raise InvalidRecord('Invalid call identity')
        return f'asc:call:{identity}'

    def load(self, identity: str) -> Call:
        try:raw=self.client.command('GET',self.key(identity))
        except (RedisError,OSError) as exc:raise StorageUnavailable('Runtime Redis unavailable') from exc
        if raw is None:raise MissingRecord(f'Missing or expired call: {identity}')
        try:call=Call.model_validate_json(raw)
        except (ValidationError,ValueError,TypeError) as exc:raise InvalidRecord(f'Malformed call: {identity}') from exc
        if call.identity!=identity:raise InvalidRecord('Stored call identity differs from key')
        call._snapshot=raw
        return call

    def save(self, call: Call) -> None:
        try:Call.model_validate_json(call.model_dump_json(by_alias=True))
        except ValidationError as exc:raise InvalidRecord(str(exc)) from exc
        payload=call.model_dump_json(by_alias=True)
        if call._snapshot is not None:
            old=Call.model_validate_json(call._snapshot)
            if any(getattr(old,k)!=getattr(call,k) for k in ('identity','submission_id','record_id','release_id','fingerprint','requested_plan_id','source','plan','baggage','retention_period_seconds')):
                raise InvalidRecord('Accepted source, identity and configuration are immutable')
            for position,previous in old.steps.items():
                current=call.steps.get(position)
                if current is None or current.invocation!=previous.invocation or (previous.request is not None and current.request!=previous.request) or (previous.result is not None and current.result!=previous.result):
                    raise InvalidRecord('Recorded step inputs, requests and outcomes are immutable')
            if old.terminal and (old.steps!=call.steps or old.error!=call.error or old.final_position!=call.final_position):
                raise InvalidRecord('Terminal processing facts are immutable')
            if old.receipt is not None and old.receipt!=call.receipt:raise InvalidRecord('Delivery receipt is immutable')
            if old.retention_deadline is not None and old.retention_deadline!=call.retention_deadline:raise InvalidRecord('Retention deadline is immutable')
        try:
            status=self.client.command('EVAL', '''
              local old=redis.call('GET',KEYS[1])
              if ARGV[1]=='' then
                if old then return -1 end
              elseif not old then return -2
              elseif old~=ARGV[1] then return -1 end
              local deadline=tonumber(ARGV[3])
              if deadline>0 and deadline<=tonumber(redis.call('TIME')[1]) then return -2 end
              redis.call('SET',KEYS[1],ARGV[2])
              if deadline>0 then redis.call('EXPIREAT',KEYS[1],deadline) end
              return 1
              ''',1,self.key(call.identity),call._snapshot or '',payload,call.retention_deadline or 0)
        except (RedisError,OSError) as exc:raise StorageUnavailable('Runtime Redis write failed') from exc
        if status==-2:raise MissingRecord('Runtime expired before update; do not replay execution')
        if status!=1:raise ConcurrentUpdate('Runtime changed concurrently')
        call._snapshot=payload
