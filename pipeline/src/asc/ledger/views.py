from __future__ import annotations


PENDING_RESULT_EXPORTS_VIEW = "pending_result_exports"


CREATE_PENDING_RESULT_EXPORTS_VIEW_SQL = f"""
    CREATE VIEW IF NOT EXISTS {PENDING_RESULT_EXPORTS_VIEW} AS
    SELECT
        json_extract(c.raw_json, '$.identifier') AS prompt_slug,
        c.call AS call_identity,
        r.result AS result_identity
    FROM calls AS c
    JOIN results AS r
        ON r.call = c.call
    WHERE NOT EXISTS (
        SELECT 1
        FROM exports AS x
        WHERE x.result = r.result
    )
"""


SELECT_PENDING_RESULT_EXPORTS_SQL = f"""
    SELECT
        prompt_slug,
        call_identity,
        result_identity
    FROM {PENDING_RESULT_EXPORTS_VIEW}
    ORDER BY prompt_slug ASC, call_identity ASC
"""


SELECT_DUPLICATE_PENDING_EXPORT_SLUGS_SQL = f"""
    SELECT
        prompt_slug,
        COUNT(*) AS pending_count
    FROM {PENDING_RESULT_EXPORTS_VIEW}
    GROUP BY prompt_slug
    HAVING COUNT(*) > 1
    ORDER BY prompt_slug ASC
"""


SELECT_DUPLICATE_PENDING_EXPORT_ROWS_SQL = f"""
    SELECT
        p.prompt_slug,
        p.call_identity,
        p.result_identity
    FROM {PENDING_RESULT_EXPORTS_VIEW} AS p
    JOIN (
        SELECT prompt_slug
        FROM {PENDING_RESULT_EXPORTS_VIEW}
        GROUP BY prompt_slug
        HAVING COUNT(*) > 1
    ) AS duplicated
        ON duplicated.prompt_slug = p.prompt_slug
    ORDER BY p.prompt_slug ASC, p.call_identity ASC
"""


LEDGER_VIEW_NAMES = (
    PENDING_RESULT_EXPORTS_VIEW,
)

CREATE_LEDGER_VIEWS_SQL = (
    CREATE_PENDING_RESULT_EXPORTS_VIEW_SQL,
)


__all__ = [
    "PENDING_RESULT_EXPORTS_VIEW",
    "CREATE_PENDING_RESULT_EXPORTS_VIEW_SQL",
    "CREATE_LEDGER_VIEWS_SQL",
    "LEDGER_VIEW_NAMES",
    "SELECT_PENDING_RESULT_EXPORTS_SQL",
    "SELECT_DUPLICATE_PENDING_EXPORT_SLUGS_SQL",
    "SELECT_DUPLICATE_PENDING_EXPORT_ROWS_SQL",
]
