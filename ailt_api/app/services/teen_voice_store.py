"""Teen voice packs live under grammar_books/{code}/teen-voices/ (same host tree as ebooks)."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path

from app.config import settings
from app.services.grammar_store import grammar_root

logger = logging.getLogger(__name__)


def teen_voices_dir(code: str) -> Path:
    return grammar_root() / code.lower() / "teen-voices"


def teen_voices_zip_path(code: str) -> Path | None:
    """Prefer a prebuilt zip next to the folder; else None (caller may zip folder)."""
    zipped = grammar_root() / code.lower() / "teen-voices.zip"
    return zipped if zipped.is_file() else None


def has_teen_voices(code: str) -> bool:
    zip_path = teen_voices_zip_path(code)
    if zip_path is not None:
        return True
    root = teen_voices_dir(code)
    if not root.is_dir():
        return False
    return (root / "manifest.json").is_file() or any(root.glob("*/voice.json"))


def list_voice_codes() -> list[str]:
    root = grammar_root()
    if not root.is_dir():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and has_teen_voices(p.name)
    )


def _manifest_version(code: str) -> int:
    root = teen_voices_dir(code)
    manifest = root / "manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            return int(data.get("version") or 1)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return 1
    zip_path = teen_voices_zip_path(code)
    if zip_path is not None:
        # File mtime as coarse version when only a zip is present
        return max(1, int(zip_path.stat().st_mtime) // 1000 % 1_000_000)
    return 1


def teen_voice_metadata(code: str) -> dict | None:
    code = code.lower()
    if not has_teen_voices(code):
        return None
    version = _manifest_version(code)
    zip_path = teen_voices_zip_path(code)
    size = zip_path.stat().st_size if zip_path else _folder_size(teen_voices_dir(code))
    url = f"{settings.public_base_url.rstrip('/')}/grammar-books/{code}/voices/file"
    return {
        "code": code,
        "version": version,
        "download_url": url,
        "size_bytes": size,
        "format": "zip",
        "kind": "teen-voices",
    }


def _folder_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def build_teen_voices_zip_bytes(code: str) -> bytes | None:
    """Return zip bytes from teen-voices.zip or by zipping the teen-voices/ folder."""
    code = code.lower()
    zip_path = teen_voices_zip_path(code)
    if zip_path is not None:
        return zip_path.read_bytes()

    root = teen_voices_dir(code)
    if not root.is_dir():
        return None

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            arc = path.relative_to(root).as_posix()
            zf.write(path, arcname=arc)
    data = buf.getvalue()
    return data if data else None
