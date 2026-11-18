import asyncio
import json
import time
import uuid

import pytest

from app import config, db, monitoria_db as mdb, monitoria_services as services, monitoria_routes as routes
from app.ai_providers.mock import MockAIProvider
from test_monitoria import isolated_monitoria, monitoria_client  # noqa: F401


def send(client, base, metadata=None, files=None, request_id=None):
    files = files if files is not None else [('ok.wav', b'RIFF....WAVE'), ('bad.txt', b'text')]
    return client.post(base + '/conversas/upload-lote',
        files=[('files', (name, body, 'audio/wav')) for name, body in files],
        data={'metadata': json.dumps(metadata if metadata is not None else [{'ticket_id': 'A'}, {'ticket_id': 'B'}]),
              'request_id': request_id or str(uuid.uuid4())})


def settle(client, base, batch_id):
    for _ in range(100):
        batch = client.get(base + '/lotes/' + batch_id).json()
        if batch['status'] not in {'queued', 'processing'}:
            return batch
        time.sleep(.03)
    pytest.fail('Batch did not complete')


def test_partial_batch_async_idempotent_and_recoverable(monitoria_client, isolated_monitoria):
    client, _, base = monitoria_client
    cid = isolated_monitoria['company_id']
    mdb.create_pillar(cid, 'Clareza')
    key = str(uuid.uuid4())
    response = send(client, base, request_id=key)
    assert response.status_code == 202, response.text
    batch = settle(client, base, response.json()['batch_id'])
    assert batch['counts']['completed'] == batch['counts']['rejected'] == 1
    assert batch['status'] == 'completed_with_errors'
    assert batch['items'][0]['ticket_id'] == 'A'
    assert batch['items'][0]['is_mock'] is True
    assert 'audio_path' not in response.text
    again = send(client, base, request_id=key)
    assert again.json()['batch_id'] == batch['batch_id']
    assert client.get(base + '/conversas').json()['total'] == 1
    assert len(list(isolated_monitoria['monitoria_root'].rglob('*.wav'))) == 1
    assert client.get(base + '/lotes').json()['items'][0]['batch_id'] == batch['batch_id']
    assert send(client, base, metadata=[{}, {'ticket_id': 'CHANGED'}], request_id=key).status_code == 409
    assert list(routes._TMP_UPLOADS.iterdir()) == []


def test_batch_permissions_and_per_file_scope(monitoria_client, isolated_monitoria):
    client, user, base = monitoria_client
    cid, operator = isolated_monitoria['company_id'], isolated_monitoria['operator_id']
    a, b = db.create_taxonomy(cid, 'area', 'a'), db.create_taxonomy(cid, 'area', 'b')
    mdb.create_pillar(cid, 'Clareza')
    db.set_user_modules(operator, cid, ['monitoria'], 'monitoria_supervisor')
    db.set_user_area_scope(operator, cid, 'selected', [a])
    user['id'] = operator
    result = send(client, base, files=[('a.wav', b'RIFF'), ('b.wav', b'RIFF')], metadata=[{'area': a}, {'area': b}])
    assert result.status_code == 202
    batch = settle(client, base, result.json()['batch_id'])
    assert batch['counts']['completed'] == batch['counts']['rejected'] == 1
    db.set_user_area_scope(operator, cid, 'selected', [b])
    after = client.get(base + '/lotes/' + batch['batch_id']).json()
    assert after['total'] == 1 and after['items'][0]['status'] == 'rejected'
    other = isolated_monitoria['other_op_id']
    db.set_user_modules(other, cid, ['monitoria'], 'monitoria_supervisor')
    db.set_user_area_scope(other, cid, 'selected', [a])
    user['id'] = other
    assert client.get(base + '/lotes/' + batch['batch_id']).status_code == 404
    assert client.get(base + '/lotes').json()['items'] == []
    foreign = db.create_company('Other', 'other-batch', '')
    assert client.get(base.replace(str(cid), str(foreign)) + '/lotes/' + batch['batch_id']).status_code in (403, 404)


def test_batch_limits_and_bad_metadata(monitoria_client, isolated_monitoria, monkeypatch):
    client, _, base = monitoria_client
    mdb.create_pillar(isolated_monitoria['company_id'], 'Clareza')
    assert send(client, base, metadata=[]).status_code == 422
    assert send(client, base, metadata=[{}] * 21, files=[('a.wav', b'R')] * 21).status_code == 413
    monkeypatch.setattr(routes, 'MAX_BATCH_FILE_BYTES', 3)
    result = send(client, base, metadata=[{}, {}, {'central_id': -1}], files=[('a.wav', b'RIFF'), ('empty.wav', b''), ('c.wav', b'R')])
    assert result.status_code == 202
    assert result.json()['counts']['rejected'] == 3
    monkeypatch.setattr(routes, 'MAX_BATCH_TOTAL_BYTES', 3)
    assert send(client, base).status_code == 413
    assert not list(routes._TMP_UPLOADS.iterdir())


def test_real_flag_rejects_batch_before_storage(monitoria_client, isolated_monitoria, monkeypatch):
    monkeypatch.setattr(config, 'MONITORIA_REAL_AI_ENABLED', True)
    client, _, base = monitoria_client
    mdb.create_pillar(isolated_monitoria['company_id'], 'Clareza')
    assert send(client, base).status_code == 409
    assert client.get(base + '/lotes').json()['items'] == []


def test_queue_survives_startup_migration_and_restarts(monitoria_client, isolated_monitoria, monkeypatch):
    client, _, base = monitoria_client
    cid = isolated_monitoria['company_id']
    mdb.create_pillar(cid, 'Clareza')
    monkeypatch.setattr(services, 'start_batch_worker', lambda: None)
    response = send(client, base)
    job_id = response.json()['items'][0]['job_id']
    assert mdb.get_job(cid, job_id)['lease_until'] is None
    db.init_db()
    assert mdb.get_job(cid, job_id)['lease_until'] is None
    assert services.cleanup_zombie_monitoria_jobs() == 0

    async def restarted_worker():
        worker = asyncio.create_task(services.batch_worker_loop())
        try:
            for _ in range(100):
                if mdb.get_job(cid, job_id)['status'] == 'completed':
                    return
                await asyncio.sleep(.02)
            pytest.fail('Restarted dispatcher did not process persisted queue')
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
    asyncio.run(restarted_worker())


def test_batch_concurrency_bounded_and_response_does_not_wait(monitoria_client, isolated_monitoria, monkeypatch):
    cid = isolated_monitoria['company_id']
    mdb.create_pillar(cid, 'Clareza')
    active, peak = 0, 0

    class Slow(MockAIProvider):
        async def transcribe(self, *args, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(.2)
                return await super().transcribe(*args, **kwargs)
            finally:
                active -= 1

    monkeypatch.setattr(services, 'get_ai_provider', lambda _: Slow())
    client, _, base = monitoria_client
    response = send(client, base, metadata=[{}] * 6, files=[('same.wav', b'RIFF')] * 6)
    assert response.status_code == 202
    assert response.json()['counts']['queued'] >= 4
    batch = settle(client, base, response.json()['batch_id'])
    assert batch['counts']['completed'] == 6
    assert 1 <= peak <= services.BATCH_CONCURRENCY
    assert len({item['conversation_uuid'] for item in batch['items']}) == 6
