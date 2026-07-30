from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, UserLearningActivity
from app.schemas import LearningActivityDto, LearningActivitySyncRequest, LearningActivitySyncResponse

router = APIRouter(prefix="/learning", tags=["learning"])

# Hard cap: never keep more than this many rows per user in user_learning_activities (remote).
MAX_ACTIVITIES_PER_USER = 99


def _to_dto(row: UserLearningActivity) -> LearningActivityDto:
    return LearningActivityDto(
        client_id=row.client_id,
        title=row.title,
        summary=row.summary,
        activity_type=row.activity_type,
        language_code=row.language_code,
        output_language_code=row.output_language_code,
        input_text=row.input_text,
        output_text=row.output_text,
        tags_json=row.tags_json,
        is_saved=row.is_saved,
        created_at_ms=row.created_at_ms,
        updated_at_ms=row.updated_at_ms,
    )


def _trim_activities(db: Session, user_id: int) -> None:
    """Drop oldest rows until the user has at most MAX_ACTIVITIES_PER_USER reserved."""
    total = db.scalar(
        select(func.count()).select_from(UserLearningActivity).where(
            UserLearningActivity.user_id == user_id
        )
    ) or 0
    overflow = int(total) - MAX_ACTIVITIES_PER_USER
    if overflow <= 0:
        return
    # Prefer deleting unsaved first, then oldest by created_at_ms.
    candidates = db.scalars(
        select(UserLearningActivity)
        .where(UserLearningActivity.user_id == user_id)
        .order_by(
            UserLearningActivity.is_saved.asc(),  # False (0) before True (1)
            UserLearningActivity.created_at_ms.asc(),
        )
        .limit(overflow)
    ).all()
    for row in candidates:
        db.delete(row)


def _maybe_update_user_score(user: User, item: LearningActivityDto) -> None:
    """Do not overwrite users.score from learning sync.

    Practice scores are JSON on users.score, updated only via /practice/sync.
    """
    _ = (user, item)
    return


@router.post("/sync", response_model=LearningActivitySyncResponse)
def sync_learning_activities(
    body: LearningActivitySyncRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningActivitySyncResponse:
    now_ms = int(time.time() * 1000)
    for item in body.activities:
        existing = db.scalar(
            select(UserLearningActivity).where(
                UserLearningActivity.user_id == user.id,
                UserLearningActivity.client_id == item.client_id,
            )
        )
        if existing:
            if item.updated_at_ms >= existing.updated_at_ms:
                existing.title = item.title
                existing.summary = item.summary
                existing.activity_type = item.activity_type
                existing.language_code = item.language_code
                existing.output_language_code = item.output_language_code
                existing.input_text = item.input_text
                existing.output_text = item.output_text
                existing.tags_json = item.tags_json
                existing.is_saved = existing.is_saved or item.is_saved
                existing.updated_at_ms = item.updated_at_ms
        else:
            db.add(
                UserLearningActivity(
                    user_id=user.id,
                    client_id=item.client_id,
                    title=item.title,
                    summary=item.summary,
                    activity_type=item.activity_type,
                    language_code=item.language_code,
                    output_language_code=item.output_language_code,
                    input_text=item.input_text,
                    output_text=item.output_text,
                    tags_json=item.tags_json,
                    is_saved=item.is_saved,
                    created_at_ms=item.created_at_ms,
                    updated_at_ms=item.updated_at_ms,
                )
            )
        _maybe_update_user_score(user, item)

    _trim_activities(db, user.id)
    db.commit()
    db.refresh(user)

    rows = db.scalars(
        select(UserLearningActivity)
        .where(UserLearningActivity.user_id == user.id)
        .order_by(UserLearningActivity.updated_at_ms.desc())
        .limit(MAX_ACTIVITIES_PER_USER)
    ).all()
    return LearningActivitySyncResponse(
        activities=[_to_dto(r) for r in rows],
        server_time_ms=now_ms,
    )
