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
- `busca`
- `limit`
- `offset`
- `sort`

Na rota versionada `GET /api/v2/empresas/{empresa_id}/documentos/publicados`, tambem existe:

- `data_validade_ate` (quando informado, retorna documentos com `data_validade <= dd/mm/aaaa`; quando omitido, retorna documentos com `data_validade >= hoje`)

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

## Observacoes

- as rotas respeitam contexto de empresa;
- administradores nao sofrem restricao por area;
- a publicacao exige perfil `aprovador` ou `admin`.
