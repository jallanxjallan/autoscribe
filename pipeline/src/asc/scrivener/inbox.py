"""Public inbox for ledger-owned Redis artifact keys."""
from asc.models.process.result import SUCCESS_RESULT_KINDS
from asc.redis.key import RedisKey
from asc.state.queue import RedisQueue

SCRIVENER_INBOX_KEY = "control:scrivener:inbox"
scrivener_inbox = RedisQueue(SCRIVENER_INBOX_KEY)
ACCEPTED_KINDS = frozenset({"call", *SUCCESS_RESULT_KINDS})

def _message_key(claimed):
    if claimed is None: return None
    return str(getattr(claimed,"key",getattr(claimed,"identity",claimed)))

def post(key):
    raw=str(key).strip()
    if not raw: raise ValueError("scrivener inbox expects a non-empty key")
    parsed=RedisKey(raw)
    if parsed.kind not in ACCEPTED_KINDS:
        raise ValueError(f"scrivener inbox accepts call/result keys, got: {raw}")
    scrivener_inbox.insert(raw); return raw

def daemon_claim(*,timeout=0,empty_limit=None): return _message_key(scrivener_inbox.daemon_claim(timeout=timeout,empty_limit=empty_limit))
def block_claim(*,timeout=0): return _message_key(scrivener_inbox.block_claim(timeout=timeout))
def claim(): return _message_key(scrivener_inbox.claim())
def count(): return scrivener_inbox.count()
def clear(): return scrivener_inbox.clear()
