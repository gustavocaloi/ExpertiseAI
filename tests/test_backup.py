import asyncio
import time
import threading
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import backup_jobs, backup_routes, backup_services as backup, config, db, kb_routes, maintenance, monitoria_services, security, services
from test_monitoria import isolated_monitoria  # noqa: F401


@pytest.fixture()
def backup_context(isolated_monitoria, monkeypatch):
    ctx = isolated_monitoria
    monkeypatch.setattr(backup_jobs, 'WAIT_SECONDS', 2)
    monkeypatch.setattr(kb_routes, '_UPLOAD_JOBS_DIR', ctx['data_dir'] / '_upload_jobs')
    monkeypatch.setattr(config, 'ACCESS_CONTROL_ENABLED', True)
    app = FastAPI()
    app.add_middleware(maintenance.StorageMaintenanceMiddleware)
    app.include_router(backup_routes.router, prefix='/api/v1')
    @app.get('/probe')
    def probe():
        return {'ok': True}
    with TestClient(app) as client:
        ctx['client'] = client
        yield ctx
    for worker in threading.enumerate():
        if worker.name.startswith("backup-"):
            worker.join(timeout=5)
            assert not worker.is_alive()
    services.clear_storage_caches()
    kb_routes._UPLOAD_JOBS.clear()


def token(ctx, user='admin_id'):
    row = db.get_user_by_id(ctx[user])
    return security.create_access_token(row['id'], ctx['company_id'], 'admin', row['email'])


def headers(ctx, user='admin_id'):
    return {'Authorization': 'Bearer ' + token(ctx, user)}


def wait_job(ctx, job_id):
    auth = headers(ctx)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        response = ctx['client'].get(f'/api/v1/admin/backup/jobs/{job_id}', headers=auth)
        assert response.status_code == 200, response.text
        job = response.json()
        if job['status'] in {'ready', 'failed'}:
            return job
        time.sleep(0.02)
    raise AssertionError('Backup job timed out')


def export(ctx):
    response = ctx['client'].post('/api/v1/admin/backup/export', headers=headers(ctx))
    assert response.status_code == 202, response.text
    job = wait_job(ctx, response.json()['job_id'])
    assert job['status'] == 'ready', job
    response = ctx['client'].get(f"/api/v1/admin/backup/jobs/{job['job_id']}/download", headers=headers(ctx))
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.content


def restore(ctx, content, **kwargs):
    return ctx['client'].post('/api/v1/admin/backup/restore', headers=kwargs.pop('headers', headers(ctx)),
        files={'file': ('backup.json', content, 'application/json')}, data={'confirmation': kwargs.pop('confirmation', 'RESTAURAR')})


def persistent_files():
    return {(key, path.relative_to(root).as_posix()): path.read_bytes()
            for key, root in backup.stores().items() if root.exists()
            for path in root.rglob('*') if path.is_file() and path.suffix != '.lock'}


def rows_snapshot():
    conn = db.get_connection()
    try:
        return {table: sorted([list(row) for row in conn.execute(f'SELECT * FROM "{table}"')], key=repr)
                for table in backup._tables(conn)}
    finally:
        conn.close()


def seed_content(ctx):
    cid = ctx['company_id']
    doc = services.create_or_update_text_document(cid, 'suporte', 'guias', 'manual', None,
        'Manual de operação', '# Conteúdo íntegro\nAção e revisão.', 'admin@test.local', is_published=True)
    services.create_or_update_text_document(cid, 'suporte', 'guias', 'manual', doc['document_uuid'],
        'Manual atualizado', '# Nova versão pendente', 'admin@test.local', pending_approval=True)
    source = ctx['data_dir'] / 'attachment.pdf'
    source.write_bytes(b'%PDF-1.7\x00\xff')
    services.attach_document_file(cid, 'suporte', 'guias', 'manual', source, 'original.pdf')
    db.set_user_area_scope(ctx['operator_id'], cid, 'selected', ['suporte'])
    db.set_user_modules(ctx['operator_id'], cid, ['conteudo', 'monitoria'], 'monitoria_analista')
    asyncio.run(monitoria_services.create_demo_conversation(cid, operador_user_id=ctx['operator_id']))
    kb_routes._UPLOAD_JOBS_DIR.mkdir()
    (kb_routes._UPLOAD_JOBS_DIR / 'completed.json').write_text(json.dumps({'status': 'done'}))
    return doc


def test_full_round_trip_users_files_permissions_search_and_sessions(backup_context):
    ctx = backup_context
    doc = seed_content(ctx)
    cid2 = db.create_company('Outra empresa', 'outra')
    db.assign_role_to_user(ctx['admin_id'], cid2, 'admin')
    before_files, before_rows = persistent_files(), rows_snapshot()
    old_access = token(ctx)
    old_refresh = security.create_refresh_token(ctx['admin_id'], ctx['company_id'], 'admin', 'admin@test.local')
    content = export(ctx)
    for root in backup.stores().values():
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        (root / 'not-in-backup.txt').write_text('remove me')
    db.create_user('Novo', 'new@test.local', security.hash_password('new'))
    db.set_user_roles_in_company(ctx['operator_id'], ctx['company_id'], ['aprovador'])
    services._DOCUMENT_META_COUNT_CACHE[999] = (1, 999)
    result = restore(ctx, content)
    assert result.status_code == 200, result.text
    assert rows_snapshot() == before_rows
    assert persistent_files() == before_files
    assert not services._DOCUMENT_META_COUNT_CACHE
    assert security.verify_password('secret', db.get_user_by_id(ctx['admin_id'])['password_hash'])
    assert db.search_document_uuids(ctx['company_id'], 'Conteúdo') == [doc['document_uuid']]
    assert db.get_user_by_email('new@test.local') is None
    for value, kind in [(old_access, 'access'), (old_refresh, 'refresh')]:
        with pytest.raises(Exception) as exc:
            security.decode_access_token(value, kind)
        assert exc.value.status_code == 401
    assert ctx['client'].get('/api/v1/admin/backup/status', headers=headers(ctx)).status_code == 200


def test_restore_rebases_audio_paths(backup_context, monkeypatch):
    ctx = backup_context
    seed_content(ctx)
    content = export(ctx)
    new_root = ctx['data_dir'] / 'relocated-audio'
    monkeypatch.setattr(monitoria_services, 'MONITORIA_ROOT', new_root)
    result = restore(ctx, content)
    assert result.status_code == 200, result.text
    conn = db.get_connection()
    try:
        audio = Path(conn.execute('SELECT audio_path FROM monitoria_conversations').fetchone()[0])
    finally:
        conn.close()
    assert audio.is_relative_to(new_root)
    assert audio.is_file()


@pytest.mark.parametrize('action', ['status', 'export', 'restore'])
def test_authorization_no_bypass_or_tenant_escalation(backup_context, monkeypatch, action):
    ctx = backup_context
    def request(auth=None):
        if action == 'restore':
            return restore(ctx, b'{}', headers=auth or {})
        method = ctx['client'].get if action == 'status' else ctx['client'].post
        return method('/api/v1/admin/backup/' + action, headers=auth or {})
    assert request().status_code == 401
    assert request(headers(ctx, 'operator_id')).status_code == 403  # forged admin claim ignored
    db.create_company('Outra', 'outra')
    assert request(headers(ctx)).status_code == 403
    monkeypatch.setattr(config, 'ACCESS_CONTROL_ENABLED', False)
    assert request(headers(ctx)).status_code == 403


@pytest.mark.parametrize('damage', ['json', 'version', 'schema', 'missing-table', 'columns', 'traversal', 'absolute', 'duplicate', 'checksum', 'foreign-key', 'missing-audio', 'no-admin'])
def test_invalid_archive_leaves_live_data_untouched(backup_context, damage):
    ctx = backup_context
    seed_content(ctx)
    payload = json.loads(export(ctx))
    if damage == 'version': payload['version'] = 200
    if damage == 'schema': payload['schema_sha256'] = 'other'
    if damage == 'missing-table': del payload['tables']['users']
    if damage == 'columns': payload['tables']['users']['columns'][0] = 'unknown'
    if damage == 'traversal': payload['files'][0]['path'] = '../outside'
    if damage == 'absolute': payload['files'][0]['path'] = '/tmp/outside'
    if damage == 'duplicate': payload['files'].append(payload['files'][0])
    if damage == 'checksum': payload['files'][0]['sha256'] = '0' * 64
    if damage == 'foreign-key':
        table = payload['tables']['user_company_roles']
        table['rows'][0][table['columns'].index('user_id')] = 100000
    if damage == 'missing-audio': payload['files'] = [f for f in payload['files'] if f['store'] != 'monitoria']
    if damage == 'no-admin':
        table = payload['tables']['user_company_roles']
        for row in table['rows']: row[table['columns'].index('role')] = 'editor'
    content = b'broken' if damage == 'json' else json.dumps(payload).encode()
    before_files, before_rows = persistent_files(), rows_snapshot()
    response = restore(ctx, content)
    assert response.status_code == 422, response.text
    assert persistent_files() == before_files
    assert rows_snapshot() == before_rows
    assert not backup._journal_path().exists()


def test_failure_during_install_rolls_back(backup_context, monkeypatch):
    ctx = backup_context
    seed_content(ctx)
    content = export(ctx)
    db.create_user('Depois', 'after@test.local', 'hash')
    before_files, before_rows = persistent_files(), rows_snapshot()
    original = backup._apply_database
    calls = []
    def fail_once(source):
        calls.append(source)
        if len(calls) == 1:
            raise OSError('simulated disk failure')
        return original(source)
    monkeypatch.setattr(backup, '_apply_database', fail_once)
    source = ctx['data_dir'] / 'backup.json'
    source.write_bytes(content)
    with pytest.raises(OSError, match='simulated'):
        backup.restore_backup(source)
    assert len(calls) == 2
    assert persistent_files() == before_files
    assert rows_snapshot() == before_rows
    assert not backup._journal_path().exists()


def test_limits_and_confirmation(backup_context, monkeypatch):
    ctx = backup_context
    assert restore(ctx, b'{}', confirmation='wrong').status_code == 422
    monkeypatch.setattr(config, 'BACKUP_MAX_BYTES', 10)
    assert restore(ctx, b'x' * 11).status_code == 413
    response = ctx['client'].post('/api/v1/admin/backup/export', headers=headers(ctx))
    assert response.status_code == 202
    assert wait_job(ctx, response.json()['job_id'])['status'] == 'failed'


def test_lock_blocks_requests_jobs_and_other_processes(backup_context):
    ctx = backup_context
    with maintenance.storage_access():
        response = ctx['client'].post('/api/v1/admin/backup/export', headers=headers(ctx))
        assert response.status_code == 202
        job_id = response.json()['job_id']
        assert ctx['client'].get(f'/api/v1/admin/backup/jobs/{job_id}', headers=headers(ctx)).json()['status'] == 'queued'
    assert wait_job(ctx, job_id)['status'] == 'ready'
    with maintenance.storage_access(exclusive=True):
        assert ctx['client'].get('/probe').status_code == 503
        command = "import fcntl,sys; f=open(sys.argv[1], 'a+b'); fcntl.flock(f,fcntl.LOCK_SH|fcntl.LOCK_NB)"
        result = subprocess.run([sys.executable, '-c', command, str(ctx['data_dir'] / '.platform-maintenance.lock')], capture_output=True)
        assert result.returncode != 0
    assert ctx['client'].get('/probe').status_code == 200
    async def check_job():
        started, release = asyncio.Event(), asyncio.Event()
        @maintenance.background_storage
        async def job():
            started.set()
            await release.wait()
        task = asyncio.create_task(job())
        await started.wait()
        with pytest.raises(maintenance.MaintenanceBusy):
            with maintenance.storage_access(exclusive=True): pass
        release.set()
        await task
    asyncio.run(check_job())


def test_interrupted_commit_recovers_on_restart(backup_context):
    import os
    ctx = backup_context
    seed_content(ctx)
    content = export(ctx)
    db.create_user('Antes da falha', 'before-crash@test.local', 'hash')
    (services.KB_ROOT / 'keep-after-crash.txt').write_text('live data')
    before_files, before_rows = persistent_files(), rows_snapshot()
    source = ctx['data_dir'] / 'restore.json'
    source.write_bytes(content)
    script = '''
import os, sys
from pathlib import Path
from app import backup_services, maintenance
backup_services._apply_database = lambda source: os._exit(9)
with maintenance.storage_access(exclusive=True):
    backup_services.restore_backup(Path(sys.argv[1]))
'''
    env = {**os.environ, 'EXPAI_DATA_DIR': str(ctx['data_dir']), 'EXPAI_DB_PATH': str(db.DB_PATH),
           'EXPAI_KB_ROOT': str(services.KB_ROOT), 'EXPAI_MONITORIA_ROOT': str(monitoria_services.MONITORIA_ROOT)}
    result = subprocess.run([sys.executable, '-c', script, str(source)], env=env, capture_output=True)
    assert result.returncode == 9, result.stderr.decode()
    assert backup._journal_path().exists()
    assert ctx['client'].get('/probe').status_code == 503
    with maintenance.storage_access(exclusive=True):
        backup.recover_restore()
    assert rows_snapshot() == before_rows
    assert persistent_files() == before_files
    assert ctx['client'].get('/probe').status_code == 200
    assert not backup._journal_path().exists()


def test_queued_kb_upload_prevents_incomplete_backup(backup_context):
    ctx = backup_context
    kb_routes._UPLOAD_JOBS_DIR.mkdir()
    (kb_routes._UPLOAD_JOBS_DIR / 'waiting.json').write_text('{"status":"processing"}')
    response = ctx['client'].post('/api/v1/admin/backup/export', headers=headers(ctx))
    assert response.status_code == 202
    job = wait_job(ctx, response.json()['job_id'])
    assert job['status'] == 'failed'
    assert 'uploads' in job['error']


def test_profile_exposes_only_actual_global_admin(backup_context, monkeypatch):
    from app import routers
    ctx = backup_context
    monkeypatch.setattr(security, 'ACCESS_CONTROL_ENABLED', True)
    monkeypatch.setattr(routers, 'ACCESS_CONTROL_ENABLED', True)
    ctx['client'].app.include_router(routers.router, prefix='/api/v1')
    assert ctx['client'].get('/api/v1/auth/me', headers=headers(ctx)).json()['can_manage_backup'] is True
    assert ctx['client'].get('/api/v1/auth/me', headers=headers(ctx, 'operator_id')).json()['can_manage_backup'] is False
    db.create_company('Outra empresa', 'outra')
    assert ctx['client'].get('/api/v1/auth/me', headers=headers(ctx)).json()['can_manage_backup'] is False


def test_unauthorized_restore_is_rejected_before_reading_body(backup_context):
    called = []
    async def endpoint(scope, receive, send):
        await receive()
    async def receive():
        raise AssertionError('Unauthorized request body must not be consumed')
    async def send(message):
        called.append(message)
    middleware = maintenance.StorageMaintenanceMiddleware(endpoint)
    asyncio.run(middleware({'type': 'http', 'path': '/api/v1/admin/backup/restore', 'headers': []}, receive, send))
    assert called[0]['status'] == 401


def test_chunked_multipart_limit(backup_context, monkeypatch):
    ctx = backup_context
    monkeypatch.setattr(config, 'BACKUP_MAX_BYTES', 10)
    response = restore(ctx, b'x' * (1024 * 1024 + 100))
    assert response.status_code == 413, response.text
