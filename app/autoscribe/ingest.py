"""Raw frontmatter guards retained exclusively for existing-source writeback."""
from __future__ import annotations

import json
import re


class IngestError(RuntimeError):
    pass


def split_frontmatter(text: str) -> tuple[str | None, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None, text
    offset = len(lines[0])
    for line in lines[1:]:
        offset += len(line)
        if line.rstrip("\r\n") == "---":
            return text[:offset], text[offset:]
    raise IngestError("unterminated leading YAML frontmatter")


def _decode_slug_scalar(value: str) -> str:
    value = value.strip()
    if not value:
        raise IngestError("blank frontmatter slug")
    if value.startswith('"'):
        decoder = json.JSONDecoder()
        try:
            parsed, end = decoder.raw_decode(value)
        except json.JSONDecodeError as exc:
            raise IngestError("invalid double-quoted frontmatter slug") from exc
        if not isinstance(parsed, str):
            raise IngestError("frontmatter slug must be text")
        remainder = value[end:].strip()
        if remainder and not remainder.startswith("#"):
            raise IngestError("invalid text after frontmatter slug")
        return parsed
    if value.startswith("'"):
        out = []
        i = 1
        while i < len(value):
            if value[i] == "'":
                if i + 1 < len(value) and value[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                remainder = value[i + 1:].strip()
                if remainder and not remainder.startswith("#"):
                    raise IngestError("invalid text after frontmatter slug")
                return "".join(out)
            out.append(value[i])
            i += 1
        raise IngestError("unterminated single-quoted frontmatter slug")
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def frontmatter_slug(prefix: str) -> str:
    matches = []
    lines = prefix.splitlines()
    for line in lines[1:-1]:
        m = re.match(r"^slug\s*:\s*(.*)$", line)
        if m:
            matches.append(_decode_slug_scalar(m.group(1)))
    if len(matches) != 1:
        raise IngestError("source requires exactly one frontmatter slug")
    return matches[0]
