import asyncio
import json
import uuid

from app import db, monitoria_db as mdb, security, kb_routes, routers
from test_monitoria import isolated_monitoria, monitoria_client  # noqa: F401


def setup_user(ctx, modules=('monitoria',), role='monitoria_analista'):
    cid, uid = ctx['company_id'], ctx['operator_id']
    db.create_taxonomy(cid, 'area', 'suporte')
    db.create_taxonomy(cid, 'area', 'financeiro')
    db.create_taxonomy(cid, 'categoria', 'duvidas', 'suporte')
    db.create_taxonomy(cid, 'categoria', 'pagamentos', 'financeiro')
    db.set_user_modules(uid, cid, list(modules), role)
    db.set_user_area_scope(uid, cid, 'selected', ['suporte'])
    return cid, uid


def test_modules_enforced_on_rest_and_session(monitoria_client, isolated_monitoria, monkeypatch):
    client, current, base = monitoria_client
    monkeypatch.setattr(routers, 'ACCESS_CONTROL_ENABLED', True)
    client.app.include_router(kb_routes.router, prefix='/api/v1')
    client.app.include_router(routers.router, prefix='/api/v1')
    cid, uid = setup_user(isolated_monitoria)
    current['id'] = uid
    assert client.get('/api/v1/auth/me').json()['modules'] == ['monitoria']
    assert client.get(f'/api/v1/empresas/{cid}/documentos').status_code == 403
    assert client.get(base + '/conversas').status_code == 200
    assert client.get(base + '/taxonomias').json() == {'areas': ['suporte'], 'categorias': [{'name': 'duvidas', 'area': 'suporte'}]}
    # Changing grants takes effect with the same authenticated user/token.
    db.set_user_modules(uid, cid, ['conteudo'])
    assert client.get(base + '/conversas').status_code == 403
    assert client.get(base + '/escopo').status_code == 403
    assert client.get(f'/api/v1/empresas/{cid}/documentos').status_code == 200
    db.set_user_modules(uid, cid, [])
    assert client.get(f'/api/v1/empresas/{cid}/documentos').status_code == 403
    assert client.get(base + '/pilares').status_code == 403


def test_access_management_sets_modules_and_audits(monitoria_client, isolated_monitoria, monkeypatch):
    client, current, base = monitoria_client
    monkeypatch.setattr(routers, 'ACCESS_CONTROL_ENABLED', True)
    client.app.include_router(routers.router, prefix='/api/v1')
    cid, uid = setup_user(isolated_monitoria)
    created = client.post(f'/api/v1/empresas/{cid}/usuarios',json={'full_name':'Novo','email':'new@test.local','password':'Test@12345','role':'editor','modules':['monitoria'],'monitoria_role':'monitoria_operador'})
    assert created.status_code == 200, created.text
    new_id = created.json()['usuario_id']
    assert db.get_user_modules(new_id,cid)['modules'] == ['monitoria']
    assert client.put(f'/api/v1/empresas/{cid}/usuarios/{new_id}/areas-acesso',json={'mode':'selected','areas':['suporte'],'profile_ids':[]}).status_code == 200
    path = f'/api/v1/empresas/{cid}/usuarios/{uid}/acessos'
    response = client.put(path, json={'roles': ['editor'], 'modules': ['conteudo','monitoria'], 'monitoria_role':'monitoria_supervisor'})
    assert response.status_code == 200, response.text
    assert response.json()['modules'] == ['conteudo','monitoria']
    assert db.get_user_modules(uid, cid)['monitoria_role'] == 'monitoria_supervisor'
    assert client.put(path, json={'roles':['editor'],'modules':['invalid']}).status_code == 422
    current['id'] = uid
    assert client.put(path, json={'roles':['admin'],'modules':['conteudo']}).status_code == 403


def test_area_scope_covers_list_detail_audio_jobs_and_batch(monitoria_client, isolated_monitoria):
    client, current, base = monitoria_client
    cid, uid = setup_user(isolated_monitoria)
    mdb.create_pillar(cid, 'Clareza')
    current['id'] = uid
    response = client.post(base+'/conversas/upload-lote', files=[('files',('a.wav',b'RIFF')),('files',('b.wav',b'RIFF'))],
        data={'request_id':str(uuid.uuid4()),'metadata':json.dumps([{'area':'suporte','categoria':'duvidas'},{'area':'financeiro'}])})
    assert response.status_code == 202, response.text
    batch = response.json()
    assert batch['counts']['rejected'] == 1
    uuid_ = batch['items'][0]['conversation_uuid']
    conv = client.get(base+'/conversas/'+uuid_).json()
    assert conv['area'] == 'suporte' and conv['categoria'] == 'duvidas'
    assert client.get(base+'/conversas',params={'area':'financeiro'}).json()['total'] == 0
    db.set_user_area_scope(uid,cid,'selected',['financeiro'])
    assert client.get(base+'/conversas/'+uuid_).status_code == 404
    assert client.get(base+'/conversas/'+uuid_+'/audio').status_code == 404
    assert client.get(base+'/jobs/'+batch['items'][0]['job_id']).status_code == 404
    assert client.get(base+'/lotes/'+batch['batch_id']).json()['total'] == 1


def test_category_validation_and_legacy_classification(monitoria_client, isolated_monitoria):
    client, current, base = monitoria_client
    cid, uid = setup_user(isolated_monitoria)
    mdb.create_pillar(cid,'Clareza')
    response=client.post(base+'/conversas/upload',files={'file':('a.wav',b'RIFF')},data={'area':'suporte','categoria':'pagamentos'})
    assert response.status_code == 422
    mdb.create_conversation(cid,'legacy',ticket_id='old')
    current['id']=uid
    assert client.get(base+'/conversas/legacy').status_code == 404
    assert client.patch(base+'/conversas/legacy/taxonomia',json={'area':'suporte'}).status_code == 403
    current['id']=isolated_monitoria['admin_id']
    response=client.patch(base+'/conversas/legacy/taxonomia',json={'area':'suporte','categoria':'duvidas'})
    assert response.status_code == 200 and response.json()['conversation_uuid']=='legacy'
    assert response.json()['ticket_id']=='old'
    current['id']=uid
    assert client.get(base+'/conversas/legacy').status_code==200
    db.init_db()
    assert mdb.get_conversation_by_uuid(cid,'legacy')['area']=='suporte'


def test_operator_is_intersection_of_own_and_allowed_area(isolated_monitoria):
    cid, uid=setup_user(isolated_monitoria,role='monitoria_operador')
    for key, area, operator in [('own','suporte',uid),('outside','financeiro',uid),('other','suporte',isolated_monitoria['other_op_id'])]:
        mdb.create_conversation(cid,key,area=area,operador_user_id=operator)
    scope=mdb.resolve_monitoria_scope(uid,cid)
    assert [c['conversation_uuid'] for c in mdb.list_conversations(cid,scope)['items']]==['own']
    assert all(scope.can_access_conversation(mdb.get_conversation_by_uuid(cid,key))==(key=='own') for key in ['own','outside','other'])
