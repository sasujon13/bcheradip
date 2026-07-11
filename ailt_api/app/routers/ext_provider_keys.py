"""Authenticated extension endpoint — fetch server-managed LLM keys."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_current_ext_user
from app.ext_database import get_ext_db
from app.models import ExtUser
from app.services.ext_provider_keys import list_provider_keys_for_client

router = APIRouter(prefix="/ext", tags=["ext-provider-keys"])


@router.get("/provider-keys")
def get_provider_keys(
    user: ExtUser = Depends(get_current_ext_user),
    db: Session = Depends(get_ext_db),
) -> dict:
    """Return Cheradip-managed provider keys for signed-in extension users.

    Keys are used server-side by the extension host only — never show in the
    settings webview. Requires an active ext_sessions Bearer token.
    """
    _ = user
    return {"keys": list_provider_keys_for_client(db)}
