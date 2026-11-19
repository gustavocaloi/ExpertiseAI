"""Disk-backed export jobs. One generator across workers; artifacts remain private."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import logging
from pathlib import Path
import re
import threading
import time
from uuid import uuid4

from fastapi import HTTPException

from . import backup_services, config, db
from .maintenance import backup_control_access, storage_access, MaintenanceBusy, session_epoch

logger = logging.getLogger(__name__)
RETENTION_SECONDS = 24 * 60 * 60
WAIT_SECONDS = 300
_JOB_ID = re.compile(r'^[a-f0-9]{32}$')


def root():
    path = Path(config.DATA_DIR) / '_backup_exports'
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _write(path, value):
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _lock(path, shared=False):
    handle = path.open('a+b')
    try:
        fcntl.flock(handle, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise MaintenanceBusy('Já existe um backup em preparação.')
    return handle


@contextmanager
def artifact_access(job_id, shared=False):
    handle = _lock(root() / f'{job_id}.lock', shared)
    try:
        yield
    finally:
        handle.close()


def _read(job_id):
    if not _JOB_ID.fullmatch(job_id):
        raise HTTPException(404, 'Backup não encontrado.')
    try:
        return json.loads((root() / f'{job_id}.meta.json').read_text())
    except FileNotFoundError:
        raise HTTPException(404, 'Backup não encontrado.')


def public_job(job):
    return {key: job.get(key) for key in ('job_id', 'status', 'progress', 'phase', 'message',
            'created_at', 'expires_at', 'filename', 'size_bytes', 'error')}


def get_job(job_id, user):
    job = _read(job_id)
    if job['owner_id'] != user.user_id or job['owner_email'] != user.email:
        raise HTTPException(404, 'Backup não encontrado.')
    if job['epoch'] != session_epoch() or job['expires_at'] <= time.time():
        raise HTTPException(410, 'Backup expirado ou invalidado. Gere um novo arquivo.')
    if job['status'] in {'queued', 'running'}:
        try:
            with artifact_access(job_id):
                job = _read(job_id)
                if job['status'] in {'queued', 'running'}:
                    job.update(status='failed', phase='failed', error='Geração interrompida pelo reinício do serviço. Gere novamente.',
                               message='O backup não foi concluído.')
                    (root() / f'{job_id}.partial').unlink(missing_ok=True)
                    _write(root() / f'{job_id}.meta.json', job)
        except MaintenanceBusy:
            pass
    return job


def latest_job(user):
    path = root() / f'latest-{user.user_id}.json'
    if not path.exists():
        return None
    try:
        return public_job(get_job(json.loads(path.read_text())['job_id'], user))
    except HTTPException as exc:
        if exc.status_code in {404, 410}:
            return None
        raise


def cleanup_expired():
    directory = root()
    epoch, now = session_epoch(), time.time()
    for path in directory.glob('*.meta.json'):
        job_id = path.name.split('.')[0]
        try:
            with artifact_access(job_id):
                job = json.loads(path.read_text())
                if job['expires_at'] <= now or job['epoch'] != epoch:
                    (directory / f'{job_id}.json').unlink(missing_ok=True)
                    (directory / f'{job_id}.partial').unlink(missing_ok=True)
                    path.unlink(missing_ok=True)
        except (MaintenanceBusy, FileNotFoundError):
            continue


def start_job(user):
    directory = root()
    try:
        generation_lock = _lock(directory / '.generator.lock')
    except MaintenanceBusy:
        existing = latest_job(user)
        if existing and existing['status'] in {'queued', 'running'}:
            return existing
        raise HTTPException(409, 'Outro administrador já está preparando um backup. Aguarde.')
    job_lock = None
    try:
        cleanup_expired()
        job_id = uuid4().hex
        job_lock = _lock(directory / f'{job_id}.lock')
        now = time.time()
        job = dict(job_id=job_id, owner_id=user.user_id, owner_email=user.email, epoch=session_epoch(),
                   status='queued', phase='waiting', progress=0, message='Aguardando operações em andamento...',
                   created_at=now, expires_at=now + RETENTION_SECONDS,
                   filename='expertise-ai-backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json',
                   size_bytes=None, error=None)
        _write(directory / f'{job_id}.meta.json', job)
        _write(directory / f'latest-{user.user_id}.json', {'job_id': job_id})
        worker = threading.Thread(target=_run, args=(directory, job, generation_lock, job_lock),
                                  name=f'backup-{job_id[:8]}', daemon=True)
        worker.start()
        return public_job(job)
    except BaseException:
        if job_lock:
            job_lock.close()
        generation_lock.close()
        raise


def _run(directory, initial, generation_lock, job_lock):
    job = dict(initial)
    job_id = job['job_id']
    partial, completed = directory / f'{job_id}.partial', directory / f'{job_id}.json'
    last_update = 0.0
    def progress(phase, percent, message):
        nonlocal last_update
        now = time.monotonic()
        if phase == job['phase'] and now - last_update < 0.2:
            return
        job.update(status='running', phase=phase, progress=max(job['progress'], min(99, int(percent))), message=message)
        _write(directory / f'{job_id}.meta.json', job)
        last_update = now
    try:
        deadline = time.monotonic() + WAIT_SECONDS
        while True:
            try:
                with backup_control_access(), storage_access(exclusive=True):
                    if job['epoch'] != session_epoch():
                        raise backup_services.InvalidBackup('Backup invalidado pela restauração. Gere novamente.')
                    current = db.get_user_by_id(job['owner_id'])
                    if not current or current['email'] != job['owner_email'] or not db.is_platform_admin(job['owner_id']):
                        raise backup_services.InvalidBackup('Permissão de administrador revogada.')
                    backup_services.export_backup(partial, progress=progress)
                    partial.replace(completed)
                    job.update(status='ready', phase='ready', progress=100, message='Backup pronto para download.',
                               size_bytes=completed.stat().st_size, expires_at=time.time() + RETENTION_SECONDS)
                    _write(directory / f'{job_id}.meta.json', job)
                    logger.info('Backup assíncrono concluído. job=%s user=%s', job_id, job['owner_id'])
                    break
            except MaintenanceBusy:
                if time.monotonic() >= deadline:
                    raise backup_services.InvalidBackup('A plataforma permaneceu ocupada. Aguarde os processamentos e gere novamente.')
                time.sleep(0.25)
    except Exception as exc:
        logger.exception('Falha na geração do backup %s', job_id)
        partial.unlink(missing_ok=True)
        completed.unlink(missing_ok=True)
        message = str(exc) if isinstance(exc, backup_services.InvalidBackup) else 'Falha ao preparar o arquivo. Tente novamente ou consulte o administrador do servidor.'
        job.update(status='failed', phase='failed', message='O backup não foi concluído.', error=message)
        _write(directory / f'{job_id}.meta.json', job)
    finally:
        job_lock.close()
        generation_lock.close()
