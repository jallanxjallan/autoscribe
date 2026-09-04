from asc.ingest.handlers.content import ingest_content

HANDLERS = {
    "content": ingest_content,
}

__all__ = ["HANDLERS", "ingest_content"]
