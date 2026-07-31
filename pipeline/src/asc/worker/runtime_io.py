"""Hydrate one canonical runtime record for engine execution."""
from dataclasses import dataclass
from asc.models.control.instruction import Instruction
from asc.models.process.call import CallRecord
from asc.models.process.result import Result, load_result, result_kind_for_engine_kind
from asc.models.process.runtime import Runtime
from asc.redis.key import RedisKey
ContentSource=CallRecord|Result
@dataclass(frozen=True,slots=True)
class EngineInput:
    runtime:Runtime; call:CallRecord; source:ContentSource; instructions:tuple[Instruction,...]; content:str

def build_engine_input(runtime:Runtime)->EngineInput:
    call=CallRecord.load(RedisKey(kind="call",identity=runtime.identity,suffix="record"))
    source=call if runtime.ordinal==1 else _load_previous_result(runtime)
    instructions=load_instructions(runtime.instruction_keys)
    return EngineInput(runtime,call,source,instructions,source.content)

def _load_previous_result(runtime:Runtime)->Result:
    previous=Runtime.load(RedisKey(kind="runtime",identity=runtime.identity,suffix=str(runtime.ordinal-1)))
    key=RedisKey(kind=result_kind_for_engine_kind(previous.engine_kind),identity=runtime.identity,suffix=str(runtime.ordinal-1))
    result=load_result(key)
    if result.identity!=runtime.identity: raise ValueError("previous result identity mismatch")
    return result

def load_instructions(instruction_keys):
    preferred=("role","context","instructions")
    labels=[x for x in preferred if x in instruction_keys]+[x for x in instruction_keys if x not in preferred]
    keys=[]
    for label in labels:
        value=instruction_keys[label]; keys.extend(value if isinstance(value,list) else [value])
    return tuple(Instruction.load(key) for key in keys)
