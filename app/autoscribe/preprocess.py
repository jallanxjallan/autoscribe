"""Supervise versioned Pandoc interpretation; never parse Markdown in Python."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess


class PreprocessInfrastructureError(RuntimeError):
    pass


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def interpret(raw: str) -> dict:
    root = Path(os.environ.get('TEMPLATES_ROOT', '/opt/autoscribe/templates/current')).resolve()
    try:
        catalog = json.loads((root / 'resources.json').read_text(encoding='utf-8'))
        if catalog.get('schema') != 'shared.resources.v1':
            raise ValueError('unsupported resource catalogue')
        relative = Path(catalog['pandoc']['autoscribe-ingest-v1'])
        script = (root / relative).resolve(strict=True)
        script.relative_to(root)
        if relative.is_absolute() or not script.is_file():
            raise ValueError('unsafe preprocessing resource')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PreprocessInfrastructureError('Versioned Pandoc ingest resource unavailable') from exc
    executable = Path(os.environ.get('AUTOSCRIBE_PANDOC', '/usr/bin/pandoc'))
    if not executable.is_absolute():
        raise PreprocessInfrastructureError('Pandoc executable must be absolute')
    try:
        process = subprocess.run([str(executable), 'lua', str(script)], input=raw.encode('utf-8'),
                                 capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreprocessInfrastructureError('Pandoc process unavailable or timed out') from exc
    if process.returncode:
        raise PreprocessInfrastructureError(f'Pandoc process/configuration failed ({process.returncode})')
    try:
        result = json.loads(process.stdout.decode('utf-8'))
        if not isinstance(result, dict) or result.get('schema') != 'autoscribe.preprocess.v1':
            raise ValueError('invalid preprocessing schema')
        if 'failure' in result:
            if (not isinstance(result['failure'], str) or not result['failure'].strip()
                    or result.get('content') != ''):
                raise ValueError('invalid failure result')
        elif (not isinstance(result.get('content'), str) or not result['content']
              or not isinstance(result.get('slug'), str) or not result['slug']
              or not isinstance(result.get('plan_id'), str) or not result['plan_id'].startswith('pln_')
              or not isinstance(result.get('assets'), list) or not isinstance(result.get('directives'), list)):
            raise ValueError('incomplete preprocessing result')
    except (UnicodeError, ValueError, TypeError) as exc:
        raise PreprocessInfrastructureError('Invalid/partial Pandoc serialization') from exc
    return result


def prepare(record: dict) -> dict:
    """Prepare normalized execution content, without inventing original-source hashes."""
    parsed = interpret(record['raw_markdown'])
    for claimed in (record['source'].get('slug'), record['baggage']['client'].get('source_slug')):
        if claimed is not None and parsed.get('slug') is not None and claimed != parsed['slug']:
            raise ValueError('source slug mismatch at ingest')
    result = {key: copy.deepcopy(record[key]) for key in ('record_id', 'source', 'baggage')}
    result.update(schema='autoscribe.prepared.v1', content_format='markdown', directive_policy='inline.v1',
                  routing={'plan_id': parsed.get('plan_id')}, content=parsed['content'],
                  content_sha256=_sha(parsed['content']), references=[], assets=[],
                  asset_references=parsed.get('assets', []), directives=parsed.get('directives', []),
                  metadata=parsed.get('metadata', {}))
    client = result['baggage']['client']
    if parsed.get('slug'):
        result['source']['slug'] = client['source_slug'] = parsed['slug']
    if parsed.get('failure'):
        result['failure'] = parsed['failure']
        result['failure_reason'] = parsed.get('reason', 'Preprocessing failed')
    return result
