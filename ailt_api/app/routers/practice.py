from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, UserPracticeActivity
from app.schemas import (
    PracticeActivityDto,
    PracticeActivitySyncRequest,
    PracticeActivitySyncResponse,
)
from app.score_utils import build_score_payload, score_to_json

router = APIRouter(prefix="/practice", tags=["practice"])

# Cap Practice history per user on the remote DB (local device keeps up to 999).
MAX_PRACTICE_PER_USER = 99


def _to_dto(row: UserPracticeActivity) -> PracticeActivityDto:
    return PracticeActivityDto(
        client_id=row.client_id,
        mode=row.mode,
        difficulty=row.difficulty,
        practice_of=row.practice_of,
        language_code=row.language_code,
        output_language_code=row.output_language_code,
        reference_text=row.reference_text,
        spoken_text=row.spoken_text,
        correction_text=row.correction_text,
        output_text=row.output_text,
        utterance_percent=float(row.utterance_percent or 0),
        overall_percent=float(row.overall_percent or 0),
        created_at_ms=row.created_at_ms,
        updated_at_ms=row.updated_at_ms,
    )


def _trim_practice(db: Session, user_id: int) -> None:
    total = db.scalar(
        select(func.count()).select_from(UserPracticeActivity).where(
            UserPracticeActivity.user_id == user_id
        )
    ) or 0
    overflow = int(total) - MAX_PRACTICE_PER_USER
    if overflow <= 0:
        return
    candidates = db.scalars(
        select(UserPracticeActivity)
        .where(UserPracticeActivity.user_id == user_id)
        .order_by(UserPracticeActivity.created_at_ms.asc())
        .limit(overflow)
    ).all()
    for row in candidates:
        db.delete(row)


@router.post("/sync", response_model=PracticeActivitySyncResponse)
def sync_practice_activities(
    body: PracticeActivitySyncRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeActivitySyncResponse:
    import time

    now_ms = int(time.time() * 1000)
    latest_current: float | None = None
    for item in body.activities:
        existing = db.scalar(
            select(UserPracticeActivity).where(
                UserPracticeActivity.user_id == user.id,
                UserPracticeActivity.client_id == item.client_id,
            )
        )
        if existing:
            if item.updated_at_ms >= existing.updated_at_ms:
                existing.mode = item.mode
                existing.difficulty = item.difficulty
                existing.practice_of = item.practice_of
                existing.language_code = item.language_code
                existing.output_language_code = item.output_language_code
                existing.reference_text = item.reference_text
                existing.spoken_text = item.spoken_text
                existing.correction_text = item.correction_text
                existing.output_text = item.output_text
                existing.utterance_percent = item.utterance_percent
                existing.overall_percent = item.overall_percent
                existing.updated_at_ms = item.updated_at_ms
        else:
            db.add(
                UserPracticeActivity(
                    user_id=user.id,
                    client_id=item.client_id,
                    mode=item.mode,
                    difficulty=item.difficulty,
                    practice_of=item.practice_of,
                    language_code=item.language_code,
                    output_language_code=item.output_language_code,
                    reference_text=item.reference_text,
                    spoken_text=item.spoken_text,
                    correction_text=item.correction_text,
                    output_text=item.output_text,
                    utterance_percent=item.utterance_percent,
                    overall_percent=item.overall_percent,
                    created_at_ms=item.created_at_ms,
                    updated_at_ms=item.updated_at_ms,
                )
            )
        latest_current = float(item.utterance_percent)

    _trim_practice(db, user.id)
    db.flush()

    rows = db.scalars(
        select(UserPracticeActivity)
        .where(UserPracticeActivity.user_id == user.id)
        .order_by(UserPracticeActivity.created_at_ms.asc())
        .limit(MAX_PRACTICE_PER_USER)
    ).all()
    payload = build_score_payload(list(rows), current=latest_current)
    user.score = score_to_json(payload)
    db.commit()
    db.refresh(user)

    return PracticeActivitySyncResponse(
        activities=[_to_dto(r) for r in rows],
        server_time_ms=now_ms,
        user_score=payload,
    )
