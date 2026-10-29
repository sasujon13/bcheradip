"""On-demand production Upload & Build from Reports. Never logs SSH secrets."""
import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.utils import timezone

REQUEST_NAME = 'run-now.json'
REMOTE_DIR = '/home/sasha/apps/cheradip/bcheradip/private_suppliers/upload_build'
NOTE = (
    'Uploads this computer\'s source and builds the live site. Creates missing tables only. '
    'Does not copy customers, orders, passwords, or shop catalogue rows. Use Sync Catalog for products.'
)


def work_dir():
    path = Path(settings.BASE_DIR) / 'private_suppliers' / 'upload_build'
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def last_ui_path():
    return work_dir() / 'last-ui-report.json'


def load_status():
    path = work_dir() / 'status.json'
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def last_deploy_report():
    ui = None
    if last_ui_path().exists():
        try:
            ui = json.loads(last_ui_path().read_text(encoding='utf-8'))
        except (OSError, ValueError):
            ui = None
    status = load_status()
    if status.get('status') in ('running', 'queued'):
        live = {key: status[key] for key in ('status', 'percent', 'activity', 'saved_at', 'updated_at', 'detail', 'note') if key in status}
        live['percent'] = int(status.get('percent') or 5)
        live['saved_at'] = status.get('updated_at') or timezone.now().isoformat()
        live['note'] = status.get('note') or NOTE
        return {**(ui or {}), **live}
    if ui:
        return ui
    if not status:
        return None
    status.setdefault('note', NOTE)
    status.setdefault('percent', 100 if status.get('status') == 'completed' else 0)
    return status


def write_progress(activity, percent, state='running'):
    payload = {
        'status': state, 'activity': activity, 'percent': int(percent),
        'updated_at': timezone.now().isoformat(), 'note': NOTE,
    }
    (work_dir() / 'status.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return payload


def request_remote_deploy():
    path = work_dir() / REQUEST_NAME
    path.write_text(json.dumps({'requested_at': timezone.now().isoformat(), 'source': 'reports'}), encoding='utf-8')
    return path


def _runner():
    return Path(settings.BASE_DIR).resolve().parent / 'deploy' / 'windows' / 'run-upload-build.py'


def start_deploy_background():
    script = _runner()
    if not script.exists():
        raise RuntimeError('Upload & Build runner is missing.')
    live = last_deploy_report() or {}
    if live.get('status') == 'running':
        return {**live, 'percent': int(live.get('percent') or 5)}
    write_progress('Starting Upload & Build', 5)
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    subprocess.Popen(
        [sys.executable, str(script)], cwd=str(script.parents[2]),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
    return {
        'status': 'running', 'percent': 5, 'activity': 'Starting Upload & Build',
        'queued': False, 'ran': False, 'note': NOTE,
    }


def run_deploy_now():
    script = _runner()
    if not script.exists():
        raise RuntimeError('Upload & Build runner is missing.')
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    completed = subprocess.run(
        [sys.executable, str(script)], cwd=str(script.parents[2]),
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=1320, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0,
        env=env)
    report = last_deploy_report() or {}
    if completed.returncode:
        report = {
            **report, 'status': 'failed', 'queued': False, 'ran': True,
            'detail': (report.get('detail') or completed.stderr or completed.stdout or 'Upload & Build failed.')[-800:],
            'note': NOTE,
        }
        last_ui_path().write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        return report
    return {**report, 'queued': False, 'ran': True, 'status': report.get('status') or 'completed', 'note': NOTE}


def queue_or_run_deploy():
    request_remote_deploy()
    if os.name == 'nt':
        return start_deploy_background()
    report = last_deploy_report() or {}
    write_progress('Upload & Build requested on the live shop. The Windows worker will upload source and build.', 8, 'queued')
    return {
        **{key: report[key] for key in report if key not in ('status', 'percent', 'activity', 'queued', 'ran')},
        'queued': True, 'ran': False, 'status': 'queued', 'percent': 8,
        'activity': 'Upload & Build requested on the live shop. The Windows worker will upload source and build.',
        'note': NOTE,
    }


_last_poll = 0


def poll_requested_deploy():
    import time
    from .catalog_sync_control import _env_db_sync, _plink
    global _last_poll
    if os.name != 'nt':
        return None
    now = time.monotonic()
    if now - _last_poll < 20:
        return None
    _last_poll = now
    requested = (work_dir() / REQUEST_NAME).exists()
    if not requested:
        config = _env_db_sync()
        plink = _plink(config)
        if plink:
            result = subprocess.run(
                plink + [f'test -f {REMOTE_DIR}/{REQUEST_NAME}'],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            requested = result.returncode == 0
    if not requested:
        return None
    try:
        return run_deploy_now()
    except (OSError, subprocess.TimeoutExpired, RuntimeError):
        return None
