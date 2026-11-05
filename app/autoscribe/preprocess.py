"""Transport adapter: retain source bytes; Pandoc alone interprets documents."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .ids import validate_submission_id

SCHEMA = 'autoscribe.prepared.v2'
MAX_DOCUMENT = 1048576
MAX_RECORD = 2097152
# Reader selection is independent of downstream representation policy. Only
# Markdown has a lossless downstream content policy in this release.
READERS = {'markdown': 'markdown+yaml_metadata_block+mark-smart', 'html': 'html', 'docx': 'docx'}


def reader_for(source_format: str) -> str:
    try:
        return READERS[source_format]
    except (KeyError, TypeError) as exc:
        raise ValueError('Unsupported input format') from exc


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def relative_path(value: object) -> str:
    if (not isinstance(value, str) or not value or len(value.encode('utf-8'))>4096
            or any(c in value for c in '\\:') or any(ord(c)<32 or ord(c)==127 for c in value)
            or any(p in ('', '.', '..') or p.lower()=='.git' for p in value.split('/'))):
        raise ValueError('Invalid source coordination path')
    return value


def _identity(envelope: dict) -> str:
    return validate_submission_id(envelope.get('submission_id'))


def prepare(envelope: object, *, work_dir: Path | None = None) -> dict:
    """Return one complete prepared success/failure. Never reconstruct Markdown."""
    original = copy.deepcopy(envelope)
    result = {'schema': SCHEMA, 'status': 'failed', 'content': '', 'content_sha256': digest(b''),
              'source': {}, 'baggage': {}, 'source_format': 'markdown', 'metadata': {},
              'directives': [], 'asset_references': [], 'assets': [], 'references': []}
    submission = None
    def failure(code: str, message: str) -> dict:
        result.update(status='failed', failure={'code': code, 'message': (message or 'Ingest failed without a diagnostic')[:4096]})
        # Failure-only identity when Pandoc cannot run. It never enters execution.
        if submission:
            seed = submission.encode('utf-8')
            result.setdefault('call_id', 'failed_'+digest(seed))
            result.update(submission_id=submission, record_id='inp_'+digest(seed)[:32])
        else:
            result['schema'] = 'autoscribe.ingest-error.v1'
        result['diagnostic_envelope'] = ({k:v for k,v in original.items()
            if k not in ('document','raw_markdown','content','baggage','source')}
            if isinstance(original,dict) else original)
        return result
    try:
        if not isinstance(envelope, dict):
            raise ValueError('Document envelope must be an object')
        if len(canonical(envelope)) >= MAX_RECORD:
            raise ValueError('Document envelope exceeds transport limit')
        if isinstance(envelope.get('source'), dict): result['source']=copy.deepcopy(envelope['source'])
        if isinstance(envelope.get('baggage'), dict): result['baggage']=copy.deepcopy(envelope['baggage'])
        submission = _identity(envelope)
        result.update(submission_id=submission, record_id='inp_'+digest(submission.encode('utf-8'))[:32])
        if 'call_source' in envelope:
            raise ValueError('call_source is retired; execution identity uses submission_id only')
        if envelope.get('schema') not in ('autoscribe.document.v1', 'autoscribe.input.v3'):
            raise ValueError('Unsupported document envelope version')
        if not isinstance(envelope.get('source', {}), dict) or not isinstance(envelope.get('baggage', {}), dict):
            raise ValueError('Invalid source or baggage object')
        if 'autoscribe_ingest' in result['baggage']:
            raise ValueError('Reserved baggage namespace autoscribe_ingest already supplied')
        source = result['source']; client = result['baggage'].get('client', {})
        if not isinstance(client,dict): raise ValueError('Invalid client coordination')
        if 'path' in source:
            relative_path(source['path'])
            if client.get('source_path', source['path'])!=source['path']:
                raise ValueError('Source/baggage path mismatch')
        elif 'source_path' in client:
            raise ValueError('Source/baggage path mismatch')
        if source.get('vault_id')!=client.get('vault_id', source.get('vault_id')):
            raise ValueError('Source/baggage vault mismatch')
        fmt = envelope.get('source_format', 'markdown')
        result['source_format']=fmt
        reader = reader_for(fmt)
        if fmt!='markdown':
            return failure('unsupported_representation', 'Native reader exists, but no downstream content policy is defined for '+fmt)
        raw = envelope.get('raw_markdown') if envelope['schema']=='autoscribe.input.v3' else envelope.get('document', envelope.get('content'))
        if not isinstance(raw, str):
            return failure('missing_document', 'Document content must be UTF-8 text')
        data = raw.encode('utf-8')
        if len(data)>MAX_DOCUMENT:
            raise ValueError('Document exceeds transport limit')
        result.update(content=raw, content_sha256=digest(data))
        claimed = envelope.get('raw_markdown_sha256', envelope.get('content_sha256'))
        if claimed is not None and claimed!=digest(data):
            raise ValueError('Original content checksum mismatch')
        if client.get('raw_markdown_sha256', digest(data))!=digest(data):
            raise ValueError('Client content checksum mismatch')
        external = envelope.get('metadata', {})
        if not isinstance(external, dict): raise ValueError('External metadata must be an object')
        # Coordination fields come only from the retained envelope, never AST data.
        sidecar = {k: external[k] for k in ('plan', 'slug') if k in external}
        claims=[]
        for container,key,name in ((envelope.get('routing',{}),'plan_id','plan'),
                                   (source,'slug','slug'),(client,'source_slug','slug')):
            if not isinstance(container,dict): raise ValueError('Invalid coordination object')
            if key in container: claims.append((name,container[key]))
        for name,value in claims:
            if name in sidecar and sidecar[name]!=value: raise ValueError('Conflicting external '+name)
            sidecar[name]=value
        filename = source.get('original_filename', source.get('path'))
        if filename is not None and (not isinstance(filename, str) or not filename.strip() or len(filename.encode('utf-8'))>4096):
            raise ValueError('Invalid original filename')
        sidecar.update(submission_id=submission, source_format=fmt, supplementary=external)
        if len(canonical(sidecar))>32768: raise ValueError('External metadata exceeds sidecar limit')
        if 'path' in source: sidecar['path']=source['path']
        if filename is not None: sidecar['original_filename']=filename
        templates = Path(os.environ.get('TEMPLATES_ROOT', '/opt/autoscribe/templates/current')).resolve()
        catalog = json.loads((templates/'resources.json').read_text(encoding='utf-8'))
        if catalog.get('schema')!='shared.resources.v1': raise ValueError('Unsupported resource catalogue')
        relative = Path(catalog['pandoc']['autoscribe-ingest'])
        defaults = (templates/relative).resolve(strict=True)
        defaults.relative_to(templates)
        if relative.is_absolute(): raise ValueError('Unsafe Pandoc defaults resource')
        executable = Path(os.environ.get('AUTOSCRIBE_PANDOC', '/usr/bin/pandoc'))
        if not executable.is_absolute(): raise ValueError('Pandoc executable must be absolute')
        # Hex makes the namespaced metadata immune to Markdown string parsing.
        # Command-line metadata has precedence over untrusted document metadata.
        command = [str(executable), '--defaults', str(defaults), '--from', reader,
                   '--metadata', 'autoscribe_transport:'+canonical(sidecar).hex()]
        try:
            completed = subprocess.run(command, input=data, capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return failure('pandoc_execution', str(exc))
        if completed.returncode:
            return failure('pandoc_execution', completed.stderr.decode('utf-8','replace'))
        try:
            parsed = json.loads(completed.stdout)
            if (parsed.get('schema')!='autoscribe.interpretation.v1'
                    or not re.fullmatch(r'call_[0-9a-f]{40}', parsed.get('call_id',''))
                    or 'call_source' in parsed or parsed.get('submission_id')!=submission
                    or not isinstance(parsed.get('source'), dict)):
                raise ValueError('Invalid interpretation contract')
            if (not isinstance(parsed.get('metadata'),dict)
                    or not isinstance(parsed.get('directives'),list)
                    or not isinstance(parsed.get('asset_references'),list)
                    or not isinstance(parsed['source'].get('hint'),str)):
                raise ValueError('Incomplete interpretation metadata')
            if 'failure' in parsed:
                if not isinstance(parsed['failure'],dict) or not all(
                    isinstance(parsed['failure'].get(k),str) and parsed['failure'][k] for k in ('code','message')):
                    raise ValueError('Invalid interpretation failure')
            elif not isinstance(parsed.get('plan'),str) or not re.fullmatch(r'pln_[A-Za-z0-9_-]{1,156}',parsed['plan']):
                raise ValueError('Missing prepared plan')
        except (ValueError, TypeError, AttributeError) as exc:
            return failure('serialization', str(exc))
        result.update(call_id=parsed['call_id'], metadata=parsed.get('metadata', {}),
                      directives=parsed.get('directives', []), asset_references=parsed.get('asset_references', []))
        # Only document-derived fields are merged; no AST value can change paths.
        identification=copy.deepcopy(source)
        identification.update({k:v for k,v in parsed['source'].items() if k!='path'})
        result['baggage']['autoscribe_ingest']={'source':identification, 'source_format':fmt,
            'submission_id':submission}
        if parsed['source'].get('slug'):
            source['slug']=parsed['source']['slug']
        result['plan']=parsed.get('plan')
        if parsed.get('failure'):
            result.update(failure=parsed['failure'])
        else:
            result['status']='ready'
        # Asset storage is transport work, outside enqueue/document semantics.
        if result['status']=='ready' and result['asset_references']:
            from .assets import stage_assets
            result['staged_assets']=stage_assets(result['asset_references'], work_dir)
        return result
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError) as exc:
        return failure('invalid_envelope', str(exc))
    except Exception as exc:
        return failure('ingest_execution', str(exc))
