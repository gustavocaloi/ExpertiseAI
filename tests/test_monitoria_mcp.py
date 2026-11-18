import asyncio
import base64
import json
import uuid
from contextlib import asynccontextmanager

import pytest
pytest.importorskip('mcp')

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.fastmcp.exceptions import ToolError
from app import db, mcp_server, monitoria_db as mdb, monitoria_routes as routes, security
from test_monitoria import isolated_monitoria  # noqa: F401


@pytest.fixture()
def mcp_app(isolated_monitoria, monkeypatch):
    monkeypatch.setattr(mcp_server, 'MCP_ENABLED', True)
    monkeypatch.setattr(mcp_server, 'ACCESS_CONTROL_ENABLED', True)
    monkeypatch.setattr(security, 'ACCESS_CONTROL_ENABLED', True)
    monkeypatch.setattr(routes, 'ACCESS_CONTROL_ENABLED', True)
    monkeypatch.setattr(routes, '_TMP_UPLOADS', isolated_monitoria['data_dir'] / 'uploads')
    app = FastAPI()
    app.include_router(routes.router, prefix='/api/v1')
    component = mcp_server.create_mcp_component(openapi_provider=app.openapi)
    app.mount('/mcp', component.app)
    return app, component


def caller(ctx, component):
    async def call(tool_name, **args):
        user_id = args.pop('_user_id', ctx['admin_id'])
        token = AccessToken(token='test-token', client_id='test', scopes=['kb:read'], subject=str(user_id),
            claims={'user_id': user_id, 'company_id': ctx['company_id'], 'email': 'test@local'})
        marker = auth_context_var.set(AuthenticatedUser(token))
        try:
            tool = component.server._tool_manager.get_tool(tool_name)
            return await tool.run({'company_id': ctx['company_id'], **args})
        finally:
            auth_context_var.reset(marker)
    return call


def test_mcp_schema_registration_and_manifest_uses_actual_api(mcp_app, isolated_monitoria):
    app, component = mcp_app
    call = caller(isolated_monitoria, component)
    async def run():
        tools = {tool.name: tool for tool in await component.server.list_tools()}
        assert len(tools) == 23
        assert tools['monitoria_submit_audio_batch'].annotations.readOnlyHint is False
        assert tools['integration_prepare_monitoria_upload'].annotations.readOnlyHint is True
        before = await call('integration_prepare_monitoria_upload', files=[{'filename': 'a.wav', 'size_bytes': 100}])
        assert before['can_submit'] is False
        await call('monitoria_create_pillar', name='Clareza', prompt='Avalie clareza')
        plan = await call('integration_prepare_monitoria_upload', files=[{'filename': 'a.wav', 'size_bytes': 100, 'metadata': {'ticket_id': 'T-1'}}])
        assert plan['can_submit'] is True and plan['runtime']['mode'] == 'mock'
        assert plan['request']['fields']['request_id']
        assert mdb.list_batches(isolated_monitoria['company_id'], mdb.resolve_monitoria_scope(isolated_monitoria['admin_id'], isolated_monitoria['company_id'], kb_roles=['admin'])) == []
        catalogue = await call('integration_list_api_operations', query='upload-lote')
        assert catalogue['total'] == 1
        operation_id = catalogue['items'][0]['operation_id']
        contract = await call('integration_get_api_contract', operation_id=operation_id)
        assert contract['operation'] == app.openapi()['paths'][catalogue['items'][0]['path']]['post']
        assert 'multipart/form-data' in contract['operation']['requestBody']['content']
        assert contract['schemas']
        with pytest.raises(ToolError):
            await call('integration_get_api_contract', operation_id='not-found')
    asyncio.run(run())


def test_mcp_company_role_and_live_revocation(mcp_app, isolated_monitoria):
    _, component = mcp_app
    cid, user = isolated_monitoria['company_id'], isolated_monitoria['operator_id']
    call = caller(isolated_monitoria, component)
    async def run():
        with pytest.raises(ToolError):
            await call('monitoria_describe', _user_id=user)
        membership = mdb.create_membership(cid, user, 'monitoria_operador')
        assert (await call('monitoria_describe', _user_id=user))['scope']['operator_only']
        with pytest.raises(ToolError):
            await call('monitoria_create_pillar', _user_id=user, name='Forbidden', prompt='X')
        with pytest.raises(ToolError):
            await call('monitoria_get_settings', _user_id=user)
        with pytest.raises(ToolError):
            await call('monitoria_describe', company_id=cid + 99)
        mdb.deactivate_membership(cid, membership['id'])
        with pytest.raises(ToolError):
            await call('monitoria_describe', _user_id=user)
        assert mdb.list_pillars(cid) == []
    asyncio.run(run())


def test_mcp_submit_poll_scores_and_replay(mcp_app, isolated_monitoria):
    _, component = mcp_app
    call = caller(isolated_monitoria, component)
    async def run():
        pillar = await call('monitoria_create_pillar', name='Clareza', prompt='Avalie clareza')
        await call('monitoria_update_pillar', pillar_id=pillar['id'], prompt='Novo critério')
        pillars = await call('monitoria_list_pillars')
        assert len(pillars['items']) == 2
        key = str(uuid.uuid4())
        files = [{'filename': 'a.wav', 'audio_base64': base64.b64encode(b'RIFF....WAVE').decode(), 'metadata': {'ticket_id': 'MCP-1'}}]
        batch = await call('monitoria_submit_audio_batch', files=files, request_id=key)
        assert batch['counts']['queued'] == 1
        assert (await call('monitoria_submit_audio_batch', files=files, request_id=key))['batch_id'] == batch['batch_id']
        for _ in range(100):
            batch = await call('monitoria_get_batch', batch_id=batch['batch_id'])
            if batch['status'] == 'completed':
                break
            await asyncio.sleep(.02)
        assert batch['status'] == 'completed'
        conv = await call('monitoria_get_conversation', conversation_uuid=batch['items'][0]['conversation_uuid'], page_size=2)
        assert len(conv['turns']) == 2 and conv['next_turn_offset'] == 2
        assert len(conv['telemetry']) == 2
        assert conv['pillar_scores'][0]['pillar_version'] == 2
        assert 'audio_path' not in json.dumps(conv)
        job = await call('monitoria_get_job', job_id=batch['items'][0]['job_id'])
        assert job['status'] == 'completed' and 'lease_owner' not in job
        assert (await call('monitoria_list_batches'))['items'][0]['batch_id'] == batch['batch_id']
        assert (await call('monitoria_search_conversations'))['total'] == 1
        user = isolated_monitoria['operator_id']
        mdb.create_membership(isolated_monitoria['company_id'], user, 'monitoria_operador')
        with pytest.raises(ToolError):
            await call('monitoria_get_conversation', _user_id=user, conversation_uuid=conv['conversation_uuid'])
        with pytest.raises(ToolError):
            await call('monitoria_get_job', _user_id=user, job_id=batch['items'][0]['job_id'])
    asyncio.run(run())


@pytest.mark.parametrize('encoded', ['%%%INVALID', base64.b64encode(b'x' * (513 * 1024)).decode()])
def test_mcp_rejects_bad_or_large_inline_audio(mcp_app, isolated_monitoria, encoded):
    _, component = mcp_app
    call = caller(isolated_monitoria, component)
    async def run():
        with pytest.raises(ToolError):
            await call('monitoria_submit_audio_batch', files=[{'filename': 'a.wav', 'audio_base64': encoded}], request_id=str(uuid.uuid4()))
        assert (await call('monitoria_list_batches'))['items'] == []
    asyncio.run(run())


def test_streamable_http_auth_and_tool_call(mcp_app, isolated_monitoria):
    app, component = mcp_app
    @asynccontextmanager
    async def lifespan(app):
        async with component.server.session_manager.run():
            yield
    app.router.lifespan_context = lifespan
    token = security.create_access_token(isolated_monitoria['admin_id'], isolated_monitoria['company_id'], 'admin', 'admin@test.local')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream'}
    with TestClient(app, base_url='http://127.0.0.1:8000') as client:
        body = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'monitoria_describe', 'arguments': {'company_id': isolated_monitoria['company_id']}}}
        assert client.post('/mcp/', json=body, headers={'Accept': headers['Accept']}).status_code == 401
        result = client.post('/mcp/', json=body, headers=headers)
        assert result.status_code == 200, result.text
        assert 'real_ai_enabled' in result.text and 'isError":true' not in result.text


def test_module_grants_apply_to_kb_and_monitoria_tools(mcp_app, isolated_monitoria):
    _, component = mcp_app
    cid, uid = isolated_monitoria['company_id'], isolated_monitoria['operator_id']
    call = caller(isolated_monitoria, component)
    db.create_taxonomy(cid, 'area', 'suporte')
    db.create_taxonomy(cid, 'categoria', 'duvidas', 'suporte')
    db.set_user_modules(uid, cid, ['monitoria'], 'monitoria_analista')
    async def run():
        assert (await call('monitoria_list_taxonomies', _user_id=uid))['areas']==['suporte']
        for tool, args in [('describe_knowledge_base', {}), ('search_documents', {}), ('get_document_metadata', {'document_uuid':'missing'}), ('get_document_content', {'document_uuid':'missing'}), ('list_taxonomies', {})]:
            with pytest.raises(ToolError, match='sem acesso ao módulo'):
                await call(tool, _user_id=uid, **args)
        db.set_user_modules(uid,cid,['conteudo'])
        with pytest.raises(ToolError):
            await call('monitoria_list_taxonomies',_user_id=uid)
        assert (await call('list_taxonomies',_user_id=uid)) is not None
    asyncio.run(run())
