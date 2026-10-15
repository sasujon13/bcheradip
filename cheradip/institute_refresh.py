"""Rate-limited public requests and the durable institute-update worker."""

import calendar
import logging
import re
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .institute_scraper import process_institute_page
from .institute_update_runs import (
    InstituteUpdateBusy, _eligible_institutes, failed_eiins_from_file,
    log_directory, process_step,
)
from .models import InstituteRefreshEvent, InstituteRefreshRequest, InstituteUpdateRun, Institutes


EIIN_PATTERN = re.compile(r'^\d{6}$')
PUBLIC_SUCCESS_INTERVAL = timedelta(hours=24)
PUBLIC_FAILURE_INTERVAL = timedelta(minutes=30)
PUBLIC_QUEUE_LIMIT = 100
WORKER_LEASE = timedelta(minutes=5)
BANGLADESH_TZ = ZoneInfo('Asia/Dhaka')
logger = logging.getLogger(__name__)


class PublicRefreshBusy(Exception):
    pass


def refresh_summary(row):
    if row is None:
        return {'status': 'not_requested', 'changed': False, 'lastCheckedAt': None}
    return {
        'status': row.status,
        'changed': row.status == 'complete' and row.outcome in {'created', 'updated', 'updated_staff'},
        'lastCheckedAt': row.completed_at,
        'outcome': row.outcome if row.status == 'complete' else '',
        'warning': 'EMIS staff could not be refreshed; saved staff is shown.'
                   if row.status == 'complete' and row.detail else '',
    }


def enqueue_public_refresh(eiin):
    """One request per EIIN, with a freshness window and bounded global backlog."""
    if not EIIN_PATTERN.fullmatch(eiin) or int(eiin) < 100000:
        raise ValueError('Invalid EIIN.')
    if not Institutes.objects.filter(eiinNo=eiin).exists():
        raise LookupError('Institute not found.')
    now = timezone.now()
    with transaction.atomic(using='default'):
        row, created = InstituteRefreshRequest.objects.select_for_update().get_or_create(eiin=eiin)
        if not created:
            if row.status == 'queued' or (row.status == 'running' and row.locked_until and row.locked_until > now):
                return refresh_summary(row)
            interval = PUBLIC_SUCCESS_INTERVAL if row.status == 'complete' else PUBLIC_FAILURE_INTERVAL
            if row.completed_at and row.completed_at + interval > now:
                return refresh_summary(row)
        if InstituteRefreshRequest.objects.filter(status__in=['queued', 'running']).count() >= PUBLIC_QUEUE_LIMIT:
            raise PublicRefreshBusy('The update queue is full. Please try again later.')
        row.status = 'queued'
        row.requested_at = now
        row.started_at = None
        row.completed_at = None
        row.locked_until = None
        row.outcome = ''
        row.detail = ''
        row.save()
        return refresh_summary(row)


def process_one_public_refresh():
    now = timezone.now()
    candidates = InstituteRefreshRequest.objects.filter(
        Q(status='queued') | Q(status='running', locked_until__lt=now)
    ).order_by('requested_at').values_list('eiin', flat=True)[:10]
    for eiin in candidates:
        claimed = InstituteRefreshRequest.objects.filter(eiin=eiin).filter(
            Q(status='queued') | Q(status='running', locked_until__lt=now)
        ).update(status='running', started_at=now, locked_until=now + WORKER_LEASE)
        if not claimed:
            continue
        try:
            result = process_institute_page(page=1, size=1, enrich_emis=True, apply=True, eiin=eiin)
            record = (result.get('records') or [{}])[0]
            if result.get('failed') or record.get('status') == 'failed':
                status, outcome, detail = 'failed', '', record.get('detail') or 'Source retrieval failed.'
            else:
                staff_changed = any(result.get(key, 0) for key in
                                    ('teachersCreated', 'teachersUpdated', 'teachersUnlisted'))
                outcome = 'updated_staff' if record.get('status') == 'unchanged' and staff_changed else record.get('status', 'unchanged')
                status, detail = 'complete', record.get('emisWarning') or ''
        except Exception as exc:
            status, outcome, detail = 'failed', '', f'{type(exc).__name__}: {exc}'
        completed = timezone.now()
        with transaction.atomic(using='default'):
            saved = InstituteRefreshRequest.objects.filter(eiin=eiin, status='running').update(
                status=status, outcome=outcome, detail=detail[:255],
                completed_at=completed, locked_until=None)
            if saved:
                InstituteRefreshEvent.objects.create(
                    eiin=eiin, status=status, outcome=outcome, detail=detail[:255])
        return eiin
    return None


def due_month_key(today=None):
    """Start on the last Dhaka calendar day; recover a missed start through day 3."""
    today = today or timezone.now().astimezone(BANGLADESH_TZ).date()
    if today.day == calendar.monthrange(today.year, today.month)[1]:
        return today.strftime('%Y-%m')
    if today.day <= 3:
        previous = today.replace(day=1) - timedelta(days=1)
        return previous.strftime('%Y-%m')
    return None


def ensure_scheduled_run(today=None):
    month = due_month_key(today)
    if not month:
        return None
    existing = InstituteUpdateRun.objects.filter(schedule_month=month).first()
    if existing:
        return existing
    year, number = (int(part) for part in month.split('-'))
    last_day = calendar.monthrange(year, number)[1]
    recent_start = datetime(year, number, last_day, tzinfo=BANGLADESH_TZ) - timedelta(days=3)
    manual_run = InstituteUpdateRun.objects.filter(
        schedule_month__isnull=True, status='running', started_at__gte=recent_start,
    ).order_by('-started_at').first()
    if manual_run is not None:
        # Continue a recent staff-started pass instead of duplicating a full crawl.
        manual_run.schedule_month = month
        manual_run.save(update_fields=['schedule_month'])
        return manual_run
    # Do not run two full crawls over the same public sources concurrently.
    if InstituteUpdateRun.objects.filter(status='running', locked_until__gt=timezone.now()).exists():
        return None
    run, _ = InstituteUpdateRun.objects.get_or_create(
        schedule_month=month, defaults={'total': _eligible_institutes().count()})
    return run


def process_scheduled_step():
    run = InstituteUpdateRun.objects.filter(schedule_month__isnull=False, retry_round__lt=3).order_by('started_at').first()
    if run is None:
        return False
    try:
        if run.status == 'running':
            process_step(run, mode='all', actor=None)
            return True
        if failed_eiins_from_file(run):
            process_step(run, mode='failed', actor=None, after=run.retry_cursor, track_retry=True)
        else:
            InstituteUpdateRun.objects.filter(pk=run.pk).update(retry_round=3, retry_cursor='')
        return True
    except InstituteUpdateBusy:
        return False


def prune_old_update_records(today=None):
    """Retain current and two preceding calendar months of completed run logs."""
    today = today or timezone.now().astimezone(BANGLADESH_TZ).date()
    month_index = today.year * 12 + today.month - 1 - 2
    cutoff = date(month_index // 12, month_index % 12 + 1, 1)
    root = Path(getattr(settings, 'INSTITUTE_UPDATE_LOG_ROOT',
                        Path(settings.BASE_DIR) / 'work' / 'institute_updates')).resolve()
    cutoff_at = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=BANGLADESH_TZ)
    old_runs = InstituteUpdateRun.objects.filter(started_at__lt=cutoff_at, status='complete').filter(
        Q(schedule_month__isnull=True) | Q(retry_round__gte=3))
    removed = 0
    for run in old_runs.iterator():
        target = log_directory(run)
        if target.is_symlink() or target.parent.resolve() != root or target.name != str(run.pk):
            continue
        if target.exists():
            shutil.rmtree(target)
        run.delete()
        removed += 1
    InstituteRefreshRequest.objects.filter(
        status__in=['complete', 'failed'], completed_at__lt=cutoff_at,
    ).delete()
    InstituteRefreshEvent.objects.filter(checked_at__lt=cutoff_at).delete()
    return removed


def worker_iteration(today=None, *, prune=False):
    """Do bounded work; safe to invoke repeatedly after crashes or restarts."""
    ensure_scheduled_run(today)
    public_eiin = process_one_public_refresh()
    monthly_worked = process_scheduled_step()
    if prune:
        prune_old_update_records(today)
    return bool(public_eiin or monthly_worked)


def run_worker_loop(*, stop_event=None, poll_seconds=5, max_seconds=None):
    started = time.monotonic()
    last_pruned_day = None
    while stop_event is None or not stop_event.is_set():
        if max_seconds is not None and time.monotonic() - started >= max_seconds:
            break
        try:
            today = timezone.now().astimezone(BANGLADESH_TZ).date()
            worked = worker_iteration(today, prune=today != last_pruned_day)
            last_pruned_day = today
        except Exception:
            logger.exception('Institute update worker iteration failed; retrying.')
            worked = False
        delay = 1 if worked else poll_seconds
        if stop_event is None:
            time.sleep(delay)
        else:
            stop_event.wait(delay)
