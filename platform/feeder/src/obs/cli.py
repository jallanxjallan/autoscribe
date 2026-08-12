from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from . import git
from .errors import ObsError
from .instruction_upload import upload_instruction
from .ipc import handle as handle_ipc
from .logging import read_log, summarize_items, write_log
from .retrieval import retrieve_results
from .state import VaultState
from .transport import dispatch_run
from .uploads import upload_instructions
from .vault import Vault


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="obs")
    root.add_argument("--vault", type=Path, help="target vault/repository; defaults to current git root")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("state")
    sub.add_parser("ipc")
    scan = sub.add_parser("scan")
    scan.add_argument("--public", action="store_true")
    command = sub.add_parser("upload-instructions")
    command.add_argument("-n", "--dry-run", action="store_true")
    command.add_argument("-f", "--force", action="store_true")
    one = sub.add_parser("upload-instruction")
    one.add_argument("source_path")
    one.add_argument("--input", required=True, type=Path)
    one.add_argument("--metadata", type=Path)
    one.add_argument("--force", action="store_true")
    one.add_argument("--no-commit", action="store_true")
    dispatch = sub.add_parser("dispatch-run")
    dispatch.add_argument("-n", "--dry-run", action="store_true")
    dispatch.add_argument("--branch")
    retrieve = sub.add_parser("retrieve-results")
    retrieve.add_argument("-n", "--dry-run", action="store_true")
    retrieve.add_argument("--branch")
    retrieve.add_argument("-f", "--force", action="store_true")
    log = sub.add_parser("log")
    log.add_argument("--date", help="local date in YYYY-MM-DD form; defaults to today")
    log.add_argument("-n", "--lines", type=int, default=200, help="number of trailing lines to print; 0 prints all")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repo: Path | None = None
    command = getattr(args, "command", "obs")
    try:
        repo = args.vault.resolve() if args.vault else git.root(Path.cwd())
        if command == "log":
            sys.stdout.write(read_log(repo, date=args.date, lines=args.lines))
        elif command == "ipc":
            request = json.load(sys.stdin)
            print(json.dumps(handle_ipc(request, repo=repo), ensure_ascii=False))
        elif command == "state":
            current = VaultState.for_vault(repo)
            print(json.dumps({"vault_root": str(repo), "state_root": str(current.root)}, indent=2))
        elif command == "scan":
            records = Vault(repo).records(public_only=args.public)
            print(json.dumps([record.__dict__ for record in records], indent=2, ensure_ascii=False))
        elif command == "upload-instructions":
            write_log(repo, command, "started")
            items, output = upload_instructions(repo, force=args.force, dry_run=args.dry_run)
            _report(command, items, args.dry_run)
            if output:
                sys.stdout.write(output)
            write_log(repo, command, f"completed: {len(items)} record(s)\n{summarize_items(items)}")
        elif command == "upload-instruction":
            write_log(repo, command, f"started: {args.source_path}")
            result = upload_instruction(repo, source_path=args.source_path, input_path=args.input, metadata_path=args.metadata, force=args.force, commit=not args.no_commit)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            write_log(repo, command, f"completed: {args.source_path}")
        elif command == "dispatch-run":
            write_log(repo, command, f"started: branch={args.branch or 'auto'}")
            items, output = dispatch_run(repo, branch=args.branch, dry_run=args.dry_run)
            _report(command, items, args.dry_run)
            if output:
                sys.stdout.write(output + ("\n" if not output.endswith("\n") else ""))
            write_log(repo, command, f"completed: {len(items)} record(s)\n{summarize_items(items)}")
        elif command == "retrieve-results":
            write_log(repo, command, f"started: branch={args.branch or 'all'} force={args.force}")
            result = retrieve_results(repo, branch=args.branch, dry_run=args.dry_run, force=args.force)
            _report_retrieval(result, args.dry_run)
            downloaded = result.get("downloaded", [])
            missing = result.get("missing", [])
            already = result.get("already_downloaded", [])
            detail = summarize_items([*downloaded, *missing])
            summary = f"completed: {len(downloaded)} downloaded, {len(missing)} missing, {len(already)} already resolved"
            write_log(repo, command, summary + (f"\n{detail}" if detail else ""))
        return 0
    except (ObsError, OSError, ValueError, json.JSONDecodeError) as exc:
        if command == "ipc":
            print(json.dumps({"ok": False, "error": str(exc), "error_type": type(exc).__name__}, ensure_ascii=False))
            return 0
        if repo is not None:
            try:
                write_log(repo, command, f"{type(exc).__name__}: {exc}", level="ERROR")
            except OSError:
                pass
        print(f"obs: ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if command == "ipc":
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}", "error_type": type(exc).__name__}, ensure_ascii=False))
            return 0
        if repo is not None:
            try:
                write_log(repo, command, f"{type(exc).__name__}: {exc}", level="ERROR")
            except OSError:
                pass
        raise


def _report(command: str, items: list[dict], dry_run: bool) -> None:
    suffix = " (dry run)" if dry_run else ""
    print(f"{command}: {len(items)} record(s){suffix}", file=sys.stderr)
    for item in items:
        slug = item.get("record_identity") or item.get("slug") or item.get("prompt_slug") or "?"
        path = item.get("source_path") or item.get("path") or ""
        print(f"  {slug}  {path}", file=sys.stderr)


def _report_retrieval(result: dict[str, list[dict]], dry_run: bool) -> None:
    suffix = " (dry run)" if dry_run else ""
    downloaded = result.get("downloaded", [])
    missing = result.get("missing", [])
    already = result.get("already_downloaded", [])

    print(f"retrieve-results: {len(downloaded)} downloaded, {len(missing)} missing{suffix}")
    for item in downloaded:
        slug = item.get("record_identity") or "?"
        path = item.get("source_path") or ""
        print(f"  downloaded  {slug}  {path}")
    for item in missing:
        slug = item.get("record_identity") or "?"
        path = item.get("source_path") or ""
        print(f"  missing     {slug}  {path}")


if __name__ == "__main__":
    raise SystemExit(main())
