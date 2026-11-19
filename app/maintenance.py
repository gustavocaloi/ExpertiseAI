"""Cross-process admission for consistent platform snapshots (local POSIX storage)."""
from __future__ import annotations

import asyncio
import fcntl
from contextlib import contextmanager, ExitStack
from functools import wraps
from pathlib import Path

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from . import config


class MaintenanceBusy(Exception):
    pass


def session_epoch() -> str:
    path = Path(config.DATA_DIR) / '.session-epoch'
    return path.read_text().strip() if path.exists() else ''


@contextmanager
def storage_access(*, exclusive=False, blocking=False):
    root = Path(config.DATA_DIR)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.platform-maintenance.lock').open('a+b') as handle:
        try:
            flags = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(handle, flags | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise MaintenanceBusy('Há operações em andamento. Aguarde e tente novamente.') from exc
        try:
            if not exclusive and (root / '.restore-journal.json').exists():
                raise MaintenanceBusy('Recuperação pendente. Reinicie o serviço antes de continuar.')
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def backup_control_access(*, exclusive=False, blocking=False):
    """Allow authenticated progress reads during export, but never during restore."""
    root = Path(config.DATA_DIR)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.backup-control.lock').open('a+b') as handle:
        try:
            fcntl.flock(handle, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise MaintenanceBusy('Backup ou restauração em andamento. Aguarde e tente novamente.') from exc
        try:
            if not exclusive and (root / '.restore-journal.json').exists():
                raise MaintenanceBusy('Recuperação pendente. Reinicie o serviço antes de continuar.')
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def background_storage(func):
    """Keep detached jobs admitted until completion; discard jobs from an old restore epoch."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        epoch = session_epoch()
        async def run():
            while True:
                if epoch != session_epoch():
                    return
                guard = storage_access()
                try:
                    guard.__enter__()
                except MaintenanceBusy:
                    await asyncio.sleep(0.25)
                    continue
                try:
                    if epoch == session_epoch():
                        return await func(*args, **kwargs)
                    return
                finally:
                    guard.__exit__(None, None, None)
        return run()
    return wrapped


async def finish_thread(func, *args):
    """A disconnected client must not release the lock while a worker still writes."""
    task = asyncio.create_task(asyncio.to_thread(func, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class StorageMaintenanceMiddleware:
    def __init__(self, app):
        self.app = app
        self.epoch = session_epoch()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'].startswith('/static/') or scope['path'] in {'/', '/health'}:
            return await self.app(scope, receive, send)
        path = scope['path'].rstrip('/')
        exclusive = path == '/api/v1/admin/backup/restore'
        control = path.startswith('/api/v1/admin/backup/') or path in {
            '/api/v1/auth/me', '/api/v1/auth/login', '/api/v1/auth/refresh', '/api/v1/config'}
        guard = ExitStack()
        try:
            if control:
                guard.enter_context(backup_control_access(exclusive=exclusive))
            if exclusive or not control:
                guard.enter_context(storage_access(exclusive=exclusive))
        except MaintenanceBusy as exc:
            guard.close()
            return await JSONResponse({'detail': str(exc)}, status_code=409 if exclusive else 503,
                                      headers={'Retry-After': '3'})(scope, receive, send)
        try:
            if (Path(config.DATA_DIR) / '.restore-journal.json').exists():
                return await JSONResponse({'detail': 'Recuperação pendente. Reinicie o serviço antes de continuar.'},
                                          status_code=503)(scope, receive, send)
            if exclusive:
                # Authorize before multipart parsing: an unauthenticated upload must not
                # hold the whole platform in maintenance while its body is received.
                from .backup_routes import require_platform_admin
                scheme, _, token = Headers(scope=scope).get('authorization', '').partition(' ')
                try:
                    require_platform_admin(token if scheme.lower() == 'bearer' else None)
                except HTTPException as exc:
                    return await JSONResponse({'detail': exc.detail}, status_code=exc.status_code)(scope, receive, send)
            epoch = session_epoch()
            if epoch != self.epoch:
                from . import services, kb_routes
                services.clear_storage_caches()
                kb_routes._UPLOAD_JOBS.clear()
                self.epoch = epoch
            received = 0
            async def limited_receive():
                nonlocal received
                message = await receive()
                received += len(message.get('body', b''))
                # Permit multipart headers while bounding the parser's temporary file.
                if received > config.BACKUP_MAX_BYTES + 1024 * 1024:
                    raise HTTPException(413, 'Arquivo excede o limite de backup configurado.')
                return message
            await self.app(scope, limited_receive if exclusive else receive, send)
        finally:
            guard.__exit__(None, None, None)
