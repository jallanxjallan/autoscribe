from asc.ingest.handlers.content import ingest_content
from asc.ingest.handlers.instructions import ingest_instruction
from asc.ingest.handlers.plan import ingest_plan

HANDLERS = {
    "content": ingest_content,
    "instruction": ingest_instruction,
    "plan": ingest_plan,
}

__all__ = ["HANDLERS", "ingest_content", "ingest_instruction", "ingest_plan"]
