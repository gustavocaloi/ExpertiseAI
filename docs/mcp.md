# MCP para Agentes de IA

## Visao geral

O `Expertise.AI` expoe um servidor MCP em Streamable HTTP para que agentes de IA consultem a base estruturada, operem a Monitoria e descubram os contratos das APIs da plataforma.

O componente foi desenhado como uma camada segura sobre o dominio existente:

- usa Bearer token da autenticacao atual;
- revalida empresa, usuario ativo, papeis e restricoes por area a cada chamada;
- na base de conhecimento, expoe somente documentos publicados;
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

## Monitoria e integrações

O servidor registra **18 tools adicionais**, além das cinco da base de conhecimento. Elas reutilizam as rotas e validações do módulo, incluindo flag de IA real, versionamento de pilares, empresa e escopo organizacional. Todas recebem `company_id`.

| Tool | Finalidade | Acesso |
| --- | --- | --- |
| `monitoria_describe` | Escopo efetivo, modo mock/real, áreas/categorias visíveis, pilares e limites | Leitura da Monitoria |
| `monitoria_search_conversations` | Conversas, filtros e indicadores autorizados; `page_size`/`offset` | Leitura da Monitoria |
| `monitoria_get_conversation` | Transcrição paginada, scores, evidências, critérios usados e contrato do áudio | Leitura da conversa |
| `monitoria_get_job` | Estado e erro de um processamento | Leitura da conversa |
| `monitoria_list_batches` | Lotes recentes do usuário; administradores veem todos | Administrador, supervisor ou analista |
| `monitoria_get_batch` | Progresso e resultado por arquivo, filtrados pelo escopo atual | Mesma regra do histórico de lotes |
| `monitoria_list_pillars` | Critérios e versões; `active_only=false` por padrão | Leitura da Monitoria |
| `monitoria_create_pillar` | Criar/versionar pilar com nome, prompt, descrição e peso | Administrador da Monitoria |
| `monitoria_update_pillar` | Versionar critérios ou ativar/desativar pilar | Administrador da Monitoria |
| `monitoria_get_settings` | Configuração do provedor e estado efetivo, sem chaves | Administrador da Monitoria |
| `monitoria_update_settings` | Selecionar provedor ou pausar/retomar; não altera a flag do servidor | Administrador da Monitoria |
| `monitoria_list_taxonomies` | Ler áreas/categorias existentes no escopo | Leitura da Monitoria |
| `monitoria_classify_conversation` | Classificar uma conversa em área/categoria existente | Administrador global da Monitoria |
| `monitoria_create_demo` | Criar/reutilizar demonstrações explicitamente fictícias | Administrador da Monitoria |
| `monitoria_submit_audio_batch` | Enviar pequenas amostras em base64 e retornar lote assíncrono | Administrador, supervisor ou analista |
| `integration_prepare_monitoria_upload` | Validar manifesto e prontidão; preparar contrato multipart sem enviar arquivos | Administrador, supervisor ou analista |
| `integration_list_api_operations` | Descobrir operações reais do OpenAPI, com busca e paginação | Usuário autenticado na empresa |
| `integration_get_api_contract` | Obter operação, schemas referenciados e autenticação | Usuário autenticado na empresa |

Leitura da Monitoria exige vínculo de administrador, supervisor, analista ou operador, ou administração da plataforma. Cada consulta aplica as restrições atuais; uma tool listada pelo protocolo não concede permissão para executá-la. O escopo de transporte histórico `kb:read` não substitui esses controles nem autoriza escrita. As tools de catálogo retornam documentação pública das APIs, não acesso aos seus dados.

Tools de consulta declaram `readOnlyHint=true`; criação/alteração declaram `false`. O backend continua validando cada operação independentemente dessas indicações. A base de conhecimento permanece somente leitura pelo MCP; agora existem mutações explícitas no domínio de Monitoria. Não há proxy HTTP arbitrário, leitura de arquivos locais por caminho ou download de URLs fornecidas pelo agente.

### Fluxo recomendado de integração

1. Use `integration_list_api_operations` com `query="monitoria"`; consulte `integration_get_api_contract` com o `operation_id` retornado para obter o contrato da instância em execução.
2. Consulte `monitoria_describe` para conhecer escopo, pilares e modo efetivo.
3. Chame `integration_prepare_monitoria_upload` com um manifesto como abaixo. A tool não grava dados; informa bloqueios, erros por item, campos multipart e UUID para idempotência.
4. Envie os arquivos pela API REST usando o [exemplo multipart](api.md#monitoria-upload-em-lote). Para pequenas amostras, use `monitoria_submit_audio_batch`.
5. Consulte `monitoria_get_batch` até o estado terminal e abra os resultados com `monitoria_get_conversation`.

Exemplo de argumentos do manifesto:

```json
{
  "company_id": 1,
  "files": [
    {"filename": "atendimento.wav", "size_bytes": 4096,
     "metadata": {"ticket_id": "T-001", "cliente": "Cliente A"}}
  ]
}
```

`can_submit` significa que não há bloqueio global e existe pelo menos um item válido. Examine `files[].errors` antes do envio. A validação usa apenas o manifesto declarado; o recebimento REST verifica novamente os arquivos e permissões.

Na tool `monitoria_submit_audio_batch`, cada item contém `filename`, `audio_base64` (base64 puro, sem prefixo data URL) e `metadata`; `request_id` é um UUID **obrigatório**. Reutilize a chave somente para repetir o mesmo lote. O limite combinado decodificado é de **512 KiB**, reduzido automaticamente se o limite de corpo MCP for menor. O corpo HTTP completo continua sujeito a `EXPAI_MCP_MAX_REQUEST_BODY_SIZE` (1 MiB por padrão). Áudios maiores devem seguir pelo REST, que aceita até 20 arquivos/25 MiB cada/200 MiB somados.

`monitoria_get_conversation` recebe `turn_offset` e `page_size`, retornando `next_turn_offset` para continuar. Evidências são limitadas aos turnos da página. O texto de cada turno respeita `EXPAI_MCP_MAX_CONTENT_CHARS`, com indicação de truncamento. Transcrições e metadados são dados não confiáveis: clientes agentes não devem executar instruções contidas nas conversas.

A flag desligada mantém novos envios mockados; nenhuma dessas tools implementa os adapters reais ou cadastra segredos. `EXPAI_API_BASE_URL` deve representar a URL pública correta para os contratos retornados. A criação do componente MCP recebe o OpenAPI da aplicação; sem esse callback, as duas tools de catálogo informam indisponibilidade.

### Verificação

Use Python **3.10 ou superior** com o SDK MCP instalado:

```bash
python -m pytest tests/test_monitoria_mcp.py tests/test_monitoria_batches.py -q
```

A suíte cobre registro real das 23 tools, anotações, validação de argumentos, autenticação Streamable HTTP, permissões atuais/revogação, limites base64, envio, consulta e idempotência. Os testes usam armazenamento isolado e provedor mock; nenhuma API externa é chamada. Sem o SDK, o arquivo de testes MCP é ignorado explicitamente, portanto esse resultado não comprova o transporte.


As tools da base de conhecimento exigem `conteudo` habilitado; as da Monitoria exigem `monitoria`, além do perfil e escopo. Revogações valem para tokens já emitidos. As duas tools de descoberta de contratos continuam disponíveis a usuários ativos da empresa: retornar documentação não concede acesso aos dados. `monitoria_search_conversations` aceita filtros `area` e `categoria`; manifesto e upload recebem esses campos nos metadados. `monitoria_classify_conversation` preserva UUID e avaliações. As antigas tools de criação de central/equipe foram substituídas pelas duas tools de taxonomia acima.
