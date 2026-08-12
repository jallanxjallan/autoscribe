from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import yaml

from .errors import ObsError
from .markdown import parse_markdown
from .process import run


@dataclass(frozen=True)
class VaultRecord:
    slug: str
    path: str
    frontmatter: dict


@dataclass(frozen=True)
class VaultScanError:
    path: str
    error_type: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "error_type": self.error_type,
            "message": self.message,
        }


@dataclass(frozen=True)
class VaultScan:
    records: list[VaultRecord]
    errors: list[VaultScanError]


class Vault:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        if not (self.root / ".obsidian").is_dir():
            raise ObsError(f"git root is not an Obsidian vault: {self.root}")
        if not (self.root / "_control").exists():
            raise ObsError(f"refusing to run without _control in vault root: {self.root}")

    def markdown_paths(self, *, public_only: bool = False) -> Iterator[Path]:
        args = [
            "rg", "--files", "--glob", "*.md",
            "--glob", "!.git/**", "--glob", "!.obsidian/**", "--glob", "!_control/**",
        ]
        result = run(args, cwd=self.root, check=False)
        if result.returncode not in {0, 1}:
            raise ObsError(f"rg file index failed: {(result.stderr or result.stdout).strip()}")
        for value in sorted(line for line in result.stdout.splitlines() if line.strip()):
            rel = Path(value)
            if public_only and any(part.startswith("_") for part in rel.parts[:-1]):
                continue
            yield self.root / rel

    def scan(self, *, public_only: bool = False) -> VaultScan:
        """Return valid records and captured per-file parse/read failures.

        This deliberately mirrors Rust's Result-style handling: one malformed
        Markdown file does not abort the entire vault scan.
        """
        records: list[VaultRecord] = []
        errors: list[VaultScanError] = []
        for path in self.markdown_paths(public_only=public_only):
            relative = path.relative_to(self.root).as_posix()
            try:
                document = parse_markdown(path.read_text(encoding="utf-8"))
                slug = str(document.frontmatter.get("slug") or "").strip()
                if slug:
                    records.append(VaultRecord(slug, relative, document.frontmatter))
            except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
                errors.append(VaultScanError(relative, type(exc).__name__, str(exc)))
        self._assert_unique(records)
        return VaultScan(records=records, errors=errors)

    def records(self, *, public_only: bool = False) -> list[VaultRecord]:
        return self.scan(public_only=public_only).records

    def slug_map(self, *, public_only: bool = False) -> dict[str, VaultRecord]:
        return {record.slug: record for record in self.records(public_only=public_only)}

    @staticmethod
    def _assert_unique(records: list[VaultRecord]) -> None:
        grouped: dict[str, list[str]] = {}
        for record in records:
            grouped.setdefault(record.slug, []).append(record.path)
        duplicates = {slug: paths for slug, paths in grouped.items() if len(paths) > 1}
        if duplicates:
            lines = ["duplicate vault slugs:"]
            for slug, paths in sorted(duplicates.items()):
                lines.append(f"  {slug}")
                lines.extend(f"    - {path}" for path in paths)
            raise ObsError("\n".join(lines))
