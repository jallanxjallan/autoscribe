"""Fetch and verify a manifest-last Dropbox source collection."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

MANIFEST = "SHA256SUMS.json"
IDENTITY = re.compile(r"[a-zA-Z0-9_-]{1,128}")
DIGEST = re.compile(r"[a-f0-9]{64}")
def _safe_component(part):
    return (bool(part) and not part.startswith(".") and part.strip() == part
            and not any(c in "\\:" or ord(c) < 32 or 127 <= ord(c) <= 159 for c in part))


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _read(remote, limit):
    rclone = Path(os.environ["AUTOSCRIBE_RCLONE"])
    if not rclone.is_absolute() or not rclone.is_file():
        raise ValueError("Pinned AUTOSCRIBE_RCLONE executable required")
    result = subprocess.run(
        [str(rclone), "cat", remote, "--count", str(limit + 1),
         "--retries", "1", "--low-level-retries", "1"],
        check=True, capture_output=True, timeout=90,
    )
    if len(result.stdout) > limit:
        raise ValueError("Dropbox file exceeds declared size")
    return result.stdout


def retrieve(pipeline, identity, digest, remote, limit, *, read=_read):
    if (not IDENTITY.fullmatch(pipeline) or not IDENTITY.fullmatch(identity)
            or not DIGEST.fullmatch(digest)
            or remote != f"dropbox:ingest/{pipeline}/{identity}-{digest}/"):
        raise ValueError("Dropbox package location or identity mismatch")
    manifest = read(remote + MANIFEST, 65536)
    if _hash(manifest) != digest:
        raise ValueError("Dropbox manifest checksum mismatch")
    entries = json.loads(manifest)
    if not isinstance(entries, dict) or not 1 <= len(entries) <= 128:
        raise ValueError("Invalid Dropbox package manifest")
    names = set()
    total = 0
    for name, entry in entries.items():
        lower = name.lower()
        if (not all(_safe_component(part) for part in name.split("/"))
                or lower == MANIFEST.lower() or lower in names
                or not isinstance(entry, dict) or set(entry) != {"bytes", "sha256"}
                or type(entry["bytes"]) is not int or entry["bytes"] < 0
                or not DIGEST.fullmatch(entry["sha256"])):
            raise ValueError(f"Unsafe Dropbox manifest entry: {name}")
        names.add(lower)
        total += entry["bytes"]
    if total > limit or any(
        "/".join(name.split("/")[:i]) in names
        for name in names for i in range(1, len(name.split("/")))
    ):
        raise ValueError("Dropbox package exceeds limits or overlaps a file")
    files = {}
    for name, entry in entries.items():
        data = read(remote + name, entry["bytes"])
        if len(data) != entry["bytes"] or _hash(data) != entry["sha256"]:
            raise ValueError(f"Dropbox file checksum or length mismatch: {name}")
        files[name] = data
    return files
