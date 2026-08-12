"""Extract one leading file-scoped processing directive from Markdown content."""

from __future__ import annotations

import re
from dataclasses import dataclass

_DIRECTIVE_RE = re.compile(
    r"\A\ufeff?[ \t]*(?P<block>:::[ \t]+directive[ \t]*\r?\n"
    r"(?P<body>.*?)"
    r"\r?\n:::[ \t]*(?:\r?\n|\Z))",
    re.DOTALL | re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ExtractedDirective:
    content: str
    directive: str | None


def extract_leading_directive(content: str) -> ExtractedDirective:
    """Remove and return a leading ``::: directive`` fenced div.

    Only a directive at the beginning of the Markdown body is recognized. This
    avoids accidentally treating examples or quoted material later in a draft
    as processing instructions.
    """

    if not isinstance(content, str):
        raise TypeError("record_content must be a string")

    match = _DIRECTIVE_RE.match(content)
    if match is None:
        return ExtractedDirective(content=content, directive=None)

    directive = match.group("body").strip()
    remaining = content[match.end() :].lstrip("\r\n")
    return ExtractedDirective(
        content=remaining,
        directive=directive or None,
    )


__all__ = ["ExtractedDirective", "extract_leading_directive"]
