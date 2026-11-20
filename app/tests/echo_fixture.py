#!/usr/bin/env python3
import sys
from asc.models.call import Invocation
invocation=Invocation.model_validate_json(sys.stdin.read())
invocation.context.load_call()
print(invocation.result(**invocation.input.model_dump()).model_dump_json())
