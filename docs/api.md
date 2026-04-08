# API Principal

## Autenticacao

- `POST /api/v1/auth/login`
  - autentica usuario e retorna JWT
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
  - lista somente documentos publicados
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

## Observacoes

- as rotas respeitam contexto de empresa;
- administradores nao sofrem restricao por area;
- a publicacao exige perfil `aprovador` ou `admin`.
