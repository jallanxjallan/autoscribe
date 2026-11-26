from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path

from .models.call import Plan
from biznet_common.control import ControlError, connect, list_labels


class UnknownPlanError(ControlError):
    pass


def resolve_plan(db_path: Path, plan_id: str) -> dict | None:
    with closing(connect(db_path)) as db, db:
        row = db.execute(
            "SELECT id, label, description, scope FROM plans WHERE id = ?",
            (plan_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def list_plans(db_path: Path) -> list[dict]:
    return list_labels(db_path, "plans")


def _decode_args(raw: object, *, step_id: str) -> dict:
    if raw in (None, ""):
        return {}
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ControlError(f"step {step_id} has invalid args_json") from exc
    if not isinstance(value, dict):
        raise ControlError(f"step {step_id} args_json is not an object")
    return value


def materialize_plan(db_path: Path, plan_id: str) -> Plan:
    with closing(connect(db_path)) as db, db:
        plan_row = db.execute(
            "SELECT id, label, description, scope FROM plans WHERE id = ?",
            (plan_id,),
        ).fetchone()
        if plan_row is None:
            raise UnknownPlanError(f"unknown plan id: {plan_id}")

        revision=db.execute("SELECT value FROM control_meta WHERE key='source_commit'").fetchone()[0]
        step_rows = db.execute(
            """
            SELECT ps.position AS step_position,
                   s.id,
                   s.label,
                   s.engine_kind,
                   s.engine,
                   s.model,
                   s.script,
                   s.rag_profile,
                   s.source_commit, s.content_sha256, s.args_json
            FROM plan_steps ps
            JOIN steps s ON s.id = ps.step_id
            WHERE ps.plan_id = ?
            ORDER BY ps.position, s.id
            """,
            (plan_id,),
        ).fetchall()
        if not step_rows:
            raise ControlError(f"plan {plan_id} has no steps")

        steps = []
        for step in step_rows:
            instruction_rows = db.execute(
                """
                SELECT si.component,
                       si.position,
                       i.id,
                       i.label,
                       i.kind,
                       i.source_commit, i.content_sha256, i.body
                FROM step_instructions si
                JOIN instructions i ON i.id = si.instruction_id
                WHERE si.step_id = ?
                ORDER BY CASE si.component
                           WHEN 'role' THEN 1
                           WHEN 'context' THEN 2
                           WHEN 'task' THEN 3
                           ELSE 4
                         END,
                         si.position,
                         i.id
                """,
                (step["id"],),
            ).fetchall()
            steps.append(
                {
                    "source_commit": str(step["source_commit"]), "content_sha256": str(step["content_sha256"]),
                    "position": int(step["step_position"]),
                    "id": str(step["id"]),
                    "label": str(step["label"]),
                    "engine_kind": str(step["engine_kind"]),
                    "engine": str(step["engine"]),
                    "model": step["model"],
                    "script": step["script"],
                    "rag_profile": step["rag_profile"],
                    "args": _decode_args(step["args_json"], step_id=str(step["id"])),
                    "instructions": [
                        {
                            "source_commit": str(row["source_commit"]), "content_sha256": str(row["content_sha256"]),
                            "component": str(row["component"]),
                            "position": int(row["position"]),
                            "id": str(row["id"]),
                            "label": str(row["label"]),
                            "kind": str(row["kind"]),
                            "body": str(row["body"]),
                        }
                        for row in instruction_rows
                    ],
                }
            )

    return Plan.model_validate({
        "revision":revision,
        "id": str(plan_row["id"]),
        "label": str(plan_row["label"]),
        "description": str(plan_row["description"] or ""),
        "scope": plan_row["scope"],
        "steps": steps,
    })


def name_key(value: str) -> str:
    import re
    import unicodedata
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    key = re.sub(r'[^a-z0-9]+', '-', value).strip('-')
    if not key:
        raise ControlError('Plan name needs a searchable name key')
    return key


def plan_metadata(record: dict, revision: str = '') -> dict:
    """One projection of canonical Control plan source; no writable index."""
    import re
    title = record['title']
    if not isinstance(title, str) or not title.strip() or any(ord(c) < 32 for c in title):
        raise ControlError('Invalid plan display name')
    key = record.get('name_key', name_key(title))
    if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key):
        raise ControlError('name_key must be lowercase and hyphenated')
    lists = {}
    for field in ('tags', 'aliases'):
        values = record.get(field, [])
        if (not isinstance(values, list) or len(values) > 32 or
            any(not isinstance(v, str) or not v.strip() or len(v) > 160 or any(ord(c)<32 for c in v) for v in values)
            or len({v.casefold() for v in values}) != len(values)):
            raise ControlError('Invalid plan '+field)
        lists[field] = values
    status = record.get('status', 'registered')
    if status not in ('registered', 'retired'):
        raise ControlError('Plan source status must be registered or retired')
    return dict(plan_id=record['identity'], display_name=title, name_key=key,
        description=' '.join((record.get('description') or '').split()), **lists, revision=revision, status=status)


def validate_plan_names(records):
    names = {}
    for record in records:
        metadata = plan_metadata(record)
        for value in [metadata['name_key'], metadata['display_name'], *metadata['aliases']]:
            token = name_key(value)
            owner = names.setdefault(token, metadata['plan_id'])
            if owner != metadata['plan_id']:
                raise ControlError(f'Plan name/alias {value!r} conflicts with {owner}; choose another name or revise that plan')


def plan_index(db_path: Path, *, repo: Path = Path('/home/jeremy/Repos/control.git'),
               git_adapter: Path = Path('/home/jeremy/.local/bin/git.py')) -> list[dict]:
    """Read only the exact accepted source blobs, verifying their DB provenance."""
    import hashlib
    import subprocess
    with closing(connect(db_path)) as db:
        db.execute('BEGIN')
        rows = db.execute('SELECT id,source_path,source_commit,content_sha256 FROM plans ORDER BY label COLLATE NOCASE,id').fetchall()
    result = []
    for row in rows:
        raw = subprocess.check_output([str(git_adapter), '-C', str(repo), 'show',
            row['source_commit']+':'+row['source_path']], timeout=15)
        if hashlib.sha256(raw).hexdigest() != row['content_sha256']:
            raise ControlError('Plan source checksum mismatch: '+row['id'])
        record = json.loads(raw)
        if record['identity'] != row['id']:
            raise ControlError('Plan index identity mismatch')
        result.append(plan_metadata(record, row['source_commit']))
    validate_plan_names([dict(identity=r['plan_id'],title=r['display_name'],name_key=r['name_key'],
        description=r['description'],tags=r['tags'],aliases=r['aliases'],status=r['status']) for r in result])
    return [r for r in result if r['status']=='registered']


def compatible_control(db_path: Path, manifest: dict, runtime_root: Path) -> dict:
    """Accepted Control content evolves independently; executable contracts do not."""
    import re
    with closing(connect(db_path)) as db:
        db.execute('BEGIN')
        meta = dict(db.execute('SELECT key,value FROM control_meta'))
        if meta.get('schema_version') != '3':
            raise ControlError('Unsupported accepted Control schema: '+str(meta.get('schema_version')))
        if not re.fullmatch(r'[0-9a-f]{40}', meta.get('source_commit','')):
            raise ControlError('Missing accepted Control source revision')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ControlError('Broken Control references')
        # Exact queries prove the API fields required by materialize_plan exist.
        db.execute('SELECT id,label,description,scope,source_commit FROM plans LIMIT 0')
        steps = db.execute('SELECT id,engine_kind,engine,model,script,rag_profile,args_json FROM steps').fetchall()
        db.execute('SELECT id,label,kind,body,source_commit,content_sha256 FROM instructions LIMIT 0')
        db.execute('SELECT plan_id,step_id,position FROM plan_steps LIMIT 0')
        db.execute('SELECT step_id,instruction_id,component,position FROM step_instructions LIMIT 0')
        bad = db.execute("SELECT si.step_id FROM step_instructions si JOIN steps s ON s.id=si.step_id WHERE s.engine_kind!='llm' LIMIT 1").fetchone()
        if bad: raise ControlError('Control instructions on non-LLM step '+bad[0])
        plans = [r[0] for r in db.execute('SELECT id FROM plans')]
    registry = json.loads((runtime_root/'extensions/registry.json').read_text())
    for step in steps:
        kind = step['engine_kind']
        field = {'llm':'model','script':'script','rag':'rag_profile'}.get(kind)
        component = step[field] if field else None
        if component not in registry:
            raise ControlError(f"Step {step['id']} references unavailable component {component!r}")
        if kind=='llm':
            if component not in set(manifest['model_catalogue']) | set(manifest['model_catalogue'].values()):
                raise ControlError('Unsupported model '+component)
            from biznet_common.llm import _validate
            # Common remains the authoritative configuration validator.
            _validate('autoscribe-worker', json.loads(step['args_json'] or '{}'), 120)
        elif kind=='rag':
            from .models.call import RetrievalConfiguration
            RetrievalConfiguration.model_validate(json.loads(step['args_json'] or '{}'))
        target = runtime_root / Path(registry[component]).relative_to(manifest['installed_engine'])
        if not target.is_file():
            raise ControlError('Missing packaged executable '+component)
    for plan_id in plans:
        plan = materialize_plan(db_path, plan_id)
        for step in plan.steps:
            if step.script=='compose-text':
                import subprocess
                checked = subprocess.run([__import__('sys').executable, '-B', str(runtime_root / Path(registry['compose-text']).relative_to(manifest['installed_engine'])), '--validate-config'], input=json.dumps(dict(
                    configuration=step.args,position=step.position,predecessors=[s.position for s in plan.steps if s.position<step.position])),
                    capture_output=True,text=True,timeout=10)
                if checked.returncode: raise ControlError('Incompatible compose configuration: '+step.id)
    return dict(schema_version=3, accepted_revision=meta['source_commit'], plans=len(plans), steps=len(steps))
