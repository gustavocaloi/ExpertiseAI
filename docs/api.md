# API Principal

## Autenticacao

- `POST /api/v1/auth/login`
  - autentica usuario e retorna `access_token` e `refresh_token`
- `POST /api/v1/auth/refresh`
  - renova a sessao e retorna novo `access_token` e novo `refresh_token`
- `POST /api/v1/auth/change-password`
  - troca obrigatoria de senha quando aplicavel
- `GET /api/v1/auth/me`
  - retorna sessao atual e perfil efetivo

## Empresas

- `POST /api/v1/empresas`
  - cria empresa e usuario admin inicial

## Documentos

- `GET /api/v1/empresas/{empresa_id}/documentos`
  - lista documentos com suporte a filtros, paginacao e ordenacao
- `GET /api/v1/empresas/{empresa_id}/documentos/publicados`
  - lista somente documentos publicados no contrato original
- `GET /api/v2/empresas/{empresa_id}/documentos/publicados`
  - lista documentos publicados com filtro de validade e metadados de paginacao
- `POST /api/v1/empresas/{empresa_id}/documentos`
  - cria ou atualiza documento via texto
- `POST /api/v1/empresas/{empresa_id}/documentos/upload`
  - importa PDF, DOCX, MD ou TXT
- `PUT /api/v1/empresas/{empresa_id}/documentos/{area}/{categoria}/{slug}/publicar`
  - publica versao especifica
- `GET /api/v1/empresas/{empresa_id}/documentos/{area}/{categoria}/{slug}`
  - lista versoes e metadados do documento
- `GET /api/v1/empresas/{empresa_id}/documentos/{area}/{categoria}/{slug}/conteudo`
  - retorna conteudo da versao publicada por padrao ou de versao especifica via `?version=`

## Taxonomias

- `GET /api/v1/empresas/{empresa_id}/areas`
- `POST /api/v1/empresas/{empresa_id}/areas`
- `DELETE /api/v1/empresas/{empresa_id}/areas`
- `GET /api/v1/empresas/{empresa_id}/categorias`
- `POST /api/v1/empresas/{empresa_id}/categorias`
- `DELETE /api/v1/empresas/{empresa_id}/categorias`

## Usuarios e acessos

- `GET /api/v1/empresas/{empresa_id}/usuarios`
- `POST /api/v1/empresas/{empresa_id}/usuarios`
- `PUT /api/v1/empresas/{empresa_id}/usuarios/{usuario_id}/acessos`
- `DELETE /api/v1/empresas/{empresa_id}/usuarios/{usuario_id}/acessos`
- `GET /api/v1/empresas/{empresa_id}/usuarios/auditoria`
  - suporta `limit` e `offset`

## Restricao por area

- `GET /api/v1/empresas/{empresa_id}/usuarios/{usuario_id}/areas-acesso`
- `PUT /api/v1/empresas/{empresa_id}/usuarios/{usuario_id}/areas-acesso`
- `GET /api/v1/empresas/{empresa_id}/perfis-restricao-areas`
- `POST /api/v1/empresas/{empresa_id}/perfis-restricao-areas`
- `DELETE /api/v1/empresas/{empresa_id}/perfis-restricao-areas/{profile_id}`

## Filtros suportados na listagem de documentos

- `area`
- `categoria`
- `tag`
- `busca` (FTS5 sobre titulo, tags e corpo; paginacao aplicada apos o match)
- `limit`
- `offset`
- `sort` (`created_desc`, `created_asc`, `validade_*`, `area_asc`, `categoria_asc`, `relevance` quando ha `busca`)

Na rota versionada `GET /api/v2/empresas/{empresa_id}/documentos/publicados`, tambem existe:

- `data_validade_ate` (quando informado, retorna documentos sem `data_validade` ou com `data_validade <= dd/mm/aaaa`; quando omitido, retorna documentos sem `data_validade` ou com `data_validade >= hoje`)

Exemplo para documentos publicados com validade ate 31/12/2026:

```text
GET /api/v2/empresas/{empresa_id}/documentos/publicados?data_validade_ate=31/12/2026
```

## Paginacao de documentos publicados

A rota `GET /api/v2/empresas/{empresa_id}/documentos/publicados` usa `limit` e `offset`.

Exemplo da primeira pagina:

```text
GET /api/v2/empresas/{empresa_id}/documentos/publicados?limit=100&offset=0
```

A resposta inclui metadados para buscar todas as paginas:

```json
{
  "total": 250,
  "limit": 100,
  "offset": 0,
  "pagination": {
    "page": 1,
    "page_size": 100,
    "total_pages": 3,
    "has_next": true,
    "has_previous": false,
    "next_offset": 100,
    "previous_offset": null
  },
  "documentos": []
}
```

Para retornar todos os documentos publicados, repita a chamada usando `pagination.next_offset` enquanto `pagination.has_next` for `true`.

## Campo `data_validade`

Nas rotas de criacao e upload de documento, a data de validade deve ser enviada no campo:

- `data_validade`

Formato esperado:

- `YYYY-MM-DD`

Exemplos:

### Criacao via JSON

```json
{
  "title": "Politica de Ferias",
  "content": "# Politica de Ferias",
  "data_validade": "2026-12-31"
}
```

### Upload via multipart/form-data

```bash
-F "data_validade=2026-12-31"
```

## Monitoria

Prefixo: `/api/v1/empresas/{company_id}/monitoria`

- `GET /escopo` — escopo efetivo do usuario no modulo
- `GET|POST /centrais`, `PATCH /centrais/{id}`
- `GET|POST /equipes`, `PATCH /equipes/{id}`
- `GET|POST /memberships`, `DELETE /memberships/{id}`
- `GET|POST /pilares`, `PATCH /pilares/{id}`
- `GET|PUT /ai-settings` — provider/modelos (secrets ficam em env)
- `POST /conversas/upload` — multipart (`file`, `ticket_id`, `cliente`, `central_id`, `operador_user_id`, ...)
- `GET /jobs`, `GET /jobs/{job_id}`
- `GET /conversas` — filtros: central, equipe, cliente, operador, status, periodo
- `GET /conversas/{conversation_uuid}` — turnos, scores e telemetria

Na fase 1 o provedor padrao e `mock` (`EXPAI_AI_PROVIDER=mock`).

## Observacoes

- as rotas respeitam contexto de empresa;
- administradores nao sofrem restricao por area;
- a publicacao exige perfil `aprovador` ou `admin`;
- o modulo de monitoria usa papeis proprios e filtra por central/equipe/operador.

Detalhes do MVP, endpoint `POST /demo`, áudio autenticado e novos filtros/indicadores: [Monitoria](monitoria.md).


### Correções de integridade da Monitoria

- `PATCH /pilares/{id}` cria automaticamente outra versão quando descrição, prompt ou peso mudam; o ID retornado pode ser diferente. Alterações apenas de `is_active` preservam a versão. Existe no máximo uma versão ativa por pilar.
- `GET /pilares?active_only=false` inclui versões anteriores e retorna `family_id`. Em `/conversas`, `pillar_family_id` busca todas as versões; `pillar_id` continua representando uma versão exata.
- `/conversas/upload` retorna 409 se não houver pilar ativo. Não cria pilar implícito.
- O detalhe contém cópia de `prompt`/`description` nos scores, `snapshot_available` e `evaluation_config`. Cópias históricas inexistentes ficam indisponíveis, sem reconstrução presumida.
- Resultados incompletos/inválidos não são publicados como sucesso. Jobs possuem leases persistidas; reexecuções acidentais de jobs concluídos são ignoradas.


### Monitoria: modo efetivo de processamento

`EXPAI_MONITORIA_REAL_AI_ENABLED=false` força mocks para novos uploads sem alterar a configuração persistida da empresa. Com `true`, o upload exige um adapter real disponível e retorna 409 antes de persistir arquivos/jobs se faltar configuração ou implementação. As rotas de demonstração continuam explicitamente mockadas. `is_enabled=false` pausa ambos os modos.

As respostas de `GET /escopo` e `GET/PUT /ai-settings` incluem `runtime` com `real_ai_enabled`, `mode`, `configured_provider`, `effective_provider`, `ready` e `reason`. O estado é informativo e controlado pelo ambiente do servidor; clientes não podem ativar a flag enviando campos no payload. `PUT /ai-settings` rejeita provedores desconhecidos e, com a flag desligada, seleção explícita de provedor diferente de `mock`. É possível alterar apenas `is_enabled` preservando um provedor real previamente salvo.

Veja os exemplos e o comportamento de jobs existentes em [flag de IA real](monitoria.md#flag-de-ia-real).


### Monitoria: upload em lote

`POST /api/v1/empresas/{company_id}/monitoria/conversas/upload-lote` aceita `multipart/form-data` com `files` repetido e `metadata` contendo um array JSON na mesma ordem. Os metadados permitidos são `ticket_id`, `cliente`, `tipo`, `area`, `categoria`, `operador_user_id` e `analista_user_id`. IDs são inteiros positivos ou `null`. Campos desconhecidos rejeitam o item.

```bash
# Reutilize este UUID somente para repetir exatamente o mesmo envio.
curl -X POST "$BASE_URL/api/v1/empresas/$COMPANY_ID/monitoria/conversas/upload-lote" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F 'request_id=4b9a06eb-42d6-420c-aa8c-c9daf2f4e8ae' \
  -F 'files=@/caminho/atendimento-1.wav' \
  -F 'files=@/caminho/atendimento-2.mp3' \
  -F 'metadata=[{"ticket_id":"T-001","cliente":"Cliente A"},{"ticket_id":"T-002","cliente":"Cliente B"}]'
```

HTTP **202** devolve `batch_id`, `status`, `total`, `counts` e `items`. Cada item inclui `index`, `filename`, `status`, `error_message` e, quando aceito, `conversation_uuid` e `job_id`. `rejected` significa que o arquivo não entrou na fila; `failed` significa falha de processamento. A resposta pode conter rejeições parciais, inclusive todos os itens rejeitados.

Consulte `GET /lotes/{batch_id}` até `completed` ou `completed_with_errors`; `GET /lotes?limit=20` recupera envios recentes. Use o mesmo prefixo da Monitoria e Bearer token nas consultas. Não confunda aceitação 202 com conclusão.

Limites: 20 arquivos, 25 MiB por arquivo, 200 MiB somados e 64 KiB de JSON. Excesso de quantidade/tamanho total retorna 413; JSON inválido ou quantidade divergente retorna 422; configuração indisponível ou chave de idempotência conflitante retorna 409. Arquivos inválidos e metadados individuais sem permissão são rejeitados por item. `request_id` é opcional no REST, mas deve ser enviado para repetir uma tentativa sem duplicação. A chave é isolada por empresa e autor.

O endpoint individual `/conversas/upload` continua disponível. Os limites de fila, retomada e concorrência do lote estão em [operação assíncrona](monitoria.md#envio-em-lote-e-processamento-assíncrono).


### Módulos por usuário e taxonomias compartilhadas

`POST /empresas/{company_id}/usuarios` e `PUT /empresas/{company_id}/usuarios/{user_id}/acessos` aceitam `modules` e `monitoria_role`. Exemplo de atualização (inclua os perfis que deseja manter):

```json
{"roles":["editor"],"modules":["monitoria"],"monitoria_role":"monitoria_analista"}
```

Na Monitoria, envie `area` e `categoria` nos metadados individuais e de lote; os filtros de `/conversas` aceitam ambos. Consulte `GET /monitoria/taxonomias` no prefixo da empresa para obter opções autorizadas. `PATCH /monitoria/conversas/{uuid}/taxonomia` recebe `{"area":"suporte","categoria":"duvidas"}` e exige administração global do módulo. As conversas antigas sem classificação não são expostas a usuários restritos.

Novos envios usando central/equipe são rejeitados. Rotas de criação/alteração de centrais/equipes e criação de memberships retornam 410. Permissões agora são definidas na Gestão de Acessos e utilizam as restrições de áreas existentes. A desativação de um módulo bloqueia suas APIs e tools MCP com 403, independentemente do papel de conteúdo.

## Backup global (administradores)

- `GET /api/v1/admin/backup/status`: permissão, formato e limite do backup.
- `POST /api/v1/admin/backup/export`: download completo em JSON.
- `POST /api/v1/admin/backup/restore`: importa multipart `file` com `confirmation=RESTAURAR` e substitui a instalação inteira.

Exigem perfil `admin` ativo em todas as empresas, com controle de acesso habilitado. A restauração invalida sessões anteriores. Veja [backup e restauração](backup.md) para contratos, compatibilidade e tratamento de falhas.
