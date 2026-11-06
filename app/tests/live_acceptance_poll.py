"""Live-test polling only: response publication is distinct from processing success."""
import re
import time


def wait_for_terminal_response(fetch_status, *, timeout=35, interval=.2,
                               monotonic=time.monotonic, sleep=time.sleep):
    """Return a delivery receipt, never an assertion of processing success.

    fetch_status receives its remaining timeout budget. It must only fetch status,
    not submit or execute. A failed execution can briefly precede publication of
    its terminal failed response. The caller must retrieve/validate that response
    and inspect its own status/failure fields independently.
    """
    if timeout <= 0 or interval <= 0:
        raise ValueError('poll timeout and interval must be positive')
    deadline = monotonic() + timeout
    last_state = None
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError(f'terminal response was not published; last state={last_state!r}')
        receipt = fetch_status(remaining)
        last_state = receipt.get('state')
        if monotonic() > deadline:
            raise TimeoutError('status fetch exceeded response-publication timeout')
        if last_state == 'completed':
            checksum = receipt.get('response_sha256')
            if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
                raise ValueError('completed delivery receipt lacks a valid response checksum')
            return receipt
        if last_state not in ('accepted', 'running', 'failed'):
            raise ValueError(f'unexpected response-publication state: {last_state!r}')
        remaining = deadline - monotonic()
        if remaining > 0:
            sleep(min(interval, remaining))
