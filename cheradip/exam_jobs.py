"""
Background exam-job runner with progress reporting.

`run_create_exam` / `run_add_exam` can take a long time (SQL + optional Home/Cloud
AI question generation), so the admin "Create Exam / Add Exam" buttons run them in
a background thread and poll progress here.

Status is persisted to small JSON files under tmp/exam_jobs so it also works when
Django has several server processes/workers.
"""
import json
import os
import threading
import uuid

from django.utils import timezone

# Project root (parent of cheradip/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOB_DIR = os.path.join(BASE_DIR, 'tmp', 'exam_jobs')

# Fields exposed through the progress API (no internal leak)
PUBLIC_FIELDS = (
    'id', 'kind', 'db_alias', 'status', 'percent', 'phase',
    'current_subject', 'current_chapter', 'current_topic',
    'topics_done', 'topics_total',
    'ai_created_total', 'ai_created_current', 'ai_existing',
    'processed', 'total', 'pending_sent', 'current_qid', 'current_table',
    'message', 'error',
)


def _job_path(job_id):
    return os.path.join(JOB_DIR, (job_id or '') + '.json')


def _read(job_id):
    try:
        with open(_job_path(job_id), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write(job):
    try:
        os.makedirs(JOB_DIR, exist_ok=True)
        tmp = _job_path(job['id']) + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(job, f, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, _job_path(job['id']))
    except OSError:
        pass


def get_job(job_id):
    return _read(job_id)


def update_job(job_id, **fields):
    job = _read(job_id)
    if job is None:
        return
    changed = False
    for key, value in fields.items():
        if key in PUBLIC_FIELDS and job.get(key) != value:
            job[key] = value
            changed = True
    if changed:
        _write(job)


def start_job(kind, db_alias, filters):
    """Start `kind` ('create_exam' | 'add_exam') in a background thread.

    Returns the job id; progress can be polled via get_job().
    """
    job_id = uuid.uuid4().hex
    job = {
        'id': job_id,
        'kind': kind,
        'db_alias': db_alias,
        'status': 'running',
        'percent': 0,
        'phase': 'Preparing…',
        'current_subject': '',
        'current_chapter': '',
        'current_topic': '',
        'topics_done': 0,
        'topics_total': 0,
        'ai_created_total': 0,
        'ai_created_current': 0,
        'ai_existing': 0,
        'message': '',
        'error': '',
        'started_at': timezone.now().isoformat(),
        'finished_at': None,
    }
    _write(job)

    from cheradip.exam_actions import run_create_exam, run_add_exam

    def _run():
        try:
            if kind == 'create_exam':
                result = run_create_exam(db_alias, filters, progress=lambda **kw: update_job(job_id, **kw))
            else:
                result = run_add_exam(db_alias, filters, progress=lambda **kw: update_job(job_id, **kw))
            update_job(
                job_id,
                status='done',
                percent=100,
                message=(result or {}).get('message', 'Done.'),
                finished_at=timezone.now().isoformat(),
            )
        except Exception as e:  # noqa: BLE001 — report any failure to the admin UI
            update_job(
                job_id,
                status='error',
                error=str(e),
                message='Exam operation failed.',
                finished_at=timezone.now().isoformat(),
            )

    threading.Thread(target=_run, daemon=True).start()
    return job_id


def start_question_update_job(db_alias, table_name, kind, chapter_list=None, topic_list=None):
    """Queue AI Question/Explanation updates for a subject table in the background.

    Each changed row becomes a pending-question-request for manual review
    (nothing is applied to the subject table directly).
    Returns the job id; progress polled via get_job().
    """
    job_id = uuid.uuid4().hex
    job = {
        'id': job_id,
        'kind': 'question_update_' + (kind or ''),
        'db_alias': db_alias,
        'status': 'running',
        'percent': 0,
        'phase': 'Preparing…',
        'current_subject': '',
        'current_chapter': '',
        'current_topic': '',
        'topics_done': 0,
        'topics_total': 0,
        'ai_created_total': 0,
        'ai_created_current': 0,
        'ai_existing': 0,
        'processed': 0,
        'total': 0,
        'pending_sent': 0,
        'current_qid': '',
        'current_table': table_name or '',
        'message': '',
        'error': '',
        'started_at': timezone.now().isoformat(),
        'finished_at': None,
    }
    _write(job)

    from cheradip.question_updater import run_question_update_job

    def _run():
        try:
            result = run_question_update_job(
                db_alias, table_name, kind,
                progress=lambda **kw: update_job(job_id, **kw),
                chapter_list=chapter_list,
                topic_list=topic_list,
            )
            update_job(
                job_id,
                status='done',
                percent=100,
                message=(result or {}).get('message', 'Done.'),
                finished_at=timezone.now().isoformat(),
            )
        except Exception as e:  # noqa: BLE001
            update_job(
                job_id,
                status='error',
                error=str(e),
                message='Question update job failed.',
                finished_at=timezone.now().isoformat(),
            )

    threading.Thread(target=_run, daemon=True).start()
    return job_id
