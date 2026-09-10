"""Build a pinned, provenance-preserving source pack from raw GitHub text files."""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any
from urllib.request import Request, urlopen

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_SOURCE_BYTES = 512_000


class SourcePackError(RuntimeError):
    pass


def canonical_sha256(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def validate_spec(spec: dict[str, Any]) -> None:
    required = {"id", "role", "repository", "commit", "path"}
    missing = required - set(spec)
    if missing:
        raise SourcePackError("Missing source fields: " + ", ".join(sorted(missing)))
    if spec["role"] not in {"material", "evidence", "knowhow", "reference"}:
        raise SourcePackError(f"Unsupported source role: {spec['role']!r}")
    if not REPO_RE.fullmatch(str(spec["repository"])):
        raise SourcePackError("Invalid GitHub repository name.")
    if not COMMIT_RE.fullmatch(str(spec["commit"])):
        raise SourcePackError("Source must be pinned to a 40-character Git commit SHA.")
    path = PurePosixPath(str(spec["path"]))
    if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
        raise SourcePackError("Invalid repository-relative source path.")
    start = spec.get("section_start")
    end = spec.get("section_end")
    if (start is None) != (end is None):
        raise SourcePackError("section_start and section_end must be provided together.")
    if start is not None and (not isinstance(start, str) or not isinstance(end, str) or not start or not end):
        raise SourcePackError("Section markers must be non-empty strings.")


def raw_url(spec: dict[str, Any]) -> str:
    validate_spec(spec)
    return (
        "https://raw.githubusercontent.com/"
        f"{spec['repository']}/{spec['commit']}/{PurePosixPath(spec['path']).as_posix()}"
    )


def fetch_text(url: str, *, timeout: int = 30, max_bytes: int = MAX_SOURCE_BYTES) -> str:
    if not url.startswith("https://raw.githubusercontent.com/"):
        raise SourcePackError("Only raw.githubusercontent.com is allowed by this resolver.")
    request = Request(url, headers={"User-Agent": "webinar-production-source-resolver/0.1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read(max_bytes + 1)
    except OSError as exc:
        raise SourcePackError(f"Source download failed: {url}: {exc}") from exc
    if len(data) > max_bytes:
        raise SourcePackError(f"Source exceeds {max_bytes} bytes: {url}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourcePackError(f"Source is not UTF-8 text: {url}") from exc


def extract_section(text: str, start: str | None, end: str | None) -> str:
    if start is None and end is None:
        return text
    assert start is not None and end is not None
    start_index = text.find(start)
    if start_index < 0:
        raise SourcePackError(f"Section start marker not found: {start!r}")
    end_index = text.find(end, start_index + len(start))
    if end_index < 0:
        raise SourcePackError(f"Section end marker not found after start: {end!r}")
    section = text[start_index:end_index].strip()
    if not section:
        raise SourcePackError("Extracted section is empty.")
    return section + "\n"


def resolve_source(spec: dict[str, Any]) -> dict[str, Any]:
    validate_spec(spec)
    url = raw_url(spec)
    full_text = fetch_text(url)
    selected = extract_section(full_text, spec.get("section_start"), spec.get("section_end"))
    return {
        "id": spec["id"],
        "role": spec["role"],
        "repository": spec["repository"],
        "commit": spec["commit"],
        "path": spec["path"],
        "section_start": spec.get("section_start"),
        "section_end": spec.get("section_end"),
        "url": url,
        "full_file_sha256": hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
        "selected_sha256": hashlib.sha256(selected.encode("utf-8")).hexdigest(),
        "content": selected,
    }


def build_source_pack(config: dict[str, Any]) -> dict[str, Any]:
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise SourcePackError("Configuration must contain a non-empty sources list.")
    resolved = [resolve_source(item) for item in sources]
    if not any(item["role"] == "material" for item in resolved):
        raise SourcePackError("At least one material source is required.")
    pack = {
        "schema_version": 1,
        "lesson_id": config.get("lesson_id"),
        "target_runtime": config.get("target_runtime"),
        "sources": resolved,
    }
    pack["source_pack_sha256"] = canonical_sha256(pack)
    return pack
