"""Obsolete worker outcome helpers.

Workers no longer write result keys into the results index. A worker writes only
the response/failure key and posts that key to the orchestrator inbox. The
orchestrator owns result-index insertion and step progression.
"""


__all__: list[str] = []
