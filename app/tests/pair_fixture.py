#!/usr/bin/env python3
"""Test-only authorial-voice interface demonstration, not a production generator."""
import sys
from asc.models.call import Call, Invocation
invocation=Invocation.model_validate_json(sys.stdin.read())
call=Call.load(invocation.context.call_id)
invocation.context.load_call()
previous=call.result(invocation.context.input_position)
if previous.output!=invocation.input:raise ValueError('Previous result differs from supplied input')
print(invocation.result(data={'original':call.source.original_text,'generated':invocation.input.text,
    'identity':call.source.identity,'tone':call.baggage['autoscribe_ingest']['metadata'].get('tone'),
    'narrative_mode':call.baggage['autoscribe_ingest']['metadata'].get('narrative_mode')}).model_dump_json())
