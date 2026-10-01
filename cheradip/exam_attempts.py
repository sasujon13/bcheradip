"""Server-owned lifecycle for exam attempts stored in Customer.settings."""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

ATTEMPTS_KEY = 'student_exam_attempts'
MAX_ACTIVE_ATTEMPTS = 20
SUBMISSION_GRACE_SECONDS = 30


def _aware(value):
    parsed = parse_datetime(str(value or ''))
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def issue_or_resume(settings, set_id, duration_seconds):
    now = timezone.now()
    data = dict(settings) if isinstance(settings, dict) else {}
    attempts = [row for row in data.get(ATTEMPTS_KEY, []) if isinstance(row, dict)]
    active = []
    resumed = None
    for row in attempts:
        expires = _aware(row.get('expiresAt'))
        if expires and expires + timedelta(seconds=SUBMISSION_GRACE_SECONDS) >= now:
            active.append(row)
            if int(row.get('setId') or 0) == int(set_id) and not resumed:
                resumed = row
    if resumed is None:
        duration_seconds = max(60, min(int(duration_seconds or 1200), 8 * 60 * 60))
        resumed = {
            'attemptId': secrets.token_urlsafe(32),
            'setId': int(set_id),
            'startedAt': now.isoformat(),
            'expiresAt': (now + timedelta(seconds=duration_seconds)).isoformat(),
        }
        active.insert(0, resumed)
    data[ATTEMPTS_KEY] = active[:MAX_ACTIVE_ATTEMPTS]
    return data, resumed


def consume_attempt(settings, set_id, attempt_id):
    now = timezone.now()
    data = dict(settings) if isinstance(settings, dict) else {}
    attempts = [row for row in data.get(ATTEMPTS_KEY, []) if isinstance(row, dict)]
    matched = None
    remaining = []
    for row in attempts:
        if str(row.get('attemptId') or '') == str(attempt_id or ''):
            matched = row
        else:
            remaining.append(row)
    if not matched or int(matched.get('setId') or 0) != int(set_id):
        raise ValueError('Invalid or already completed exam attempt')
    expires = _aware(matched.get('expiresAt'))
    if not expires or now > expires + timedelta(seconds=SUBMISSION_GRACE_SECONDS):
        raise ValueError('This exam attempt has expired')
    data[ATTEMPTS_KEY] = remaining[:MAX_ACTIVE_ATTEMPTS]
    return data, matched, now
