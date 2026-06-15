"""Language pack files on disk — served via /languages/{code}/file."""

from __future__ import annotations

import json
import logging
import re
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import LanguagePack

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^v(\d+(?:\.\d+)*)$")


def packs_root() -> Path:
    return settings.packs_dir.resolve()


def _parse_version(stem: str) -> int:
    m = _VERSION_RE.match(stem)
    if not m:
        return 1
    return int(m.group(1).split(".")[0])


def pack_file_path(code: str, version: int | None = None) -> Path | None:
    lang_dir = packs_root() / code.lower()
    if not lang_dir.is_dir():
        return None
    if version is not None:
        for ext in (".zip", ".json"):
            candidate = lang_dir / f"v{version}{ext}"
            if candidate.is_file():
                return candidate
        return None
    for pattern in ("v*.zip", "v*.json"):
        files = sorted(lang_dir.glob(pattern), key=lambda p: _parse_version(p.stem), reverse=True)
        if files:
            return files[0]
    return None


def list_available_codes() -> list[str]:
    root = packs_root()
    if not root.is_dir():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and pack_file_path(p.name) is not None
    )


def pack_metadata(code: str) -> dict | None:
    path = pack_file_path(code)
    if not path:
        return None
    version = _parse_version(path.stem)
    size = path.stat().st_size
    url = f"{settings.public_base_url.rstrip('/')}/languages/{code.lower()}/file"
    return {
        "code": code.lower(),
        "version": version,
        "download_url": url,
        "size_bytes": size,
        "format": "zip" if path.suffix.lower() == ".zip" else "json",
    }


def sync_packs_to_db(db: Session) -> int:
    """Upsert language_packs rows from files on disk."""
    count = 0
    for code in list_available_codes():
        meta = pack_metadata(code)
        if not meta:
            continue
        row = db.scalar(select(LanguagePack).where(LanguagePack.code == meta["code"]))
        if row:
            row.version = meta["version"]
            row.download_url = meta["download_url"]
            row.size_bytes = meta["size_bytes"]
            row.active = True
        else:
            db.add(
                LanguagePack(
                    code=meta["code"],
                    version=meta["version"],
                    download_url=meta["download_url"],
                    size_bytes=meta["size_bytes"],
                    active=True,
                )
            )
        count += 1
    db.commit()
    logger.info("Synced %d language packs from %s", count, packs_root())
    return count


def validate_pack_file(path: Path) -> bool:
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
                return "dictionary.db" in names and "metadata.json" in names
        except (OSError, zipfile.BadZipFile):
            return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(data.get("languageCode")) and isinstance(data.get("entries"), dict)
    except (json.JSONDecodeError, OSError):
        return False
