from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LanguagePack
from app.services.pack_store import list_available_codes, pack_file_path, pack_metadata

router = APIRouter(prefix="/languages", tags=["languages"])


@router.get("/list")
def list_languages(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(LanguagePack).where(LanguagePack.active.is_(True))).all()
    if not rows:
        # Fallback when DB empty — read from disk
        return {
            "languages": [pack_metadata(code) for code in list_available_codes()],
        }
    return {
        "languages": [
            {
                "code": r.code,
                "version": r.version,
                "download_url": r.download_url,
                "size_bytes": r.size_bytes,
            }
            for r in rows
        ]
    }


@router.get("/{code}/download")
def download_info(code: str, db: Session = Depends(get_db)) -> dict:
    row = db.scalar(select(LanguagePack).where(LanguagePack.code == code.lower()))
    if row:
        return {
            "code": row.code,
            "version": row.version,
            "download_url": row.download_url,
            "size_bytes": row.size_bytes,
        }
    meta = pack_metadata(code)
    if not meta:
        raise HTTPException(404, "Language pack not found")
    return meta


@router.get("/{code}/file")
def download_file(code: str) -> FileResponse:
    path = pack_file_path(code.lower())
    if not path:
        raise HTTPException(404, "Pack file not found on server")
    media = "application/zip" if path.suffix.lower() == ".zip" else "application/json"
    return FileResponse(
        path,
        media_type=media,
        filename=f"{code.lower()}_{path.name}",
    )
