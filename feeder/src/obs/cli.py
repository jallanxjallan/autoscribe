from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import git
from .downloads import writeback, writenew
from .errors import ObsError
from .state import VaultState
from .uploads import dispatch_run, upload_instructions
from .instruction_upload import upload_instruction
from .vault import Vault


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="obs")
    root.add_argument("--vault", type=Path, help="target vault/repository; defaults to current git root")
    sub = root.add_subparsers(dest="command", required=True)
    state = sub.add_parser("state")
    scan = sub.add_parser("scan")
    scan.add_argument("--public", action="store_true")
    for name in ("upload-instructions",):
        command = sub.add_parser(name)
        command.add_argument("-n", "--dry-run", action="store_true")
        command.add_argument("-f", "--force", action="store_true")
    one = sub.add_parser("upload-instruction")
    one.add_argument("source_path")
    one.add_argument("--input", required=True, type=Path)
    one.add_argument("--metadata", type=Path)
    one.add_argument("--force", action="store_true")
    one.add_argument("--no-commit", action="store_true")
    sub.add_parser("ipc")
    dispatch = sub.add_parser("dispatch-run")
    dispatch.add_argument("-n", "--dry-run", action="store_true")
    dispatch.add_argument("--manifest", type=Path)
    back = sub.add_parser("writeback")
    back.add_argument("-n", "--dry-run", action="store_true")
    back.add_argument("--limit", type=int)
    new = sub.add_parser("writenew")
    new.add_argument("target_dir", nargs="?", default="new")
    new.add_argument("-n", "--dry-run", action="store_true")
    new.add_argument("--limit", type=int)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        repo = args.vault.resolve() if args.vault else git.root(Path.cwd())
        if args.command == "state":
            current = VaultState.for_vault(repo)
            print(json.dumps({"vault_root": str(repo), "state_root": str(current.root)}, indent=2))
        elif args.command == "scan":
            records = Vault(repo).records(public_only=args.public)
            print(json.dumps([record.__dict__ for record in records], indent=2, ensure_ascii=False))
        elif args.command == "upload-instructions":
            items, output = upload_instructions(repo, force=args.force, dry_run=args.dry_run)
            _report(args.command, items, args.dry_run)
            if output:
                sys.stdout.write(output)
        elif args.command == "upload-instruction":
            result = upload_instruction(repo, source_path=args.source_path, input_path=args.input, metadata_path=args.metadata, force=args.force, commit=not args.no_commit)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.command == "ipc":
            from .ipc import main as ipc_main
            return ipc_main()
        elif args.command == "dispatch-run":
            items, output = dispatch_run(repo, manifest_path=args.manifest, dry_run=args.dry_run)
            _report(args.command, items, args.dry_run)
            if output:
                sys.stdout.buffer.write(output)
                sys.stdout.buffer.flush()
        elif args.command == "writeback":
            items = writeback(repo, dry_run=args.dry_run, limit=args.limit)
            _report(args.command, items, args.dry_run)
        elif args.command == "writenew":
            items = writenew(repo, target_dir=args.target_dir, dry_run=args.dry_run, limit=args.limit)
            _report(args.command, items, args.dry_run)
        return 0
    except (ObsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"obs: ERROR: {exc}", file=sys.stderr)
        return 1


def _report(command: str, items: list[dict], dry_run: bool) -> None:
    suffix = " (dry run)" if dry_run else ""
    print(f"{command}: {len(items)} record(s){suffix}", file=sys.stderr)
    for item in items:
        slug = item.get("slug") or item.get("prompt_slug") or item.get("call_slug") or "?"
        path = item.get("path") or ""
        print(f"  {slug}  {path}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
