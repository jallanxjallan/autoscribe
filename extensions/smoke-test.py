#!/usr/bin/env python3
"""Verify the existing Control smoke protocol; stdin/stdout only, no network."""
import sys

EXPECTED = (
    'AUTOSCRIBE_LLM_SMOKE_V1',
    'ROLE=PASS',
    'CONTEXT=PASS',
    'TASK=PASS',
    'INPUT=AUTOSCRIBE_SMOKE_INPUT_V1',
)


def main():
    data = sys.stdin.buffer.read(1048577)
    try:
        if len(data) > 1048576:
            raise ValueError('response exceeds input limit')
        text = data.decode('utf-8').replace('\r\n', '\n')
        if text.endswith('\n'):
            text = text[:-1]
        if tuple(text.split('\n')) != EXPECTED:
            raise ValueError('expected exactly the five Control smoke protocol lines')
    except (UnicodeError, ValueError) as error:
        print('smoke-test: '+str(error), file=sys.stderr)
        return 2
    # Preserve the verified response, including its original line endings.
    sys.stdout.buffer.write(data)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
