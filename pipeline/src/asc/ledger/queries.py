from asc.ledger.util import insert_sql


CALL_COLUMNS = (
    "identity",
    "source_identity",
    "content",
    "created_at",
    "extra_json",
)

RESPONSE_COLUMNS = (
    "identity",
    "final_step",
    "result_key",
    "result_kind",
    "status",
    "content",
    "fail_message",
    "raw_json",
    "created_at",
)

EXPORT_COLUMNS = (
    "response_identity",
    "destination",
    "export_mode",
    "target_slug",
    "target_path",
    "exported_at",
    "export_message",
    "consumer_json",
    "created_at",
)

INSERT_CALL_SQL = insert_sql("calls", CALL_COLUMNS)
INSERT_RESPONSE_SQL = insert_sql("responses", RESPONSE_COLUMNS)
INSERT_EXPORT_SQL = insert_sql("exports", EXPORT_COLUMNS)

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

SELECT_RESPONSE_SQL = f"""
    SELECT {", ".join(RESPONSE_COLUMNS)}
    FROM responses
    WHERE identity = ?
"""

SELECT_RESPONSES_SQL = f"""
    SELECT {", ".join(RESPONSE_COLUMNS)}
    FROM responses
    ORDER BY created_at ASC
"""

SELECT_EXPORT_BY_ID_SQL = """
    SELECT
        export_id,
        response_identity,
        destination,
        export_mode,
        target_slug,
        target_path,
        exported_at,
        export_message,
        consumer_json,
        created_at
    FROM exports
    WHERE export_id = ?
"""

SELECT_EXPORTS_FOR_RESPONSE_SQL = """
    SELECT
        export_id,
        response_identity,
        destination,
        export_mode,
        target_slug,
        target_path,
        exported_at,
        export_message,
        consumer_json,
        created_at
    FROM exports
    WHERE response_identity = ?
    ORDER BY exported_at ASC, export_id ASC
"""

SELECT_PENDING_EXPORTS_SQL = """
    SELECT
        c.source_identity AS record_identity,
        r.identity AS call_identity,
        r.final_step AS final_step,
        r.result_key AS result_key,
        r.content AS content,
        r.raw_json AS raw_json,
        r.created_at AS created_at
    FROM responses AS r
    JOIN calls AS c
        ON c.identity = r.identity
    LEFT JOIN exports AS e
        ON e.response_identity = r.identity
    WHERE r.status = 'success'
      AND e.response_identity IS NULL
    ORDER BY c.source_identity ASC, r.identity ASC
"""

SELECT_PENDING_EXPORT_BY_SOURCE_IDENTITY_SQL = """
    SELECT
        c.source_identity AS record_identity,
        r.identity AS call_identity,
        r.final_step AS final_step,
        r.result_key AS result_key,
        r.content AS content,
        r.raw_json AS raw_json,
        r.created_at AS created_at
    FROM responses AS r
    JOIN calls AS c
        ON c.identity = r.identity
    LEFT JOIN exports AS e
        ON e.response_identity = r.identity
    WHERE r.status = 'success'
      AND e.response_identity IS NULL
      AND c.source_identity = ?
    ORDER BY r.created_at ASC, r.identity ASC
    LIMIT 1
"""

SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL = """
    SELECT
        c.identity AS identity,
        c.source_identity AS source_identity,
        c.content AS source_content,
        c.extra_json AS extra_json,
        c.created_at AS call_created_at,
        r.final_step AS step_number,
        r.result_key AS result_key,
        r.content AS content,
        r.raw_json AS raw_json,
        r.created_at AS step_created_at,
        e.created_at AS export_created_at,
        e.exported_at AS exported_at,
        e.export_message AS export_message
    FROM calls AS c
    JOIN responses AS r
        ON r.identity = c.identity
    LEFT JOIN exports AS e
        ON e.response_identity = r.identity
    WHERE c.identity = ?
    ORDER BY e.exported_at DESC, e.export_id DESC
    LIMIT 1
"""

__all__ = [
    "CALL_COLUMNS",
    "RESPONSE_COLUMNS",
    "EXPORT_COLUMNS",
    "INSERT_CALL_SQL",
    "INSERT_RESPONSE_SQL",
    "INSERT_EXPORT_SQL",
    "SELECT_CALL_SQL",
    "SELECT_CALL_BY_SOURCE_IDENTITY_SQL",
    "SELECT_CALLS_SQL",
    "SELECT_RESPONSE_SQL",
    "SELECT_RESPONSES_SQL",
    "SELECT_EXPORT_BY_ID_SQL",
    "SELECT_EXPORTS_FOR_RESPONSE_SQL",
    "SELECT_PENDING_EXPORTS_SQL",
    "SELECT_PENDING_EXPORT_BY_SOURCE_IDENTITY_SQL",
    "SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL",
]
