"""Redis worker ownership. Pending membership is retained until resolution."""
import uuid

from .redis_runtime import WORKER_QUEUE_KEY, RedisClient

_ACQUIRE = """
local now = tonumber(redis.call('TIME')[1])
local state = redis.call('HGET', KEYS[1], 'state')
if state == 'done' or state == 'uncertain' then
    redis.call('ZREM', KEYS[2], ARGV[1])
    return ''
end
if state and tonumber(redis.call('HGET', KEYS[1], 'deadline')) > now then
    return ''
end
if state == 'running' then
    redis.call('HSET', KEYS[1], 'state', 'uncertain', 'updated_at', now,
               'error', 'Worker lease expired after execution intent')
    redis.call('ZREM', KEYS[2], ARGV[1])
    return 'uncertain'
end
if not redis.call('ZSCORE', KEYS[2], ARGV[1]) then return '' end
if not state then
    local call = redis.call('HGET', ARGV[1], 'call_id')
    if not call then return redis.error_reply('Pending task has no call identity') end
    state = 'claimed'
    redis.call('HSET', KEYS[1], 'call_id', call, 'created_at', now)
end
redis.call('HSET', KEYS[1], 'state', state, 'owner', ARGV[2],
           'deadline', now + tonumber(ARGV[3]), 'updated_at', now)
return state
"""

_TRANSITION = """
local now = tonumber(redis.call('TIME')[1])
if redis.call('HGET', KEYS[1], 'owner') ~= ARGV[2]
   or redis.call('HGET', KEYS[1], 'state') ~= ARGV[3]
   or tonumber(redis.call('HGET', KEYS[1], 'deadline')) <= now then
    return 0
end
if ARGV[4] == 'result' then
    redis.call('HSET', KEYS[3], unpack(ARGV, 7))
    redis.call('EXPIRE', KEYS[3], ARGV[6])
end
redis.call('HSET', KEYS[1], 'state', ARGV[4], 'error', ARGV[5], 'updated_at', now)
if ARGV[4] == 'done' or ARGV[4] == 'uncertain' then
    redis.call('ZREM', KEYS[2], ARGV[1])
end
return 1
"""


class Claim:
    def __init__(self, client: RedisClient, task_key: str):
        self.client = client
        self.task_key = task_key
        self.key = f"claim:{task_key}"
        self.owner = uuid.uuid4().hex

    def acquire(self, lease: int) -> str:
        return self.client.command("EVAL", _ACQUIRE, 2, self.key, WORKER_QUEUE_KEY,
                                   self.task_key, self.owner, lease)

    def transition(self, previous: str, state: str, *, error: str = "",
                   result_key: str = "", ttl: int = 0, fields: dict | None = None) -> bool:
        values = [value for pair in (fields or {}).items() for value in pair]
        return bool(self.client.command(
            "EVAL", _TRANSITION, 3, self.key, WORKER_QUEUE_KEY, result_key,
            self.task_key, self.owner, previous, state, error, ttl, *values,
        ))
