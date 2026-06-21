#!/usr/bin/env python3
"""Import modules in a package and report failures on stdout."""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import pkgutil
from collections.abc import Sequence


DEFAULT_PACKAGE = "asc"


def _split_patterns(values: Sequence[str]) -> list[str]:
    """Expand repeatable/comma-separated CLI pattern arguments."""

    patterns: list[str] = []
    for value in values:
        for pattern in value.split(","):
            text = pattern.strip()
            if text:
                patterns.append(text)
    return patterns


def _matches_any(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def _should_import(
    name: str,
    *,
    include_patterns: Sequence[str],
    exclude_patterns: Sequence[str],
) -> bool:
    if include_patterns and not _matches_any(name, include_patterns):
        return False
    if exclude_patterns and _matches_any(name, exclude_patterns):
        return False
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import modules in a package and report import failures.",
    )
    parser.add_argument(
        "package",
        nargs="?",
        default=DEFAULT_PACKAGE,
        help=f"Package to scan. Defaults to {DEFAULT_PACKAGE!r}.",
    )
    parser.add_argument(
        "-i",
        "--include",
        action="append",
        default=[],
        metavar="PATTERN",
        help=(
            "Only import modules whose full dotted name matches PATTERN. "
            "May be repeated or comma-separated. Example: --include 'asc.enqueuer*'"
        ),
    )
    parser.add_argument(
        "-x",
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help=(
            "Skip modules whose full dotted name matches PATTERN. "
            "May be repeated or comma-separated. Example: --exclude 'asc.export*'"
        ),
    )
    parser.add_argument(
        "--show-skipped",
        action="store_true",
        help="Print SKIP lines for modules ignored by include/exclude patterns.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    package_name = args.package
    include_patterns = _split_patterns(args.include)
    exclude_patterns = _split_patterns(args.exclude)

    try:
        package = importlib.import_module(package_name)
    except Exception as exc:
        print(f"FAIL {package_name} {type(exc).__name__}: {exc}")
        return 1

    if not hasattr(package, "__path__"):
        print(f"FAIL {package_name} ValueError: package has no __path__")
        return 1

    failed: list[tuple[str, str, str]] = []

    for module in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        name = module.name
        if not _should_import(
            name,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
        ):
            if args.show_skipped:
                print(f"SKIP {name}")
            continue

        try:
            importlib.import_module(name)
            print(f"OK {name}")
        except Exception as exc:
            failed.append((name, type(exc).__name__, str(exc)))
            print(f"FAIL {name} {type(exc).__name__}: {exc}")

    print("")
    print("FAILED")
    for name, error_type, message in failed:
        print(f"{name} {error_type}: {message}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
