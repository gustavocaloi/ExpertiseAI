"""Regression coverage for the five findings of the Monitoria audit."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from test_monitoria import isolated_monitoria, monitoria_client
from app import db, monitoria_db as mdb, monitoria_services as services
from app.ai_providers.mock import MockAIProvider


def test_definition_changes_create_version_and_preserve_snapshot(monitoria_client):
    client, _, base = monitoria_client
    example = client.post(base + '/demo').json()['items'][0]
    path = base + '/conversas/' + example['conversation_uuid']
    detail = client.get(path).json()
    score = detail['pillar_scores'][0]
    assert score['snapshot_available'] and score['prompt']
    changed = client.patch(base + '/pilares/' + str(score['pillar_id']), json={'prompt': 'Novo critério', 'weight': 9}).json()
    assert changed['version'] == score['pillar_version'] + 1
    assert changed['id'] != score['pillar_id']
    assert client.get(path).json()['pillar_scores'] == detail['pillar_scores']
    old = next(p for p in client.get(base + '/pilares?active_only=false').json()['items'] if p['id'] == score['pillar_id'])
    assert old['prompt'] == score['prompt'] and not old['is_active']
    assert changed['family_id'] == old['family_id']


def test_family_filter_preserves_history_and_version_filter_is_exact(monitoria_client):
    client, _, base = monitoria_client
    client.post(base + '/demo')
    pillar = client.get(base + '/pilares').json()['items'][0]
    new = client.post(base + '/pilares', json={'name': pillar['name'], 'prompt': 'Novo critério'}).json()
    assert client.get(base + '/conversas', params={'pillar_family_id': new['family_id']}).json()['total'] == 3
    assert client.get(base + '/conversas', params={'pillar_id': pillar['id']}).json()['total'] == 3
    assert client.get(base + '/conversas', params={'pillar_id': new['id']}).json()['total'] == 0
    all_versions = client.get(base + '/pilares?active_only=false').json()['items']
    assert {pillar['id'], new['id']} <= {p['id'] for p in all_versions}
    foreign = db.create_company('Other', 'other', '')
    foreign_pillar = mdb.create_pillar(foreign, pillar['name'])
    assert client.get(base + '/conversas', params={'pillar_family_id': foreign_pillar['family_id']}).json()['total'] == 0


def test_no_active_pillars_rejects_upload_and_worker_creates_nothing(monitoria_client, isolated_monitoria):
    client, _, base = monitoria_client
    client.post(base + '/demo')
    for pillar in client.get(base + '/pilares').json()['items']:
        assert client.patch(base + '/pilares/' + str(pillar['id']), json={'is_active': False}).status_code == 200
    before = client.get(base + '/pilares?active_only=false').json()['items']
    response = client.post(base + '/conversas/upload', files={'file': ('sample.wav', b'RIFF')})
    assert response.status_code == 409 and 'Configuração pendente' in response.json()['detail']
    assert client.get(base + '/conversas').json()['total'] == 3
    cid = isolated_monitoria['company_id']
    mdb.create_conversation(cid, 'pending-config')
    mdb.create_job(cid, 'pending-job', 'pending-config')
    asyncio.run(services.process_conversation_job(cid, 'pending-job', 'pending-config'))
    assert mdb.get_job(cid, 'pending-job')['status'] == 'failed'
    assert client.get(base + '/pilares').json()['items'] == []
    assert client.get(base + '/pilares?active_only=false').json()['items'] == before


def _pending_job(fixture, suffix='invalid'):
    cid = fixture['company_id']
    mdb.create_pillar(cid, 'Empatia', prompt='Reconhecer a necessidade do cliente')
    audio = fixture['data_dir'] / f'{suffix}.wav'
    audio.write_bytes(b'RIFF')
    mdb.create_conversation(cid, suffix, audio_path=str(audio))
    mdb.create_job(cid, suffix + '-job', suffix)
    return cid, suffix + '-job', suffix


@pytest.mark.parametrize('fault', ['high', 'negative', 'nan', 'infinite', 'no_rationale', 'empty', 'missing', 'duplicate', 'unknown', 'wrong_pillar', 'wrong_version', 'turn_score', 'no_evidence'])
def test_invalid_evaluation_cannot_publish_partial_results(isolated_monitoria, monkeypatch, fault):
    args = _pending_job(isolated_monitoria)
    class Invalid(MockAIProvider):
        async def evaluate_pillar(self, **kwargs):
            result = await super().evaluate_pillar(**kwargs)
            if fault in {'high', 'negative', 'nan', 'infinite'}:
                result.score = {'high': 180, 'negative': -1, 'nan': float('nan'), 'infinite': float('inf')}[fault]
            elif fault == 'no_rationale': result.rationale = ''
            elif fault == 'empty': result.turn_scores = []
            elif fault == 'missing': result.turn_scores.pop()
            elif fault == 'duplicate': result.turn_scores.append(result.turn_scores[0])
            elif fault == 'unknown': result.turn_scores[0].turn_index = 999
            elif fault == 'wrong_pillar': result.pillar_id += 999
            elif fault == 'wrong_version': result.pillar_version += 1
            elif fault == 'turn_score': result.turn_scores[0].score = 180
            elif fault == 'no_evidence': result.turn_scores[0].evidence = ''
            return result
    monkeypatch.setattr(services, 'get_ai_provider', lambda _: Invalid())
    asyncio.run(services.process_conversation_job(*args))
    conversation = mdb.get_conversation_by_uuid(args[0], args[2])
    assert conversation['status'] == 'failed'
    detail = mdb.conversation_detail_payload(conversation)
    assert detail['turns'] == detail['pillar_scores'] == detail['telemetry'] == []


@pytest.mark.parametrize('fault', ['empty', 'backwards', 'missing_time', 'duplicate', 'speaker', 'empty_text'])
def test_invalid_transcription_is_rejected(isolated_monitoria, monkeypatch, fault):
    args = _pending_job(isolated_monitoria)
    class Invalid(MockAIProvider):
        async def transcribe(self, *args, **kwargs):
            result = await super().transcribe(*args, **kwargs)
            if fault == 'empty': result.turns = []
            elif fault == 'backwards': result.turns[0].t_end = -1
            elif fault == 'missing_time': result.turns[0].t_start = None
            elif fault == 'duplicate': result.turns[1].turn_index = 0
            elif fault == 'speaker': result.turns[0].speaker = 'unknown'
            elif fault == 'empty_text': result.turns[0].text = ' '
            return result
    monkeypatch.setattr(services, 'get_ai_provider', lambda _: Invalid())
    asyncio.run(services.process_conversation_job(*args))
    assert mdb.get_job(args[0], args[1])['status'] == 'failed'
    assert mdb.list_turns(mdb.get_conversation_by_uuid(args[0], args[2])['id']) == []


def test_second_process_cannot_expire_live_worker_and_snapshot_stays_stable(isolated_monitoria, monkeypatch):
    args = _pending_job(isolated_monitoria, 'slow')
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        class Slow(MockAIProvider):
            async def transcribe(self, *args, **kwargs):
                started.set()
                await release.wait()
                return await super().transcribe(*args, **kwargs)
        monkeypatch.setattr(services, 'get_ai_provider', lambda _: Slow())
        monkeypatch.setattr(services, 'HEARTBEAT_SECONDS', .05)
        task = asyncio.create_task(services.process_conversation_job(*args))
        await asyncio.wait_for(started.wait(), 3)
        initial = mdb.get_job(args[0], args[1])['lease_until']
        pillar = mdb.list_pillars(args[0])[0]
        mdb.update_pillar(args[0], pillar['id'], prompt='Critério alterado durante a execução')
        env = {**os.environ, 'EXPAI_DB_PATH': str(isolated_monitoria['data_dir'] / 'system.sqlite3')}
        try:
            await asyncio.sleep(.12)
            child = await asyncio.to_thread(subprocess.run, [sys.executable, '-c',
                'from app.monitoria_services import cleanup_zombie_monitoria_jobs; print(cleanup_zombie_monitoria_jobs())'],
                env=env, capture_output=True, text=True, timeout=45)
            assert child.returncode == 0, child.stderr
            assert child.stdout.strip() == '0'
            job = mdb.get_job(args[0], args[1])
            assert job['status'] == 'processing' and job['lease_until'] > initial
            assert not mdb.claim_job(*args, 'other-owner')
        finally:
            release.set()
            await asyncio.wait_for(task, 5)
        assert mdb.get_job(args[0], args[1])['status'] == 'completed'
        scores = mdb.list_pillar_scores(mdb.get_conversation_by_uuid(args[0], args[2])['id'])
        assert scores[0]['prompt'] == pillar['prompt']
        assert scores[0]['pillar_version'] == pillar['version']
        # Re-dispatching completed work must not overwrite prior evidence.
        await services.process_conversation_job(*args)
        assert mdb.list_pillar_scores(mdb.get_conversation_by_uuid(args[0], args[2])['id']) == scores
    asyncio.run(run())


def test_expired_owner_cannot_publish_and_cleanup_is_idempotent(isolated_monitoria):
    args = _pending_job(isolated_monitoria, 'expired')
    assert mdb.claim_job(*args, 'old-owner')
    conn = db.get_connection()
    with conn:
        conn.execute('UPDATE monitoria_jobs SET lease_until = ? WHERE job_id = ?', (time.time() - 1, args[1]))
    conn.close()
    assert not mdb.renew_job_lease(args[0], args[1], 'old-owner')
    assert not mdb.complete_job(args[0], args[1], 'old-owner', [], [], [], {})
    assert services.cleanup_zombie_monitoria_jobs() == 1
    assert services.cleanup_zombie_monitoria_jobs() == 0
    assert mdb.get_job(args[0], args[1])['status'] == 'failed'
    assert mdb.get_conversation_by_uuid(args[0], args[2])['status'] == 'failed'
    assert not mdb.fail_owned_job(args[0], args[1], 'old-owner', 'stale error')


def test_simultaneous_claims_have_one_winner(isolated_monitoria):
    args = _pending_job(isolated_monitoria, 'claim')
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda owner: mdb.claim_job(*args, owner), ['a', 'b']))
    assert sorted(outcomes) == [False, True]


def test_concurrent_pillar_versions_are_unique(isolated_monitoria):
    cid = isolated_monitoria['company_id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        versions = list(pool.map(lambda prompt: mdb.create_pillar(cid, 'Empatia', prompt=prompt), ['a', 'b']))
    assert sorted(p['version'] for p in versions) == [1, 2]
    assert len({p['family_id'] for p in versions}) == 1
    assert len(mdb.list_pillars(cid)) == 1


def test_migration_preserves_scores_and_marks_legacy_snapshots_unknown(monitoria_client):
    client, _, base = monitoria_client
    example = client.post(base + '/demo').json()['items'][0]
    detail = client.get(base + '/conversas/' + example['conversation_uuid']).json()
    conn = db.get_connection()
    # Recreate the legacy columns on a disposable database, then rerun initialization twice.
    with conn:
        conn.execute('DROP INDEX idx_monitoria_pillars_family')
        conn.execute('DROP INDEX idx_monitoria_jobs_lease')
        for table, columns in {'monitoria_pillars': ['family_id'], 'monitoria_pillar_scores': ['prompt', 'description'],
            'monitoria_jobs': ['lease_owner', 'lease_until'], 'monitoria_conversations': ['evaluation_config']}.items():
            for column in columns:
                conn.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
    conn.close()
    db.init_db()
    db.init_db()
    restored = client.get(base + '/conversas/' + example['conversation_uuid']).json()
    assert restored['score'] == detail['score']
    assert all(p['snapshot_available'] is False and p['prompt'] is None for p in restored['pillar_scores'])
    assert all(p['family_id'] for p in client.get(base + '/pilares').json()['items'])


def test_database_error_rolls_back_all_result_rows(isolated_monitoria):
    args = _pending_job(isolated_monitoria, 'rollback')
    conn = db.get_connection()
    with conn:
        conn.execute("""CREATE TRIGGER simulate_score_write_failure BEFORE INSERT ON monitoria_turn_scores
            BEGIN SELECT RAISE(ABORT, 'simulated storage failure'); END""")
    conn.close()
    asyncio.run(services.process_conversation_job(*args))
    conversation = mdb.get_conversation_by_uuid(args[0], args[2])
    assert conversation['status'] == 'failed'
    assert mdb.list_turns(conversation['id']) == []
    assert mdb.list_pillar_scores(conversation['id']) == []
    assert mdb.list_turn_scores(conversation['id']) == []


def test_queued_job_has_grace_and_only_expires_after_deadline(isolated_monitoria):
    args = _pending_job(isolated_monitoria, 'queued')
    assert services.cleanup_zombie_monitoria_jobs() == 0
    conn = db.get_connection()
    with conn:
        conn.execute('UPDATE monitoria_jobs SET lease_until = ? WHERE job_id = ?', (time.time() - 1, args[1]))
    conn.close()
    assert services.cleanup_zombie_monitoria_jobs() == 1
    assert not mdb.claim_job(*args, 'late-worker')


def test_inactive_revision_edit_does_not_disable_active_version(isolated_monitoria):
    cid = isolated_monitoria['company_id']
    first = mdb.create_pillar(cid, 'Clareza', prompt='one')
    second = mdb.create_pillar(cid, 'Clareza', prompt='two')
    third = mdb.update_pillar(cid, first['id'], prompt='three')
    assert third['version'] == 3 and not third['is_active']
    assert [p['id'] for p in mdb.list_pillars(cid)] == [second['id']]
