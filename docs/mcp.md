# MCP para Agentes de IA

## Visao geral

O `Expertise.AI` expoe um servidor MCP em Streamable HTTP para que agentes de IA consultem a base estruturada da plataforma.

O componente foi desenhado como uma camada segura sobre o dominio existente:

- usa Bearer token da autenticacao atual;
- revalida empresa, usuario ativo, papeis e restricoes por area a cada chamada;
- expoe somente documentos publicados;
- filtra documentos expirados por padrao;
- usa `document_uuid` como identidade estavel para consumo por agentes;
- limita tamanho de pagina e tamanho maximo de conteudo retornado.

## Endpoint

Por padrao:

```text
POST /mcp/
```

O endpoint usa o transporte MCP `streamable-http`. Alguns clientes podem configurar a URL como `/mcp`; redirecionamento de barra final depende do cliente e do proxy, entao prefira informar `/mcp/` quando possivel.

Status operacional simples:

```text
GET /mcp-status
```

## Autenticacao

O cliente MCP deve enviar:

```text
Authorization: Bearer <access_token>
```

O token e o mesmo retornado por:

```text
POST /api/v1/auth/login
```

O servidor MCP recusa inicializacao quando `EXPAI_ACCESS_CONTROL_ENABLED=false`, a menos que o MCP esteja desabilitado. Isso evita expor conteudo corporativo por uma porta paralela sem controle de acesso.

## Tools disponiveis

### `describe_knowledge_base`

Descreve o escopo visivel para o usuario autenticado em uma empresa.

Entrada principal:

- `company_id`

Retorna usuario efetivo, limites do MCP, areas e categorias visiveis.

### `search_documents`

Busca documentos publicados visiveis para o usuario.

Filtros:

- `company_id`
- `query`
- `area`
- `categoria`
- `tag`
- `data_validade_de` no formato `YYYY-MM-DD`
- `data_validade_ate` no formato `YYYY-MM-DD`
- `include_expired`
- `include_content`
- `limit`
- `offset`
- `sort`

Por padrao, documentos expirados nao sao retornados. `limit` e limitado por `EXPAI_MCP_MAX_PAGE_SIZE`.

### `get_document_metadata`

Retorna metadados publicos de um documento publicado usando `document_uuid`.

Entrada:

- `company_id`
- `document_uuid`
- `include_expired`

### `get_document_content`

Retorna o Markdown de uma versao publicada usando `document_uuid`.

Entrada:

- `company_id`
- `document_uuid`
- `version`, opcional
- `include_expired`

Versoes nao publicadas nunca sao retornadas pelo MCP. O corpo e limitado por `EXPAI_MCP_MAX_CONTENT_CHARS` e a resposta indica `content_truncated` quando houver corte.

### `list_taxonomies`

Lista areas e categorias visiveis para o usuario autenticado.

Entrada:

- `company_id`

## Variaveis de ambiente

- `EXPAI_MCP_ENABLED`: habilita ou desabilita o componente. Padrao: `true`.
- `EXPAI_MCP_REQUIRED`: quando `true`, falha o startup se o MCP nao puder ser montado. Padrao: `false`.
- `EXPAI_MCP_PATH`: caminho de montagem. Padrao: `/mcp`.
- `EXPAI_MCP_ISSUER_URL`: URL declarada como emissor OAuth/MCP. Padrao: `EXPAI_API_BASE_URL`.
- `EXPAI_MCP_RESOURCE_SERVER_URL`: URL publica do recurso MCP. Padrao: `EXPAI_API_BASE_URL + EXPAI_MCP_PATH`.
- `EXPAI_MCP_REQUIRED_SCOPES`: escopos exigidos pelo middleware MCP. Padrao: `kb:read`.
- `EXPAI_MCP_MAX_PAGE_SIZE`: maior pagina permitida em buscas. Padrao: `100`.
- `EXPAI_MCP_MAX_CONTENT_CHARS`: maximo de caracteres retornados por documento. Padrao: `200000`.
- `EXPAI_MCP_MAX_REQUEST_BODY_SIZE`: tamanho maximo do corpo HTTP MCP. Padrao: `1048576`.
- `EXPAI_MCP_MAX_SESSIONS`: limite defensivo de sessoes do transporte. Padrao: `100`.
- `EXPAI_MCP_SESSION_IDLE_TIMEOUT_SECONDS`: timeout defensivo de sessao. Padrao: `1800`.
- `EXPAI_MCP_ALLOWED_HOSTS`: allowlist de `Host` para protecao contra DNS rebinding.
- `EXPAI_MCP_ALLOWED_ORIGINS`: allowlist de `Origin` para clientes em navegador.

Em producao, configure `EXPAI_API_BASE_URL`, `EXPAI_MCP_ALLOWED_HOSTS` e `EXPAI_MCP_ALLOWED_ORIGINS` com o dominio publico real servido pelo proxy.

## Seguranca operacional

- O MCP nao cria, altera, publica ou remove documentos.
- O MCP nao expoe rascunhos nem versoes pendentes.
- O MCP usa `document_uuid`; agentes nao devem depender de `area/categoria/slug` como identidade.
- O backend reconsulta papeis ativos no banco a cada tool call.
- Administradores veem todas as areas; usuarios nao admin respeitam restricoes efetivas por area.
- Leituras de conteudo geram log estruturado com empresa, documento, versao e tamanho retornado.

## Dependencia

O componente usa o SDK oficial MCP para Python na linha `1.x`:

```text
mcp>=1.30.0,<2.0.0
```

A linha `2.x` mudou superficies publicas importantes, por isso a versao esta limitada ate uma migracao planejada.
