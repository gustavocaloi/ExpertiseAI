import json
import threading

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import backup_jobs, backup_routes, backup_services, db, maintenance
from test_backup import (backup_context, isolated_monitoria, headers, export, restore, wait_job, seed_content)  # noqa: F401


def test_returns_before_generation_progress_is_readable_and_download_waits(backup_context, monkeypatch):
    ctx = backup_context
    entered, release = threading.Event(), threading.Event()
    original = backup_services.export_backup
    def slow_export(path, progress=None):
        progress('files', 60, 'Preparando arquivos de teste...')
        entered.set()
        assert release.wait(5)
        original(path, progress=progress)
    monkeypatch.setattr(backup_services, 'export_backup', slow_export)
    auth = headers(ctx)
    try:
        response = ctx['client'].post('/api/v1/admin/backup/export', headers=auth)
        assert response.status_code == 202
        job_id = response.json()['job_id']
        assert entered.wait(3)
        progress = ctx['client'].get(f'/api/v1/admin/backup/jobs/{job_id}', headers=auth)
        assert progress.status_code == 200
        assert progress.json()['progress'] == 60
        assert progress.json()['status'] == 'running'
        assert ctx['client'].get('/probe').status_code == 503
        assert ctx['client'].get('/api/v1/admin/backup/status', headers=auth).status_code == 200
        assert ctx['client'].get(f'/api/v1/admin/backup/jobs/{job_id}/download', headers=auth).status_code == 409
        assert ctx['client'].post('/api/v1/admin/backup/export', headers=auth).json()['job_id'] == job_id
        assert restore(ctx, b'{}').status_code == 409
        # An independent ASGI instance reads persistent status while the original generator runs.
        app = FastAPI()
        app.add_middleware(maintenance.StorageMaintenanceMiddleware)
        app.include_router(backup_routes.router, prefix='/api/v1')
        with TestClient(app) as second:
            assert second.get('/api/v1/admin/backup/jobs/latest', headers=auth).json()['job']['job_id'] == job_id
    finally:
        release.set()
    assert wait_job(ctx, job_id)['progress'] == 100
    first = ctx['client'].get(f'/api/v1/admin/backup/jobs/{job_id}/download', headers=auth)
    second = ctx['client'].get(f'/api/v1/admin/backup/jobs/{job_id}/download', headers=auth)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert first.json()['format'] == backup_services.FORMAT


def test_jobs_are_owner_scoped_and_permissions_are_rechecked(backup_context):
    ctx = backup_context
    export(ctx)
    job = ctx['client'].get('/api/v1/admin/backup/jobs/latest', headers=headers(ctx)).json()['job']
    path = f"/api/v1/admin/backup/jobs/{job['job_id']}"
    db.set_user_roles_in_company(ctx['other_op_id'], ctx['company_id'], ['admin'])
    for suffix in ['', '/download']:
        assert ctx['client'].get(path + suffix).status_code == 401
        assert ctx['client'].get(path + suffix, headers=headers(ctx, 'operator_id')).status_code == 403
        assert ctx['client'].get(path + suffix, headers=headers(ctx, 'other_op_id')).status_code == 404
    assert ctx['client'].get('/api/v1/admin/backup/jobs/latest', headers=headers(ctx, 'other_op_id')).json()['job'] is None
    db.set_user_roles_in_company(ctx['admin_id'], ctx['company_id'], ['editor'])
    assert ctx['client'].get(path + '/download', headers=headers(ctx)).status_code == 403


def test_ready_job_invalidated_by_restore(backup_context):
    ctx = backup_context
    content = export(ctx)
    job = ctx['client'].get('/api/v1/admin/backup/jobs/latest', headers=headers(ctx)).json()['job']
    assert restore(ctx, content).status_code == 200
    assert ctx['client'].get(f"/api/v1/admin/backup/jobs/{job['job_id']}/download", headers=headers(ctx)).status_code == 410
    assert ctx['client'].get('/api/v1/admin/backup/jobs/latest', headers=headers(ctx)).json()['job'] is None
    backup_jobs.cleanup_expired()
    assert not (backup_jobs.root() / f"{job['job_id']}.json").exists()


def test_expiry_and_cleanup_do_not_delete_active_download(backup_context):
    ctx = backup_context
    export(ctx)
    job = ctx['client'].get('/api/v1/admin/backup/jobs/latest', headers=headers(ctx)).json()['job']
    meta = backup_jobs.root() / f"{job['job_id']}.meta.json"
    record = json.loads(meta.read_text())
    record['expires_at'] = 0
    meta.write_text(json.dumps(record))
    artifact = backup_jobs.root() / f"{job['job_id']}.json"
    with backup_jobs.artifact_access(job['job_id'], shared=True):
        backup_jobs.cleanup_expired()
        assert artifact.exists()
    assert ctx['client'].get(f"/api/v1/admin/backup/jobs/{job['job_id']}/download", headers=headers(ctx)).status_code == 410
    backup_jobs.cleanup_expired()
    assert not artifact.exists()


def test_interrupted_job_is_reported_as_failed(backup_context):
    ctx = backup_context
    export(ctx)
    job = ctx['client'].get('/api/v1/admin/backup/jobs/latest', headers=headers(ctx)).json()['job']
    meta = backup_jobs.root() / f"{job['job_id']}.meta.json"
    record = json.loads(meta.read_text())
    record.update(status='running', progress=40)
    meta.write_text(json.dumps(record))
    (backup_jobs.root() / f"{job['job_id']}.partial").write_text('incomplete')
    response = ctx['client'].get(f"/api/v1/admin/backup/jobs/{job['job_id']}", headers=headers(ctx))
    assert response.json()['status'] == 'failed'
    assert 'reinício' in response.json()['error']
    assert not (backup_jobs.root() / f"{job['job_id']}.partial").exists()
    assert ctx['client'].get(f"/api/v1/admin/backup/jobs/{job['job_id']}/download", headers=headers(ctx)).status_code == 409


def test_export_progress_measures_work_without_changing_format(backup_context, tmp_path):
    seed_content(backup_context)
    updates = []
    path = tmp_path / 'backup.json'
    backup_services.export_backup(path, progress=lambda phase, percent, message: updates.append((phase, percent)))
    assert {phase for phase, _ in updates} == {'snapshot', 'inventory', 'tables', 'files', 'finalizing'}
    percentages = [percent for _, percent in updates]
    assert percentages == sorted(percentages)
    assert percentages[-1] == 99
    assert json.loads(path.read_text())['version'] == 1
