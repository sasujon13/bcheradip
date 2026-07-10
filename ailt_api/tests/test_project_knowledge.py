"""API tests for lightweight ext project knowledge sync."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.deps import get_current_ext_user, get_ext_db
from app.ext_database import ExtBase
from app.main import api
from app.models import ExtProjectKnowledge, ExtSession, ExtUser
from app.routers import ext_project_knowledge as pk_router
from app.security import session_expires_at


@pytest.fixture()
def ext_db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ExtBase.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def ext_user(ext_db_session):
    user = ExtUser(email="pk@test.dev", username="pktest", password_hash="x", role="user")
    ext_db_session.add(user)
    ext_db_session.commit()
    ext_db_session.refresh(user)
    return user


@pytest.fixture()
def auth_headers(ext_db_session, ext_user):
    token = "test-token-project-knowledge"
    ext_db_session.add(
        ExtSession(user_id=ext_user.id, token=token, expires_at=session_expires_at())
    )
    ext_db_session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def authed_client(ext_db_session, ext_user):
    def override_ext_db():
        try:
            yield ext_db_session
        finally:
            pass

    def override_ext_user():
        return ext_user

    api.dependency_overrides[get_ext_db] = override_ext_db
    api.dependency_overrides[get_current_ext_user] = override_ext_user
    with TestClient(api) as client:
        yield client
    api.dependency_overrides.clear()


@pytest.fixture()
def db_only_client(ext_db_session):
    def override_ext_db():
        try:
            yield ext_db_session
        finally:
            pass

    api.dependency_overrides[get_ext_db] = override_ext_db
    with TestClient(api) as client:
        yield client
    api.dependency_overrides.clear()


def _body(**overrides):
    base = {
        "project_hash": "a" * 32,
        "project_name": "demo-app",
        "path_aliases": {"helper.ts": "src/helper.ts"},
        "summary": {"workspace": "demo-app"},
        "project_md_excerpt": "## Stack\nTypeScript",
        "updated_at_ms": int(time.time() * 1000),
    }
    base.update(overrides)
    return base


def test_json_size_helper():
    small = pk_router._json_size({"a": 1})
    large = pk_router._json_size({"x": "y" * 50_000})
    assert small < large
    assert large > pk_router._MAX_PAYLOAD_BYTES


def test_upsert_get_and_list(authed_client):
    put = authed_client.put("/ext/project-knowledge", json=_body())
    assert put.status_code == 200
    data = put.json()
    assert data["project_hash"] == "a" * 32
    assert data["path_aliases"]["helper.ts"] == "src/helper.ts"

    get = authed_client.get(f"/ext/project-knowledge/{'a' * 32}")
    assert get.status_code == 200
    assert get.json()["project_name"] == "demo-app"

    listed = authed_client.get("/ext/project-knowledge")
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["project_name"] == "demo-app"


def test_get_not_found(authed_client):
    res = authed_client.get("/ext/project-knowledge/" + "b" * 32)
    assert res.status_code == 404


def test_requires_auth(db_only_client):
    res = db_only_client.get("/ext/project-knowledge")
    assert res.status_code == 401


def test_rejects_oversized_payload(authed_client):
    res = authed_client.put(
        "/ext/project-knowledge",
        json=_body(
            project_md_excerpt="x" * 12_000,
            path_aliases={},
            summary={"blob": "y" * 40_000},
        ),
    )
    assert res.status_code == 413


def test_stale_upsert_does_not_downgrade(authed_client, ext_db_session, ext_user):
    newer_ms = 9_000
    older_ms = 5_000
    ext_db_session.add(
        ExtProjectKnowledge(
            user_id=ext_user.id,
            project_hash="c" * 32,
            project_name="kept-name",
            path_aliases_json='{"old.ts":"src/old.ts"}',
            summary_json="{}",
            project_md_excerpt="keep me",
            updated_at_ms=newer_ms,
        )
    )
    ext_db_session.commit()

    res = authed_client.put(
        "/ext/project-knowledge",
        json=_body(
            project_hash="c" * 32,
            project_name="stale-name",
            path_aliases={"new.ts": "src/new.ts"},
            updated_at_ms=older_ms,
        ),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["project_name"] == "kept-name"
    assert data["path_aliases"] == {"old.ts": "src/old.ts"}
    assert data["updated_at_ms"] == newer_ms
