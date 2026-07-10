"""Lightweight project metadata sync for the Cheradip VS Code extension.

Stores only path aliases and a small project.md excerpt — never file trees or
source. Rows are capped at ~48 KB so 100 users stay well under 1 MB total for
typical usage (not GB). Sync is on-demand from the extension, not mysqldump.
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_ext_user
from app.ext_database import get_ext_db
from app.models import ExtProjectKnowledge, ExtUser
from app.schemas import (
    ExtProjectKnowledgeListItem,
    ExtProjectKnowledgeResponse,
    ExtProjectKnowledgeUpsert,
)

router = APIRouter(prefix="/ext/project-knowledge", tags=["ext-project-knowledge"])

_MAX_PAYLOAD_BYTES = 48_000
_MAX_ALIASES = 200


def _json_size(obj: object) -> int:
    return len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def _row_to_response(row: ExtProjectKnowledge) -> ExtProjectKnowledgeResponse:
    aliases: dict[str, str] = {}
    summary: dict = {}
    try:
        if row.path_aliases_json:
            aliases = json.loads(row.path_aliases_json)
    except json.JSONDecodeError:
        pass
    try:
        if row.summary_json:
            summary = json.loads(row.summary_json)
    except json.JSONDecodeError:
        pass
    return ExtProjectKnowledgeResponse(
        project_hash=row.project_hash,
        project_name=row.project_name or "",
        path_aliases=aliases if isinstance(aliases, dict) else {},
        summary=summary if isinstance(summary, dict) else {},
        project_md_excerpt=row.project_md_excerpt or "",
        updated_at_ms=int(row.updated_at_ms or 0),
    )


@router.get("", response_model=list[ExtProjectKnowledgeListItem])
def list_projects(
    user: ExtUser = Depends(get_current_ext_user),
    db: Session = Depends(get_ext_db),
) -> list[ExtProjectKnowledgeListItem]:
    rows = db.scalars(
        select(ExtProjectKnowledge)
        .where(ExtProjectKnowledge.user_id == user.id)
        .order_by(ExtProjectKnowledge.updated_at_ms.desc())
        .limit(50)
    ).all()
    return [
        ExtProjectKnowledgeListItem(
            project_hash=r.project_hash,
            project_name=r.project_name or "",
            updated_at_ms=int(r.updated_at_ms or 0),
        )
        for r in rows
    ]


@router.get("/{project_hash}", response_model=ExtProjectKnowledgeResponse)
def get_project(
    project_hash: str,
    user: ExtUser = Depends(get_current_ext_user),
    db: Session = Depends(get_ext_db),
) -> ExtProjectKnowledgeResponse:
    row = db.scalar(
        select(ExtProjectKnowledge).where(
            ExtProjectKnowledge.user_id == user.id,
            ExtProjectKnowledge.project_hash == project_hash,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Project knowledge not found")
    return _row_to_response(row)


@router.put("", response_model=ExtProjectKnowledgeResponse)
def upsert_project(
    body: ExtProjectKnowledgeUpsert,
    user: ExtUser = Depends(get_current_ext_user),
    db: Session = Depends(get_ext_db),
) -> ExtProjectKnowledgeResponse:
    if len(body.path_aliases) > _MAX_ALIASES:
        raise HTTPException(status_code=413, detail=f"Too many path aliases (max {_MAX_ALIASES})")

    payload = {
        "path_aliases": body.path_aliases,
        "summary": body.summary,
        "project_md_excerpt": body.project_md_excerpt,
    }
    if _json_size(payload) > _MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Project knowledge payload too large")

    now_ms = int(time.time() * 1000)
    updated_ms = body.updated_at_ms or now_ms

    row = db.scalar(
        select(ExtProjectKnowledge).where(
            ExtProjectKnowledge.user_id == user.id,
            ExtProjectKnowledge.project_hash == body.project_hash,
        )
    )
    aliases_json = json.dumps(body.path_aliases, ensure_ascii=False)
    summary_json = json.dumps(body.summary, ensure_ascii=False)
    excerpt = (body.project_md_excerpt or "")[:12000]

    if row:
        if int(row.updated_at_ms or 0) > updated_ms:
            return _row_to_response(row)
        row.project_name = (body.project_name or "")[:120]
        row.path_aliases_json = aliases_json
        row.summary_json = summary_json
        row.project_md_excerpt = excerpt
        row.updated_at_ms = updated_ms
    else:
        row = ExtProjectKnowledge(
            user_id=user.id,
            project_hash=body.project_hash,
            project_name=(body.project_name or "")[:120],
            path_aliases_json=aliases_json,
            summary_json=summary_json,
            project_md_excerpt=excerpt,
            updated_at_ms=updated_ms,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return _row_to_response(row)
