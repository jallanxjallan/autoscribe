from asc.scrivener.util import insert_sql


CALL_COLUMNS = (
    "identity",
    "source_identity",
    "source_json",
    "created_at",
)

STEP_COLUMNS = (
    "identity",
    "step_number",
    "result_key",
    "status",
    "content",
    "fail_message",
    "raw_json",
    "created_at",
)

EXPORT_COLUMNS = (
    "identity",
    "source_identity",
    "final_step",
    "result_key",
    "exported_at",
    "export_message",
    "created_at",
)

INSERT_CALL_SQL = insert_sql("calls", CALL_COLUMNS)
INSERT_STEP_SQL = insert_sql("steps", STEP_COLUMNS)
INSERT_EXPORT_SQL = insert_sql("exports", EXPORT_COLUMNS)

CONFIRM_EXPORT_SQL = """
    UPDATE exports
    SET
        exported_at = ?,
        export_message = ?
    WHERE identity = ?
"""

SELECT_CALL_SQL = f"""
    SELECT {", ".join(CALL_COLUMNS)}
    FROM calls
    WHERE identity = ?
"""

SELECT_CALL_BY_SOURCE_IDENTITY_SQL = f"""
    SELECT {", ".join(CALL_COLUMNS)}
    FROM calls
    WHERE source_identity = ?
    ORDER BY created_at DESC
    LIMIT 1
"""

SELECT_CALLS_SQL = f"""
    SELECT {", ".join(CALL_COLUMNS)}
    FROM calls
    ORDER BY created_at ASC
"""

SELECT_STEP_BY_IDENTITY_NUMBER_SQL = f"""
    SELECT {", ".join(STEP_COLUMNS)}
    FROM steps
    WHERE identity = ?
      AND step_number = ?
"""

SELECT_STEPS_FOR_IDENTITY_SQL = f"""
    SELECT {", ".join(STEP_COLUMNS)}
    FROM steps
    WHERE identity = ?
    ORDER BY step_number ASC
"""

SELECT_EXPORT_BY_IDENTITY_SQL = f"""
    SELECT {", ".join(EXPORT_COLUMNS)}
    FROM exports
    WHERE identity = ?
"""

SELECT_PENDING_EXPORTS_SQL = f"""
    SELECT {", ".join(EXPORT_COLUMNS)}
    FROM exports
    WHERE exported_at IS NULL
    ORDER BY created_at ASC, identity ASC
"""

SELECT_PENDING_EXPORT_BY_SOURCE_IDENTITY_SQL = f"""
    SELECT {", ".join(EXPORT_COLUMNS)}
    FROM exports
    WHERE source_identity = ?
      AND exported_at IS NULL
    ORDER BY created_at ASC, identity ASC
    LIMIT 1
"""

SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL = """
    SELECT
        c.identity AS identity,
        c.source_identity AS source_identity,
        c.source_json AS source_json,
        c.created_at AS call_created_at,
        e.final_step AS step_number,
        e.result_key AS result_key,
        s.content AS content,
        s.raw_json AS raw_json,
        s.created_at AS step_created_at,
        e.created_at AS export_created_at,
        e.exported_at AS exported_at,
        e.export_message AS export_message
    FROM calls AS c
    JOIN exports AS e
        ON e.identity = c.identity
    JOIN steps AS s
        ON s.identity = e.identity
       AND s.step_number = e.final_step
    WHERE c.identity = ?
"""


__all__ = [
    "CALL_COLUMNS",
    "STEP_COLUMNS",
    "EXPORT_COLUMNS",
    "INSERT_CALL_SQL",
    "INSERT_STEP_SQL",
    "INSERT_EXPORT_SQL",
    "CONFIRM_EXPORT_SQL",
    "SELECT_CALL_SQL",
    "SELECT_CALL_BY_SOURCE_IDENTITY_SQL",
    "SELECT_CALLS_SQL",
    "SELECT_STEP_BY_IDENTITY_NUMBER_SQL",
    "SELECT_STEPS_FOR_IDENTITY_SQL",
    "SELECT_EXPORT_BY_IDENTITY_SQL",
    "SELECT_PENDING_EXPORTS_SQL",
    "SELECT_PENDING_EXPORT_BY_SOURCE_IDENTITY_SQL",
    "SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL",
]
