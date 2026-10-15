"""Resumable staff updates for EIINs already in Cheradip's institute database."""

import csv
import os
import re
import tempfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .institute_scraper import process_institute_page
from .models import InstituteUpdateAttempt, InstituteUpdateRun, Institutes


EIIN_PATTERN = re.compile(r'^\d{6}$')
BATCH_SIZE = 3  # Keep each staff request short and avoid flooding public sources.
LOG_NAMES = {'completed': 'completed.txt', 'failed': 'failed.txt'}


class InstituteUpdateBusy(Exception):
    pass


def log_directory(run):
    root = Path(getattr(settings, 'INSTITUTE_UPDATE_LOG_ROOT',
                        Path(settings.BASE_DIR) / 'work' / 'institute_updates')).resolve()
    return root / str(run.pk)


def log_path(run, kind):
    if kind not in LOG_NAMES:
        raise ValueError('Unknown institute update log.')
    return log_directory(run) / LOG_NAMES[kind]


def _replace_tsv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                         dir=path.parent, prefix='.institute-', suffix='.tmp',
                                         delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.writer(stream, delimiter='\t')
            writer.writerow(header)
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_logs(run):
    """Produce the two human-readable files from authoritative attempt records."""
    completed = []
    failed = []
    for attempt in run.attempts.order_by('eiin').iterator():
        stamp = attempt.updated_at.isoformat(timespec='seconds')
        if attempt.status == 'completed':
            completed.append((attempt.eiin, attempt.outcome, stamp, attempt.detail))
        elif attempt.status == 'failed':
            failed.append((attempt.eiin, attempt.detail, stamp, attempt.attempts))
    _replace_tsv(log_path(run, 'completed'), ('EIIN', 'RESULT', 'UPDATED_AT', 'EMIS_NOTE'), completed)
    _replace_tsv(log_path(run, 'failed'), ('EIIN', 'ERROR', 'UPDATED_AT', 'ATTEMPTS'), failed)


def rebuild_logs_locked(run):
    """Keep downloads and resume reconciliation from racing an active batch."""
    now = timezone.now()
    acquired = InstituteUpdateRun.objects.filter(pk=run.pk).filter(
        Q(locked_until__isnull=True) | Q(locked_until__lt=now)).update(
            locked_until=now + timedelta(minutes=6))
    if not acquired:
        raise InstituteUpdateBusy('Wait for the current EIIN batch to finish.')
    try:
        write_logs(run)
    finally:
        InstituteUpdateRun.objects.filter(pk=run.pk).update(locked_until=None)


def _append_log_rows(run, kind, rows):
    if not rows:
        return
    path = log_path(run, kind)
    if not path.exists():
        write_logs(run)
        return
    with path.open('a', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())


def _refresh_failed_log(run):
    rows = ((item.eiin, item.detail, item.updated_at.isoformat(timespec='seconds'), item.attempts)
            for item in run.attempts.filter(status='failed').order_by('eiin').iterator())
    _replace_tsv(log_path(run, 'failed'), ('EIIN', 'ERROR', 'UPDATED_AT', 'ATTEMPTS'), rows)


def failed_eiins_from_file(run):
    """Read retry EIINs from the requested text file, not a fresh source crawl."""
    path = log_path(run, 'failed')
    if not path.exists():
        write_logs(run)
    with path.open(encoding='utf-8', newline='') as stream:
        rows = csv.reader(stream, delimiter='\t')
        next(rows, None)
        candidates = {row[0].strip() for row in rows if row and EIIN_PATTERN.fullmatch(row[0].strip())}
    if not candidates:
        return []
    active = set(InstituteUpdateAttempt.objects.filter(
        run=run, status='failed', eiin__in=candidates).values_list('eiin', flat=True))
    return sorted(candidates & active)


def _eligible_institutes():
    # `000000` exists as a local placeholder, not a searchable government EIIN.
    return Institutes.objects.filter(eiinNo__regex=r'^[0-9]{6}$', eiinNo__gte='100000')


def start_or_resume_run():
    with transaction.atomic(using='default'):
        latest = InstituteUpdateRun.objects.select_for_update().first()
        if latest and latest.status == 'running':
            run = latest
        else:
            run = InstituteUpdateRun.objects.create(total=_eligible_institutes().count())
    # Repair an interrupted append before resuming; do not hold a DB lock during I/O.
    rebuild_logs_locked(run)
    return run


def run_summary(run):
    if run is None:
        return None
    completed = run.attempts.filter(status='completed').count()
    failed = run.attempts.filter(status='failed').count()
    return {'runId': str(run.pk), 'status': run.status, 'total': run.total,
            'processed': completed + failed, 'completed': completed, 'failed': failed,
            'cursor': run.cursor, 'startedAt': run.started_at,
            'completedAt': run.completed_at,
            'scheduleMonth': run.schedule_month, 'retryRound': run.retry_round,
            'logDirectory': str(log_directory(run)),
            'completedLogUrl': '/api/scraper/institutes/automatic/logs/completed/',
            'failedLogUrl': '/api/scraper/institutes/automatic/logs/failed/'}


def _record_attempt(run, eiin, status, outcome, detail):
    with transaction.atomic(using='default'):
        attempt, created = InstituteUpdateAttempt.objects.select_for_update().get_or_create(
            run=run, eiin=eiin,
            defaults={'status': status, 'outcome': outcome, 'detail': detail[:255]},
        )
        if not created:
            attempt.status = status
            attempt.outcome = outcome
            attempt.detail = detail[:255]
            attempt.attempts += 1
            attempt.save(update_fields=['status', 'outcome', 'detail', 'attempts', 'updated_at'])
    return attempt


def _update_eiin(run, eiin, actor):
    try:
        result = process_institute_page(page=1, size=1, enrich_emis=True, apply=True,
                                        actor=actor, eiin=eiin)
        record = result['records'][0]
        if result['failed']:
            status, outcome, detail = 'failed', '', record.get('detail') or 'Banbeis retrieval failed.'
        else:
            status, outcome, detail = 'completed', record['status'], record.get('emisWarning') or ''
    except Exception as exc:
        # A save error is retryable too; never mark an uncommitted update complete.
        status, outcome, detail = 'failed', '', f'Update error: {type(exc).__name__}: {exc}'
    attempt = _record_attempt(run, eiin, status, outcome, detail)
    return {'eiin': eiin, 'status': status, 'outcome': outcome, 'detail': detail[:255],
            'updatedAt': attempt.updated_at.isoformat(timespec='seconds'), 'attempts': attempt.attempts}


def process_step(run, *, mode, actor, after='', track_retry=False):
    if mode not in {'all', 'failed'}:
        raise ValueError('Unknown institute update mode.')
    now = timezone.now()
    lease_until = now + timedelta(minutes=6)
    acquired = InstituteUpdateRun.objects.filter(pk=run.pk).filter(
        Q(locked_until__isnull=True) | Q(locked_until__lt=now)).update(locked_until=lease_until)
    if not acquired:
        raise InstituteUpdateBusy('An institute update batch is already running.')
    try:
        run.refresh_from_db()
        if mode == 'all':
            if run.status == 'complete':
                selected = []
            else:
                selected = list(_eligible_institutes().filter(eiinNo__gt=run.cursor)
                                .order_by('eiinNo').values_list('eiinNo', flat=True)[:BATCH_SIZE])
        else:
            if after and not EIIN_PATTERN.fullmatch(after):
                raise ValueError('Invalid retry cursor.')
            selected = [eiin for eiin in failed_eiins_from_file(run) if eiin > after][:BATCH_SIZE]
        records = []
        for eiin in selected:
            records.append(_update_eiin(run, eiin, actor))
            if mode == 'all':
                run.cursor = eiin
                run.save(update_fields=['cursor'])
        if mode == 'all':
            has_more = _eligible_institutes().filter(eiinNo__gt=run.cursor).exists()
            if not has_more:
                run.status = 'complete'
                run.completed_at = timezone.now()
                run.save(update_fields=['status', 'completed_at'])
        else:
            next_after = selected[-1] if selected else after
            has_more = any(eiin > next_after for eiin in failed_eiins_from_file(run))
            if track_retry:
                run.retry_cursor = next_after if has_more else ''
                if not has_more:
                    run.retry_round = min(3, run.retry_round + 1)
                run.save(update_fields=['retry_cursor', 'retry_round'])
        if not all(log_path(run, kind).exists() for kind in LOG_NAMES):
            write_logs(run)
        else:
            completed_rows = [(item['eiin'], item['outcome'], item['updatedAt'], item['detail'])
                              for item in records if item['status'] == 'completed']
            _append_log_rows(run, 'completed', completed_rows)
            if mode == 'all':
                failed_rows = [(item['eiin'], item['detail'], item['updatedAt'], item['attempts'])
                               for item in records if item['status'] == 'failed']
                _append_log_rows(run, 'failed', failed_rows)
            elif not has_more:
                _refresh_failed_log(run)
        return {'run': run_summary(run), 'records': records, 'hasMore': has_more,
                'nextAfter': selected[-1] if selected else after}
    finally:
        InstituteUpdateRun.objects.filter(pk=run.pk).update(locked_until=None)
