from __future__ import annotations

from asc.ledger.util import insert_sql


CALL_COLUMNS = (
    "call",
    "plan",
    "record_identity",
    "raw_json",
    "created_at",
)

CALL_SELECT_COLUMNS = (
    "call AS call_identity",
    "call",
    "plan",
    "record_identity",
    "record_identity AS prompt_slug",
    "raw_json",
    "created_at",
)

STEP_INSERT_COLUMNS = (
    "call",
    "step_number",
    "handler",
    "engine",
    "status",
    "prompt",
    "response",
    "fail_message",
    "raw_json",
    "input_key",
    "output_key",
    "created_at",
    "started_at",
    "completed_at",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
)

STEP_COLUMNS = (
    "step_id",
    "call AS call_identity",
    "call",
    "step_number",
    "handler",
    "engine",
    "status",
    "prompt",
    "response",
    "fail_message",
    "raw_json",
    "input_key",
    "output_key",
    "created_at",
    "started_at",
    "completed_at",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
)

RESULT_COLUMNS = (
    "result",
    "call",
    "terminal_step_id",
    "created_at",
)

RESULT_SELECT_COLUMNS = (
    "result AS result_identity",
    "result",
    "call AS call_identity",
    "call",
    "terminal_step_id",
    "created_at",
)

EXPORT_COLUMNS = (
    "result",
    "export_message",
    "created_at",
)

EXPORT_SELECT_COLUMNS = (
    "result AS result_identity",
    "result",
    "export_message",
    "created_at",
)


INSERT_CALL_SQL = insert_sql("calls", CALL_COLUMNS)
INSERT_STEP_SQL = insert_sql("steps", STEP_INSERT_COLUMNS)
INSERT_RESULT_SQL = insert_sql("results", RESULT_COLUMNS)
INSERT_EXPORT_SQL = insert_sql("exports", EXPORT_COLUMNS)

UPDATE_STEP_COMPLETION_SQL = """
    UPDATE steps
    SET
        status = ?,
        response = ?,
        fail_message = ?,
        raw_json = ?,
        input_key = COALESCE(?, input_key),
        output_key = COALESCE(?, output_key),
        started_at = ?,
        completed_at = ?,
        prompt_tokens = ?,
        completion_tokens = ?,
        total_tokens = ?
    WHERE call = ?
      AND step_number = ?
      AND status IN ('pending', 'running')
"""


SELECT_CALL_SQL = f"""
    SELECT {", ".join(CALL_SELECT_COLUMNS)}
    FROM calls
    WHERE call = ?
"""

SELECT_CALL_BY_PROMPT_SLUG_SQL = f"""
    SELECT {", ".join(CALL_SELECT_COLUMNS)}
    FROM calls
    WHERE record_identity = ?
    ORDER BY created_at DESC
    LIMIT 1
"""

SELECT_CALLS_FOR_PLAN_SQL = f"""
    SELECT {", ".join(CALL_SELECT_COLUMNS)}
    FROM calls
    WHERE plan = ?
    ORDER BY created_at ASC
"""

SELECT_CALLS_SQL = f"""
    SELECT {", ".join(CALL_SELECT_COLUMNS)}
    FROM calls
    ORDER BY created_at ASC
"""

SELECT_CALL_IDENTITIES_FOR_PLAN_SQL = """
    SELECT call
    FROM calls
    WHERE plan = ?
    ORDER BY created_at ASC
"""


SELECT_STEP_SQL = f"""
    SELECT {", ".join(STEP_COLUMNS)}
    FROM steps
    WHERE step_id = ?
"""

SELECT_STEP_BY_CALL_NUMBER_SQL = f"""
    SELECT {", ".join(STEP_COLUMNS)}
    FROM steps
    WHERE call = ?
      AND step_number = ?
"""

SELECT_STEPS_FOR_CALL_SQL = f"""
    SELECT {", ".join(STEP_COLUMNS)}
    FROM steps
    WHERE call = ?
    ORDER BY step_number ASC, step_id ASC
"""

SELECT_PREVIOUS_COMPLETED_STEP_SQL = f"""
    SELECT {", ".join(STEP_COLUMNS)}
    FROM steps
    WHERE call = ?
      AND step_number = ?
      AND status = 'completed'
    ORDER BY step_id DESC
    LIMIT 1
"""


SELECT_RESULT_SQL = f"""
    SELECT {", ".join(RESULT_SELECT_COLUMNS)}
    FROM results
    WHERE result = ?
"""

SELECT_RESULT_BY_CALL_SQL = f"""
    SELECT {", ".join(RESULT_SELECT_COLUMNS)}
    FROM results
    WHERE call = ?
"""

SELECT_RESULTS_SQL = f"""
    SELECT {", ".join(RESULT_SELECT_COLUMNS)}
    FROM results
    ORDER BY created_at ASC
"""

SELECT_EXPORT_BY_RESULT_IDENTITY_SQL = f"""
    SELECT {", ".join(EXPORT_SELECT_COLUMNS)}
    FROM exports
    WHERE result = ?
"""

SELECT_INCOMPLETE_CALL_IDENTITIES_SQL = """
    SELECT c.call AS call_identity
    FROM calls AS c
    WHERE NOT EXISTS (
        SELECT 1
        FROM results AS r
        WHERE r.call = c.call
    )
    ORDER BY c.created_at ASC
"""


SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL = """
    SELECT
        c.call AS call_identity,
        c.call AS call,
        c.plan AS plan,
        c.record_identity AS prompt_slug,
        c.record_identity AS record_identity,
        c.raw_json AS raw_record,
        c.created_at AS call_created_at,
        r.result AS result_identity,
        r.result AS result,
        r.terminal_step_id AS terminal_step_id,
        r.created_at AS result_created_at,
        s.step_number AS step_number,
        s.prompt AS prompt_content,
        s.response AS content,
        s.raw_json AS raw_json,
        s.completed_at AS step_completed_at
    FROM calls AS c
    JOIN results AS r
        ON r.call = c.call
    JOIN steps AS s
        ON s.step_id = r.terminal_step_id
    WHERE c.call = ?
"""


__all__ = [
    "CALL_COLUMNS",
    "CALL_SELECT_COLUMNS",
    "STEP_COLUMNS",
    "STEP_INSERT_COLUMNS",
    "RESULT_COLUMNS",
    "RESULT_SELECT_COLUMNS",
    "EXPORT_COLUMNS",
    "EXPORT_SELECT_COLUMNS",
    "INSERT_CALL_SQL",
    "INSERT_STEP_SQL",
    "INSERT_RESULT_SQL",
    "INSERT_EXPORT_SQL",
    "UPDATE_STEP_COMPLETION_SQL",
    "SELECT_CALL_SQL",
    "SELECT_CALL_BY_PROMPT_SLUG_SQL",
    "SELECT_CALLS_FOR_PLAN_SQL",
    "SELECT_CALL_IDENTITIES_FOR_PLAN_SQL",
    "SELECT_CALLS_SQL",
    "SELECT_STEP_SQL",
    "SELECT_STEP_BY_CALL_NUMBER_SQL",
    "SELECT_STEPS_FOR_CALL_SQL",
    "SELECT_PREVIOUS_COMPLETED_STEP_SQL",
    "SELECT_RESULT_SQL",
    "SELECT_RESULT_BY_CALL_SQL",
    "SELECT_RESULTS_SQL",
    "SELECT_EXPORT_BY_RESULT_IDENTITY_SQL",
    "SELECT_INCOMPLETE_CALL_IDENTITIES_SQL",
    "SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL",
]
