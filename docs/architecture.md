# Arquitetura e Persistencia

## Visao geral

O `Expertise.AI` combina:

- arquivos Markdown versionados para o conteudo da base;
- `SQLite` local para usuarios, empresas, papeis e configuracoes administrativas.

Esse desenho permite uma base rastreavel, simples de operar e preparada para migracao e auditoria.

## Estrutura de armazenamento

### Conteudo

- `data/kb_store/<empresa_id>/_documents/<document_uuid>/`
- `v1.md`, `v2.md`, `v3.md` em diante representam as versoes do documento.
- `document.meta.json` controla metadados, versao publicada, anexos e historico.

### Dados administrativos

- `data/system.sqlite3`

Principais entidades:

- `users`
- `companies`
- `user_company_roles`
- tabelas de restricao por area e perfis reutilizaveis
- trilha de auditoria de acessos
- tabelas `monitoria_*` (centrais, equipes, memberships, pilares, conversas, turnos, scores e jobs)

### Monitoria de atendimento

O modulo de monitoria e um dominio separado da base de conhecimento:

- metadados e resultados em SQLite (`monitoria_*`);
- arquivos de audio em `data/monitoria_store/<empresa_id>/<conversation_uuid>/`;
- pipeline assincrono: upload -> transcricao -> avaliacao por pilar -> scores;
- provedor de IA plugavel (`EXPAI_AI_PROVIDER`, padrao `mock` na fase 1);
- hierarquia `Empresa -> Central -> Equipe -> Operador`, com `cliente` como dimensao de filtro do ticket;
- papeis proprios (`monitoria_admin`, `monitoria_supervisor`, `monitoria_analista`, `monitoria_operador`); admins da KB tem acesso total ao modulo.

## Identidade do documento

A identidade fisica do documento e baseada em:

- `empresa_id`
- `document_uuid`

`area`, `categoria` e `slug` permanecem como metadados editaveis. Isso permite alterar classificacao e identificadores sem perder o vinculo fisico do documento.

## Publicacao e versoes

- cada nova alteracao gera uma nova versao;
- a versao publicada e controlada por `published_version` em `document.meta.json`;
- versoes podem ficar em rascunho ou pendentes de aprovacao;
- a linha do tempo registra criacao, publicacao e aprovacao.

## Migracao do layout legado

O startup da aplicacao executa migracao automatica do layout antigo para o layout baseado em `_documents/<document_uuid>`.

A migracao preserva:

- `document_uuid`
- historico de versoes
- anexos
- metadados existentes

## Otimizacoes de performance

Cada empresa possui um indice local leve:

- `data/kb_store/<empresa_id>/_documents.index.json` (`schema_version: 2`)

Esse indice guarda metadados (sem o corpo Markdown) e acelera:

- paginacao
- filtros por area, categoria e tag
- ordenacao
- abertura de documentos por resolucao mais rapida de metadados

A listagem aplica filtros e `offset`/`limit` antes de carregar o conteudo.
Por padrao as rotas de listagem usam `include_content=true` e leem o Markdown
apenas dos itens da pagina atual (em paralelo, sem reler `document.meta.json`).
Use `include_content=false` quando o cliente precisar so de metadados.

### Busca textual (FTS5)

A busca por `busca` usa o indice SQLite FTS5 `document_search_fts` em `system.sqlite3`.

- sincronizado na publicacao/edicao/exclusao e no rebuild do indice JSON;
- cobre titulo, slug, area, categoria, tags e corpo da versao selecionada;
- indices JSON antigos (sem `schema_version: 2`) sao migrados no proximo acesso.

Para medir latencia local (p50/p95) com 1k/5k/10k documentos:

```bash
python scripts/bench_document_search.py --sizes 1000,5000,10000 --rounds 30
```
