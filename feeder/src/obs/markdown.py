from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml


@dataclass(frozen=True)
class MarkdownDocument:
    frontmatter: dict[str, Any]
    body: str
    has_frontmatter: bool


def parse_markdown(text: str) -> MarkdownDocument:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return MarkdownDocument({}, normalized, False)
    end = normalized.find("\n---\n", 4)
    if end < 0:
        return MarkdownDocument({}, normalized, False)
    raw = normalized[4:end]
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    return MarkdownDocument(data, normalized[end + 5 :], True)


def render_markdown(frontmatter: dict[str, Any], body: str) -> str:
    rendered = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip()
    clean_body = body.replace("\r\n", "\n").lstrip("\n")
    if not clean_body.endswith("\n"):
        clean_body += "\n"
    return f"---\n{rendered}\n---\n{clean_body}"


def strip_frontmatter(text: str) -> str:
    document = parse_markdown(text)
    return document.body if document.has_frontmatter else text.replace("\r\n", "\n")


def slug_prefix(slug: str) -> str:
    match = re.match(r"^([A-Za-z0-9_-]+)[._]", slug.strip())
    return match.group(1).lower() if match else ""
