from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .errors import ObsError
from .markdown import parse_markdown
from .process import run


@dataclass(frozen=True)
class VaultRecord:
    slug: str
    path: str
    frontmatter: dict


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

    def records(self, *, public_only: bool = False) -> list[VaultRecord]:
        records: list[VaultRecord] = []
        for path in self.markdown_paths(public_only=public_only):
            document = parse_markdown(path.read_text(encoding="utf-8"))
            slug = str(document.frontmatter.get("slug") or "").strip()
            if slug:
                records.append(
                    VaultRecord(slug, path.relative_to(self.root).as_posix(), document.frontmatter)
                )
        self._assert_unique(records)
        return records

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
