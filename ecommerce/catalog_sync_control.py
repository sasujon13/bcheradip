"""On-demand catalogue sync for Reports. Never logs SSH secrets."""
import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.utils import timezone

REQUEST_NAME = 'run-now.json'
REMOTE_SYNC_DIR = '/home/sasha/apps/cheradip/bcheradip/private_suppliers/catalog_sync'


def sync_dir():
    path = Path(settings.BASE_DIR) / 'private_suppliers' / 'catalog_sync'
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def last_ui_path():
    return sync_dir() / 'last-ui-report.json'


def summarize_result(result):
    created = updated = unchanged = conflicts = photos = records = 0
    for entry in result.get('steps') or []:
        text = str(entry).strip().split('\n')[-1]
        if not text.startswith('{'):
            continue
        try:
            payload = json.loads(text)
        except ValueError:
            continue
        records += int(payload.get('records') or 0)
        created += int(payload.get('created') or 0)
        updated += int(payload.get('updated') or 0)
        unchanged += int(payload.get('unchanged') or 0)
        conflicts += int(payload.get('conflict_count') or 0)
        photos += int(payload.get('photos_imported') or 0)
    return {
        'status': result.get('status') or 'unknown',
        'started_at': result.get('started_at'),
        'finished_at': result.get('finished_at'),
        'records': records, 'created': created, 'updated': updated,
        'unchanged': unchanged, 'conflicts': conflicts, 'photos': photos,
        'detail': result.get('detail') or '',
        'note': 'Catalogue only (local shop ↔ live shop). Not supplier collection or hosting.',
    }


def last_catalog_report():
    fresh = load_run_report()
    ui = None
    path = last_ui_path()
    if path.exists():
        try:
            ui = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            ui = None
    if fresh and fresh.get('status') in ('running', 'queued'):
        live = {key: fresh[key] for key in ('status', 'percent', 'activity', 'saved_at', 'queued', 'ran', 'detail') if key in fresh}
        return {**(ui or {}), **live, 'status': fresh['status'], 'percent': int(fresh.get('percent') or 5)}
    if not ui:
        return fresh
    if not fresh:
        return ui
    if (fresh.get('saved_at') or '') >= (ui.get('saved_at') or ''):
        return {**ui, **fresh, 'queued': False, 'ran': True, 'percent': int(fresh.get('percent') or 100)}
    return ui


def load_run_report():
    folder = sync_dir()
    status = {}
    try:
        status = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        status = {}
    checkpoint = {}
    try:
        checkpoint = json.loads((folder / 'checkpoint.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        checkpoint = {}
    result = {}
    token = status.get('run') or ''
    for candidate in (folder / token / 'result.json' if token else None, Path(checkpoint.get('last_result') or '')):
        if candidate and candidate.exists():
            try:
                result = json.loads(candidate.read_text(encoding='utf-8'))
                break
            except (OSError, ValueError):
                continue
    if not result and not status:
        return None
    live_state = status.get('status') or ''
    if live_state in ('running', 'queued'):
        return {
            'status': live_state,
            'percent': int(status.get('percent') or 5),
            'activity': status.get('activity') or '',
            'saved_at': status.get('updated_at') or timezone.now().isoformat(),
            'queued': live_state == 'queued',
            'ran': False,
            'note': 'Catalogue only (local shop ↔ live shop). Not supplier collection or hosting.',
        }
    summary = summarize_result(result) if result else {
        'status': live_state or 'unknown', 'records': 0, 'created': 0, 'updated': 0,
        'unchanged': 0, 'conflicts': 0, 'photos': 0, 'detail': '',
        'note': 'Catalogue only (local shop ↔ live shop). Not supplier collection or hosting.',
    }
    summary.update(
        activity=status.get('activity') or '',
        percent=int(status.get('percent') or (100 if live_state == 'completed' else 0)),
        saved_at=status.get('updated_at') or timezone.now().isoformat(),
    )
    return summary


def save_ui_report(payload):
    payload = {**payload, 'saved_at': timezone.now().isoformat()}
    last_ui_path().write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return payload


def request_remote_sync():
    path = sync_dir() / REQUEST_NAME
    path.write_text(json.dumps({'requested_at': timezone.now().isoformat(), 'source': 'reports'}), encoding='utf-8')
    return path


def _sync_script():
    return Path(settings.BASE_DIR).resolve().parent / 'deploy' / 'sync-catalog.py'


def run_sync_now():
    script = _sync_script()
    if not script.exists():
        raise RuntimeError('Catalogue sync script is missing.')
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    completed = subprocess.run(
        [sys.executable, str(script)], cwd=str(script.parent.parent),
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=600, creationflags=creationflags, env=env)
    clear_sync_request()
    report = load_run_report() or last_catalog_report() or {}
    if completed.returncode:
        detail = (report.get('detail') or completed.stderr or completed.stdout or 'Catalogue sync failed.')[-800:]
        report = save_ui_report({
            **summarize_result({**report, 'status': 'failed', 'detail': detail}),
            'queued': False, 'ran': True, 'status': 'failed', 'detail': detail,
        })
        publish_ui_report(report)
        return report
    report = save_ui_report({**(report or {}), 'queued': False, 'ran': True, 'status': (report or {}).get('status') or 'completed'})
    publish_ui_report(report)
    try:
        from .storefront_index import refresh_storefront_index
        refresh_storefront_index()
    except Exception:
        pass
    return report


def write_progress(activity, percent, state='running'):
    payload = {
        'status': state, 'activity': activity, 'percent': int(percent),
        'updated_at': timezone.now().isoformat(), 'interval_seconds': 120, 'run': '',
    }
    (sync_dir() / 'status.json').write_text(json.dumps(payload), encoding='utf-8')
    return payload


def start_sync_background():
    """Start one hidden cycle so Reports can poll percent from status.json."""
    script = _sync_script()
    if not script.exists():
        raise RuntimeError('Catalogue sync script is missing.')
    live = load_run_report() or {}
    if live.get('status') == 'running':
        return {**live, 'percent': int(live.get('percent') or 5)}
    write_progress('Starting catalogue sync', 5)
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    subprocess.Popen(
        [sys.executable, str(script)], cwd=str(script.parent.parent),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
    return {
        'status': 'running', 'percent': 5, 'activity': 'Starting catalogue sync',
        'queued': False, 'ran': False,
        'note': 'Catalogue only (local shop ↔ live shop). Not supplier collection or hosting.',
    }


def queue_or_run_sync():
    """Windows shop PC starts a hidden cycle. Live Linux queues the Windows worker."""
    request_remote_sync()
    if os.name == 'nt':
        return start_sync_background()
    report = last_catalog_report() or {}
    write_progress('Sync requested on the live shop. The Windows catalogue worker will run one two-way cycle.', 8, 'queued')
    return {
        **{key: report[key] for key in report if key not in ('status', 'percent', 'activity', 'queued', 'ran')},
        'queued': True, 'ran': False, 'status': 'queued', 'percent': 8,
        'activity': 'Sync requested on the live shop. The Windows catalogue worker will run one two-way cycle.',
        'note': 'Catalogue only. The flashing two-minute terminal is not required.',
    }


def _env_db_sync():
    path = Path(settings.BASE_DIR) / '.env.db-sync'
    config = {}
    if not path.exists():
        return config
    for line in path.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip().strip('"\'')
    return config


def remote_sync_requested():
    if os.name != 'nt':
        return (sync_dir() / REQUEST_NAME).exists()
    config = _env_db_sync()
    if not config.get('SSH_HOST') or not config.get('SSH_USER'):
        return (sync_dir() / REQUEST_NAME).exists()
    remote = f'test -f {REMOTE_SYNC_DIR}/{REQUEST_NAME}'
    plink = _plink(config)
    if not plink:
        return (sync_dir() / REQUEST_NAME).exists()
    result = subprocess.run(
        plink + [remote],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return result.returncode == 0 or (sync_dir() / REQUEST_NAME).exists()


_last_poll = 0


def _plink(config):
    putty = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'PuTTY' / 'plink.exe'
    if not putty.exists() or not config.get('SSH_HOST') or not config.get('SSH_USER'):
        return None
    return [
        str(putty), '-batch', '-ssh', '-P', config.get('SSH_PORT') or '22',
        '-l', config['SSH_USER'], '-pw', config.get('SSH_PASSWORD') or '', config['SSH_HOST'],
    ]


def clear_sync_request():
    (sync_dir() / REQUEST_NAME).unlink(missing_ok=True)
    if os.name != 'nt':
        return
    config = _env_db_sync()
    plink = _plink(config)
    if not plink:
        return
    subprocess.run(
        plink + [f'rm -f {REMOTE_SYNC_DIR}/{REQUEST_NAME}'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def publish_ui_report(payload):
    if os.name != 'nt':
        return payload
    config = _env_db_sync()
    pscp = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'PuTTY' / 'pscp.exe'
    plink = _plink(config)
    if not pscp.exists() or not plink:
        return payload
    local = last_ui_path()
    if not local.exists():
        return payload
    subprocess.run(
        plink + [f'mkdir -p {REMOTE_SYNC_DIR} && chmod 700 {REMOTE_SYNC_DIR}'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    subprocess.run(
        [str(pscp), '-batch', '-P', config.get('SSH_PORT') or '22', '-pw', config.get('SSH_PASSWORD') or '',
         str(local), f"{config['SSH_USER']}@{config['SSH_HOST']}:{REMOTE_SYNC_DIR}/last-ui-report.json"],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return payload


def poll_requested_sync():
    import time
    global _last_poll
    if os.name != 'nt':
        return None
    now = time.monotonic()
    if now - _last_poll < 20:
        return None
    _last_poll = now
    try:
        if remote_sync_requested():
            return run_sync_now()
    except (OSError, subprocess.TimeoutExpired, RuntimeError):
        return None
    return None
