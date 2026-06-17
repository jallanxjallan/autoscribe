#!/usr/bin/env python3
"""Import every module in a package and report failures on stdout."""

from __future__ import annotations

import importlib
import pkgutil
import sys


def main() -> int:
    package_name = sys.argv[1] if len(sys.argv) > 1 else "asc"

    try:
        package = importlib.import_module(package_name)
    except Exception as exc:
        print(f"FAIL {package_name} {type(exc).__name__}: {exc}")
        return 1

    failed: list[tuple[str, str, str]] = []

    for module in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        name = module.name
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