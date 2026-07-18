from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.services.grammar_store import (
    grammar_file_path,
    grammar_metadata,
    list_available_codes,
)
from app.services.teen_voice_store import (
    build_teen_voices_zip_bytes,
    list_voice_codes,
    teen_voice_metadata,
    teen_voices_zip_path,
)

router = APIRouter(prefix="/grammar-books", tags=["grammar-books"])


@router.get("/list")
def list_grammar_books() -> dict:
    return {
        "books": [grammar_metadata(code) for code in list_available_codes()],
    }


@router.get("/voices/list")
def list_teen_voice_packs() -> dict:
    return {
        "voices": [teen_voice_metadata(code) for code in list_voice_codes()],
    }


@router.get("/{code}/download")
def download_info(code: str) -> dict:
    meta = grammar_metadata(code.lower())
    if not meta:
        raise HTTPException(404, "Grammar book not found")
    return meta


@router.get("/{code}/file")
def download_file(code: str) -> FileResponse:
    path = grammar_file_path(code.lower())
    if not path:
        raise HTTPException(404, "Grammar book file not found on server")
    return FileResponse(
        path,
        media_type="application/json",
        filename=f"{code.lower()}_grammar_{path.name}",
    )


@router.get("/{code}/voices/download")
def voice_download_info(code: str) -> dict:
    meta = teen_voice_metadata(code.lower())
    if not meta:
        raise HTTPException(404, "Teen voice pack not found")
    return meta


@router.get("/{code}/voices/file")
def voice_download_file(code: str):
    code = code.lower()
    zip_path = teen_voices_zip_path(code)
    if zip_path is not None:
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"{code}_teen_voices.zip",
        )
    data = build_teen_voices_zip_bytes(code)
    if not data:
        raise HTTPException(404, "Teen voice pack file not found on server")
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{code}_teen_voices.zip"',
        },
    )
