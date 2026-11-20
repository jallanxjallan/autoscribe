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
