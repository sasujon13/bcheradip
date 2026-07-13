"""Grammar ebook JSON files on disk — served via /grammar-books/{code}/file."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^v(\d+(?:\.\d+)*)$")


def grammar_root() -> Path:
    return settings.grammar_books_dir.resolve()


def _parse_version(stem: str) -> int:
    m = _VERSION_RE.match(stem)
    if not m:
        return 1
    return int(m.group(1).split(".")[0])


def grammar_file_path(code: str, version: int | None = None) -> Path | None:
    lang_dir = grammar_root() / code.lower()
    if not lang_dir.is_dir():
        return None
    if version is not None:
        candidate = lang_dir / f"v{version}.json"
        return candidate if candidate.is_file() else None
    files = sorted(lang_dir.glob("v*.json"), key=lambda p: _parse_version(p.stem), reverse=True)
    return files[0] if files else None


def list_available_codes() -> list[str]:
    root = grammar_root()
    if not root.is_dir():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and grammar_file_path(p.name) is not None
    )


def grammar_metadata(code: str) -> dict | None:
    path = grammar_file_path(code)
    if not path:
        return None
    version = _parse_version(path.stem)
    size = path.stat().st_size
    url = f"{settings.public_base_url.rstrip('/')}/grammar-books/{code.lower()}/file"
    return {
        "code": code.lower(),
        "version": version,
        "download_url": url,
        "size_bytes": size,
        "format": "json",
    }


def validate_grammar_file(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("chapters"), list):
            return False
        lang = str(data.get("languageCode") or data.get("language_code") or "").strip()
        return bool(lang) and len(data["chapters"]) >= 1
    except (json.JSONDecodeError, OSError, TypeError):
        return False
