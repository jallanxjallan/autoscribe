PENDING_EXPORTS_VIEW = "pending_exports"


CREATE_PENDING_EXPORTS_VIEW_SQL = f"""
    CREATE VIEW IF NOT EXISTS {PENDING_EXPORTS_VIEW} AS
    SELECT
        e.source_identity AS record_identity,
        e.identity AS call_identity,
        e.final_step AS final_step,
        e.result_key AS result_key,
        s.content AS content,
        s.raw_json AS raw_json,
        e.created_at AS created_at
    FROM exports AS e
    JOIN steps AS s
        ON s.identity = e.identity
       AND s.step_number = e.final_step
    WHERE e.exported_at IS NULL
"""


SELECT_PENDING_EXPORTS_SQL = f"""
    SELECT
        record_identity,
        call_identity,
        final_step,
        result_key,
        content,
        raw_json,
        created_at
    FROM {PENDING_EXPORTS_VIEW}
    ORDER BY record_identity ASC, call_identity ASC
"""


SELECT_DUPLICATE_PENDING_EXPORT_SLUGS_SQL = f"""
    SELECT
        record_identity,
        COUNT(*) AS pending_count
    FROM {PENDING_EXPORTS_VIEW}
    GROUP BY record_identity
    HAVING COUNT(*) > 1
    ORDER BY record_identity ASC
"""


SELECT_DUPLICATE_PENDING_EXPORT_ROWS_SQL = f"""
    SELECT
        p.record_identity,
        p.call_identity,
        p.final_step,
        p.result_key
    FROM {PENDING_EXPORTS_VIEW} AS p
    JOIN (
        SELECT record_identity
        FROM {PENDING_EXPORTS_VIEW}
        GROUP BY record_identity
        HAVING COUNT(*) > 1
    ) AS duplicated
        ON duplicated.record_identity = p.record_identity
    ORDER BY p.record_identity ASC, p.call_identity ASC
"""


LEDGER_VIEW_NAMES = (PENDING_EXPORTS_VIEW,)
CREATE_LEDGER_VIEWS_SQL = (CREATE_PENDING_EXPORTS_VIEW_SQL,)


__all__ = [
    "PENDING_EXPORTS_VIEW",
    "CREATE_PENDING_EXPORTS_VIEW_SQL",
    "CREATE_LEDGER_VIEWS_SQL",
    "LEDGER_VIEW_NAMES",
    "SELECT_PENDING_EXPORTS_SQL",
    "SELECT_DUPLICATE_PENDING_EXPORT_SLUGS_SQL",
    "SELECT_DUPLICATE_PENDING_EXPORT_ROWS_SQL",
]
