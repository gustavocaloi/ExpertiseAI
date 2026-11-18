from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app import config, db, services, monitoria_db as mdb, monitoria_services
from app.security import hash_password


@pytest.fixture()
def isolated_monitoria(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    kb_root = data_dir / "kb_store"
    monitoria_root = data_dir / "monitoria_store"
    db_path = data_dir / "system.sqlite3"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "KB_ROOT", kb_root)
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "MONITORIA_ROOT", monitoria_root)
    monkeypatch.setattr(config, "AI_PROVIDER", "mock")
    monkeypatch.setattr(config, "MONITORIA_REAL_AI_ENABLED", False)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(services, "KB_ROOT", kb_root)
    monkeypatch.setattr(monitoria_services, "MONITORIA_ROOT", monitoria_root)

    db.init_db()
    company_id = db.create_company("Empresa Teste", "empresa-teste", "desc")
    admin_id = db.create_user("Admin", "admin@test.local", hash_password("secret"))
    operator_id = db.create_user("Operador", "op@test.local", hash_password("secret"))
    other_op_id = db.create_user("Outro", "other@test.local", hash_password("secret"))
    db.set_user_roles_in_company(admin_id, company_id, ["admin"])
    db.set_user_roles_in_company(operator_id, company_id, ["editor"])
    db.set_user_roles_in_company(other_op_id, company_id, ["editor"])

    yield {
        "company_id": company_id,
        "admin_id": admin_id,
        "operator_id": operator_id,
        "other_op_id": other_op_id,
        "monitoria_root": monitoria_root,
        "data_dir": data_dir,
    }


def test_init_creates_monitoria_tables(isolated_monitoria):
    conn = db.get_connection()
    try:
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'monitoria_%'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert "monitoria_conversations" in names
    assert "monitoria_pillars" in names
    assert "monitoria_jobs" in names


def test_mock_pipeline_completes_with_turns_and_scores(isolated_monitoria):
    company_id = isolated_monitoria["company_id"]
    operator_id = isolated_monitoria["operator_id"]
    central = mdb.create_central(company_id, "Central A")
    mdb.create_pillar(
        company_id,
        "Empatia",
        description="Avalia empatia",
        prompt="Avalie empatia do operador",
        weight=1.0,
    )
    audio_path = isolated_monitoria["data_dir"] / "sample.wav"
    audio_path.write_bytes(b"RIFF....WAVE")

    async def _run_pipeline():
        result = await monitoria_services.create_conversation_from_upload(
            company_id,
            tmp_audio_path=audio_path,
            audio_filename="sample.wav",
            ticket_id="T-100",
            cliente="Cliente X",
            central_id=int(central["id"]),
            operador_user_id=operator_id,
        )
        job_id = result["job_id"]
        conversation_uuid = result["conversation_uuid"]
        for _ in range(50):
            job = mdb.get_job(company_id, job_id)
            if job and job["status"] in {"completed", "failed"}:
                return job, conversation_uuid
            await asyncio.sleep(0.05)
        return mdb.get_job(company_id, job_id), conversation_uuid

    job, conversation_uuid = asyncio.run(_run_pipeline())
    assert job is not None
    assert job["status"] == "completed"

    conversation = mdb.get_conversation_by_uuid(company_id, conversation_uuid)
    assert conversation is not None
    assert conversation["status"] == "completed"
    detail = mdb.conversation_detail_payload(conversation)
    assert len(detail["turns"]) >= 2
    speakers = {turn["speaker"] for turn in detail["turns"]}
    assert speakers == {"cliente", "operador"}
    assert detail["pillar_scores"]
    assert detail["telemetry"]


def test_scope_hides_other_area_and_other_operator(isolated_monitoria):
    company_id = isolated_monitoria["company_id"]
    operator_id = isolated_monitoria["operator_id"]
    other_op_id = isolated_monitoria["other_op_id"]
    db.create_taxonomy(company_id, "area", "a")
    db.create_taxonomy(company_id, "area", "b")
    db.set_user_area_scope(other_op_id, company_id, "selected", ["b"])
    central_a = mdb.create_central(company_id, "Central A")
    central_b = mdb.create_central(company_id, "Central B")

    conv_a = mdb.create_conversation(
        company_id,
        "uuid-a",
        ticket_id="A",
        cliente="C1", area="a",
        central_id=int(central_a["id"]),
        operador_user_id=operator_id,
        status="completed",
    )
    conv_b = mdb.create_conversation(
        company_id,
        "uuid-b",
        ticket_id="B",
        cliente="C2", area="b",
        central_id=int(central_b["id"]),
        operador_user_id=other_op_id,
        status="completed",
    )

    mdb.create_membership(
        company_id,
        operator_id,
        "monitoria_operador",
        central_id=int(central_a["id"]),
    )
    scope_op = mdb.resolve_monitoria_scope(operator_id, company_id, kb_roles=["editor"])
    assert scope_op.can_access_conversation(conv_a)
    assert not scope_op.can_access_conversation(conv_b)

    listed = mdb.list_conversations(company_id, scope_op)
    uuids = {item["conversation_uuid"] for item in listed["items"]}
    assert "uuid-a" in uuids
    assert "uuid-b" not in uuids

    mdb.create_membership(
        company_id,
        other_op_id,
        "monitoria_supervisor",
        central_id=int(central_b["id"]),
    )
    scope_sup = mdb.resolve_monitoria_scope(other_op_id, company_id, kb_roles=["editor"])
    assert scope_sup.can_access_conversation(conv_b)
    assert not scope_sup.can_access_conversation(conv_a)


@pytest.fixture()
def monitoria_client(isolated_monitoria, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import monitoria_routes, security
    monkeypatch.setattr(monitoria_routes, '_TMP_UPLOADS', isolated_monitoria['data_dir'] / 'uploads')
    monkeypatch.setattr(security, 'ACCESS_CONTROL_ENABLED', True)
    monkeypatch.setattr(monitoria_routes, 'ACCESS_CONTROL_ENABLED', True)
    app = FastAPI()
    app.include_router(monitoria_routes.router, prefix='/api/v1')
    current = {'id': isolated_monitoria['admin_id']}
    def user():
        row = db.get_user_by_id(current['id'])
        roles = db.get_user_roles_in_company(current['id'], isolated_monitoria['company_id'])
        return security.TokenData(sub=str(current['id']), user_id=current['id'],
            company_id=isolated_monitoria['company_id'], role=roles[0], roles=roles, email=row['email'])
    app.dependency_overrides[security.current_user] = user
    with TestClient(app) as client:
        yield client, current, f"/api/v1/empresas/{isolated_monitoria['company_id']}/monitoria"


def test_demo_is_idempotent_and_has_complete_telemetry(monitoria_client, isolated_monitoria):
    client, _, base = monitoria_client
    first = client.post(base + '/demo')
    assert first.status_code == 201, first.text
    assert all(c['status'] == 'completed' for c in first.json()['items'])
    again = client.post(base + '/demo')
    assert [c['conversation_uuid'] for c in first.json()['items']] == [c['conversation_uuid'] for c in again.json()['items']]
    listing = client.get(base + '/conversas', params={'limit': 1}).json()
    assert listing['total'] == listing['summary']['completed'] == 3
    assert len(listing['items']) == 1
    assert listing['summary']['average_score'] is not None
    assert 'audio_path' not in listing['items'][0]
    conv = client.get(base + '/conversas/' + first.json()['items'][0]['conversation_uuid']).json()
    assert conv['is_mock'] is True
    assert len(conv['turns']) == 8
    assert len(conv['pillar_scores']) == 4
    assert len(conv['telemetry']) == 32
    assert all(0 <= t['score'] <= 100 and t['t_start'] is not None for t in conv['telemetry'])
    assert conv['score'] == round(sum(p['score'] * p['weight'] for p in conv['pillar_scores']) / sum(p['weight'] for p in conv['pillar_scores']), 1)
    audio = client.get(base + '/conversas/' + conv['conversation_uuid'] + '/audio')
    assert audio.status_code == 200 and audio.content[:4] == b'RIFF'
    filtered = client.get(base + '/conversas', params={'tipo': 'Suporte', 'analista_user_id': isolated_monitoria['admin_id'], 'pillar_id': conv['pillar_scores'][0]['pillar_id']}).json()
    assert filtered['total'] == filtered['summary']['total'] == 1


def test_jobs_audio_and_upload_follow_scope(monitoria_client, isolated_monitoria):
    client, current, base = monitoria_client
    demo = client.post(base + '/demo').json()['items'][0]
    company = isolated_monitoria['company_id']
    op = isolated_monitoria['operator_id']
    mdb.create_membership(company, op, 'monitoria_operador')
    current['id'] = op
    assert client.get(base + '/conversas').json()['total'] == 0
    for suffix in ['/conversas/' + demo['conversation_uuid'], '/conversas/' + demo['conversation_uuid'] + '/audio', '/jobs/' + demo['job_id']]:
        assert client.get(base + suffix).status_code == 404
    assert client.post(base + '/demo').status_code == 403
    assert client.post(base + '/conversas/upload', files={'file': ('sample.wav', b'RIFF....WAVE', 'audio/wav')}).status_code == 403
    mdb.create_membership(company, op, 'monitoria_supervisor', central_id=mdb.create_central(company, 'Restrita')['id'])
    assert client.get(base + '/jobs').json()['items'] == []
    assert client.post(base + '/conversas/upload', files={'file': ('sample.wav', b'RIFF', 'audio/wav')}).status_code == 403


def test_upload_validation_and_mock_result(monitoria_client, isolated_monitoria):
    client, _, base = monitoria_client
    client.post(base + '/pilares', json={'name': 'Profissionalismo'})
    assert client.post(base + '/conversas/upload', files={'file': ('note.txt', b'hello')}).status_code == 415
    assert client.post(base + '/conversas/upload', files={'file': ('empty.wav', b'')}).status_code == 422
    foreign = db.create_company('Outra', 'outra', '')
    foreign_central = mdb.create_central(foreign, 'Outra central')
    assert client.post(base + '/conversas/upload', data={'central_id': foreign_central['id']}, files={'file': ('file.wav', b'RIFF')}).status_code == 422
    response = client.post(base + '/conversas/upload', data={'ticket_id': 'T-200', 'tipo': 'Suporte'}, files={'file': ('file.wav', b'RIFF....WAVE')})
    assert response.status_code == 202, response.text
    assert 'audio_path' not in response.json()['conversation']
    import time
    for _ in range(50):
        job = client.get(base + '/jobs/' + response.json()['job_id']).json()
        if job['status'] in {'completed', 'failed'}:
            break
        time.sleep(.02)
    assert job['status'] == 'completed'
    assert not list((isolated_monitoria['data_dir'] / 'uploads').iterdir())
    client.put(base + '/ai-settings', json={'is_enabled': False})
    assert client.post(base + '/demo').status_code == 409
    assert client.put(base + '/ai-settings', json={'provider': 'openai'}).status_code == 422
    assert client.post(base + '/pilares', json={'name': 'Inválido', 'weight': -1}).status_code == 422


def test_combined_area_profiles_match_detail_and_listing(isolated_monitoria):
    cid, user = isolated_monitoria['company_id'], isolated_monitoria['operator_id']
    for area in ['a','b','c']:
        db.create_taxonomy(cid, 'area', area)
    db.set_user_modules(user, cid, ['monitoria'], 'monitoria_supervisor')
    db.set_user_area_scope(user, cid, 'selected', ['a','b'])
    for key, area in [('first','a'),('second','b'),('hidden','c'),('legacy','')]:
        mdb.create_conversation(cid,key,area=area,operador_user_id=user)
    scope=mdb.resolve_monitoria_scope(user,cid)
    listed={c['conversation_uuid'] for c in mdb.list_conversations(cid,scope)['items']}
    assert listed=={'first','second'}
    for key in ['first','second','hidden','legacy']:
        assert scope.can_access_conversation(mdb.get_conversation_by_uuid(cid,key))==(key in listed)
    assert not scope.can_access_conversation({'company_id':cid+1,'area':'a'})


def test_pillar_versions_preserve_previous_score_weights(monitoria_client, isolated_monitoria):
    client, _, base = monitoria_client
    example = client.post(base + '/demo').json()['items'][0]
    detail = client.get(base + '/conversas/' + example['conversation_uuid']).json()
    pillar = detail['pillar_scores'][0]
    client.post(base + '/pilares', json={'name': pillar['pillar_name'], 'weight': 99, 'prompt': 'Novo critério'})
    after = client.get(base + '/conversas/' + example['conversation_uuid']).json()
    assert after['score'] == detail['score']
    assert after['pillar_scores'] == detail['pillar_scores']
