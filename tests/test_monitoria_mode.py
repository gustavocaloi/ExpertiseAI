"""Feature flag tests: all adapters are local doubles; no external API calls."""
import asyncio
import os
import subprocess
import sys

import pytest

from app import config, monitoria_db as mdb, monitoria_services as services
from app.ai_providers import registry
from app.ai_providers.mock import MockAIProvider
from test_monitoria import isolated_monitoria, monitoria_client  # noqa: F401


def complete_upload(ctx):
    source = ctx['data_dir'] / 'mode.wav'
    source.write_bytes(b'RIFF....WAVE')

    async def run():
        result = await services.create_conversation_from_upload(ctx['company_id'], tmp_audio_path=source, audio_filename=source.name)
        await asyncio.gather(*list(services._JOB_TASKS))
        return result

    return asyncio.run(run())


def test_disabled_forces_mock_despite_saved_real_provider(isolated_monitoria, monitoria_client, monkeypatch):
    cid = isolated_monitoria['company_id']
    mdb.create_pillar(cid, 'Clareza')
    mdb.upsert_ai_settings(cid, provider='openai')

    class MustNotConstruct:
        def __init__(self):
            raise AssertionError('Real adapter constructed with flag off')

    monkeypatch.setitem(registry._PROVIDERS, 'openai', MustNotConstruct)
    result = complete_upload(isolated_monitoria)
    conv = mdb.get_conversation_by_uuid(cid, result['conversation_uuid'])
    assert result['is_mock'] is True
    assert conv['provider'] == 'mock'
    assert conv['status'] == 'completed'
    assert mdb.conversation_detail_payload(conv)['evaluation_config']['real_ai_enabled'] is False
    assert mdb.get_ai_settings(cid)['provider'] == 'openai'  # configuration preserved
    client, _, base = monitoria_client
    runtime = client.get(base + '/escopo').json()['runtime']
    assert runtime['effective_provider'] == 'mock'
    assert runtime['configured_provider'] == 'openai'
    assert runtime['ready'] is True
    with pytest.raises(ValueError, match='IA real desativada'):
        registry.get_ai_provider('openai')


@pytest.mark.parametrize('provider', ['mock', 'openai', 'anthropic', 'groq'])
def test_real_mode_unconfigured_or_unimplemented_rejects_before_persistence(monitoria_client, isolated_monitoria, monkeypatch, provider):
    monkeypatch.setattr(config, 'MONITORIA_REAL_AI_ENABLED', True)
    cid = isolated_monitoria['company_id']
    client, _, base = monitoria_client
    mdb.create_pillar(cid, 'Clareza')
    assert client.put(base + '/ai-settings', json={'provider': provider}).status_code == 200
    settings = client.get(base + '/ai-settings').json()
    assert settings['runtime']['mode'] == 'real'
    assert settings['runtime']['ready'] is False
    response = client.post(base + '/conversas/upload', files={'file': ('sample.wav', b'RIFF', 'audio/wav')})
    assert response.status_code == 409
    assert client.get(base + '/conversas').json()['total'] == 0
    assert not isolated_monitoria['monitoria_root'].exists()


def test_real_mode_records_provider_with_local_test_adapter(isolated_monitoria, monkeypatch):
    monkeypatch.setattr(config, 'MONITORIA_REAL_AI_ENABLED', True)

    class TestAdapter(MockAIProvider):
        name = 'openai'

    monkeypatch.setitem(registry._PROVIDERS, 'openai', TestAdapter)
    cid = isolated_monitoria['company_id']
    mdb.create_pillar(cid, 'Clareza')
    mdb.upsert_ai_settings(cid, provider='openai')
    result = complete_upload(isolated_monitoria)
    detail = mdb.conversation_detail_payload(mdb.get_conversation_by_uuid(cid, result['conversation_uuid']))
    assert result['is_mock'] is False
    assert detail['status'] == 'completed'
    assert detail['provider'] == 'openai'
    assert detail['evaluation_config']['real_ai_enabled'] is True


def test_disabling_blocks_already_queued_real_job_without_relabeling(isolated_monitoria, monkeypatch):
    cid = isolated_monitoria['company_id']
    mdb.create_pillar(cid, 'Clareza')
    mdb.create_conversation(cid, 'queued-real', provider='openai')
    mdb.create_job(cid, 'real-job', 'queued-real')
    monkeypatch.setattr(services, 'get_ai_provider', lambda _: pytest.fail('Provider must not be constructed'))
    asyncio.run(services.process_conversation_job(cid, 'real-job', 'queued-real'))
    conv = mdb.get_conversation_by_uuid(cid, 'queued-real')
    assert conv['status'] == 'failed'
    assert conv['provider'] == 'openai'
    assert 'IA real desativada' in conv['error_message']
    assert mdb.conversation_detail_payload(conv)['turns'] == []


def test_demo_is_mock_in_real_mode_and_pause_still_applies(monitoria_client, isolated_monitoria, monkeypatch):
    monkeypatch.setattr(config, 'MONITORIA_REAL_AI_ENABLED', True)
    cid = isolated_monitoria['company_id']
    mdb.upsert_ai_settings(cid, provider='openai')
    client, _, base = monitoria_client
    response = client.post(base + '/demo')
    assert response.status_code == 201
    assert all(item['status'] == 'completed' and item['is_mock'] for item in response.json()['items'])
    assert client.put(base + '/ai-settings', json={'is_enabled': False}).status_code == 200
    assert client.post(base + '/demo').status_code == 409
    assert client.post(base + '/conversas/upload', files={'file': ('sample.wav', b'RIFF')}).status_code == 409


@pytest.mark.parametrize('raw, expected', [(None, 'False'), ('false', 'False'), ('true', 'True'), ('1', 'True'), (' YES ', 'True'), ('0', 'False'), ('invalid', 'False')])
def test_feature_flag_env_is_off_by_default(raw, expected):
    env = os.environ.copy()
    env.pop('EXPAI_MONITORIA_REAL_AI_ENABLED', None)
    if raw is not None:
        env['EXPAI_MONITORIA_REAL_AI_ENABLED'] = raw
    result = subprocess.run([sys.executable, '-c', 'from app.config import MONITORIA_REAL_AI_ENABLED; print(MONITORIA_REAL_AI_ENABLED)'], env=env, text=True, capture_output=True, check=True)
    assert result.stdout.strip() == expected
