from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.grammar_store import (
    grammar_file_path,
    grammar_metadata,
    list_available_codes,
)

router = APIRouter(prefix="/grammar-books", tags=["grammar-books"])


@router.get("/list")
def list_grammar_books() -> dict:
    return {
        "books": [grammar_metadata(code) for code in list_available_codes()],
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
