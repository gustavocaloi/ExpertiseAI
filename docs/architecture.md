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

Cada empresa possui um indice local:

- `data/kb_store/<empresa_id>/_documents.index.json`

Esse indice acelera:

- paginacao
- filtros por area, categoria e tag
- busca textual
- abertura de documentos por resolucao mais rapida de metadados
