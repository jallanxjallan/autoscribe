from __future__ import annotations

import json
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SHELL_EXECUTABLE = Path('/bin/zsh')


class DispatchError(RuntimeError):
    pass


def _validated_items(vault_root: Path, raw_items: Any) -> list[dict[str, str]]:
    if not isinstance(raw_items, list) or not raw_items:
        raise DispatchError('The current selection is empty.')

    root = vault_root.resolve()
    items: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw in raw_items:
        if not isinstance(raw, dict):
            raise DispatchError('Every selected item must be an object.')
        raw_path = str(raw.get('path') or '').strip()
        slug = str(raw.get('slug') or '').strip()
        if not raw_path:
            raise DispatchError('Every selected item must have a filepath.')
        if not slug:
            raise DispatchError(f'Selected file is missing a slug: {raw_path}')

        candidate = (root / raw_path).resolve()
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError as exc:
            raise DispatchError(f'Selected path is outside the vault: {raw_path}') from exc

        if relative not in seen:
            seen.add(relative)
            items.append({'path': relative, 'slug': slug})

    return items


def _run_zsh(vault_root: Path, command: str, *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    if not SHELL_EXECUTABLE.is_file():
        raise DispatchError(f'zsh executable not found: {SHELL_EXECUTABLE}')
    return subprocess.run(
        [str(SHELL_EXECUTABLE), '-lic', command],
        cwd=str(vault_root),
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _state_root(vault_root: Path) -> Path:
    command = f'obs --vault {shlex.quote(str(vault_root))} state'
    result = _run_zsh(vault_root, command)
    if result.returncode != 0:
        raise DispatchError((result.stderr or result.stdout or 'obs state failed').strip())
    try:
        payload = json.loads(result.stdout)
        state_root = Path(str(payload['state_root'])).expanduser()
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise DispatchError(f'obs state returned invalid JSON: {result.stdout.strip()}') from exc
    return state_root


def _write_ephemeral_manifest(
    vault_root: Path,
    items: list[dict[str, str]],
    plan_slug: str,
    commit_message: str,
) -> Path:
    manifest_path = _state_root(vault_root) / 'workflow' / 'runs' / 'current-run.json'
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone().isoformat()
    payload = {
        'type': 'run_dispatch_manifest',
        'version': 1,
        'label': commit_message,
        'slug': f'run.{plan_slug}',
        'created': now,
        'updated': now,
        'vault': {'name': vault_root.name, 'root': str(vault_root)},
        'plan': {'slug': plan_slug, 'label': plan_slug},
        'count': len(items),
        'items': [
            {'path': item['path'], 'prompt_slug': item['slug'], 'plan_slug': plan_slug}
            for item in items
        ],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest_path


def _run_dispatch_pipeline(vault_root: Path) -> subprocess.CompletedProcess[str]:
    pipeline = (
        'set -o pipefail; '
        f'obs --vault {shlex.quote(str(vault_root))} dispatch-run '
        '| xargs -0 -r -n 2 pandoc --defaults=upload_prompt --output=/dev/null '
        '| asc enqueue'
    )
    result = _run_zsh(vault_root, pipeline)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f'exit status {result.returncode}').strip()
        raise DispatchError(f'{pipeline}: {detail}')
    return result


def dispatch(vault_root: Path, request: dict[str, Any]) -> dict[str, Any]:
    plan_slug = str(request.get('plan_slug') or '').strip()
    if not plan_slug:
        raise DispatchError('Select an uploaded plan.')

    items = _validated_items(vault_root, request.get('items'))
    stamp = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')
    dispatch_label = f'{plan_slug} {stamp}'
    manifest_path = _write_ephemeral_manifest(vault_root, items, plan_slug, dispatch_label)

    try:
        result = _run_dispatch_pipeline(vault_root)
    finally:
        manifest_path.unlink(missing_ok=True)

    messages: list[str] = []
    if result.stdout.strip():
        messages.extend(line for line in result.stdout.splitlines() if line.strip())
    if result.stderr.strip():
        messages.extend(line for line in result.stderr.splitlines() if line.strip())

    return {
        'ok': True,
        'operation': 'dispatch',
        'plan_slug': plan_slug,
        'count': len(items),
        'messages': messages,
    }


def handle(request: dict[str, Any]) -> dict[str, Any]:
    operation = str(request.get('operation') or '').strip()
    vault_root = Path(str(request.get('vault_root') or '')).expanduser().resolve()
    if not vault_root.is_dir():
        raise DispatchError(f'Vault root is not a directory: {vault_root}')
    if operation == 'dispatch':
        return dispatch(vault_root, request)
    raise DispatchError(f'Unknown operation: {operation or "<empty>"}')


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise DispatchError('Request must be a JSON object.')
        print(json.dumps(handle(request), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
