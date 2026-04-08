# Frontend e Experiencia de Uso

## Visao geral

A interface web fica em:

- `app/static/index.html`
- `app/static/styles.css`
- `app/static/app.js`

## Sessoes principais

- Inicio
- Perfil
- Estrutura
- Administracao de usuarios
- Restricao de areas por usuario
- Criacao e edicao de documento

## Home

A home concentra:

- listagem de documentos;
- filtros por area, categoria, tag e busca;
- ordenacao;
- paginacao;
- sinalizacao de pendencias de aprovacao para quem pode publicar.

## Jornada do aprovador

- visualiza documentos pendentes na home;
- abre o documento e consulta a versao;
- publica a versao pendente;
- acompanha historico de aprovacao na timeline.

O botao `Publicar novo documento` permanece visivel, mas fica desabilitado para o perfil `aprovador`.

## Jornada do editor

- cria documento por texto ou upload;
- gera nova versao;
- quando nao possui permissao de publicacao, envia versao para pendencia de aprovacao.

## Administracao de usuarios

A interface administrativa oferece:

- lista compacta de usuarios;
- popup com edicao completa;
- perfis acumulativos;
- redefinicao de senha;
- revogacao e reativacao;
- perfis reutilizaveis de restricao por area;
- auditoria recente paginada.

## Timeline do documento

A linha do tempo mostra:

- versoes do documento;
- versao publicada;
- versoes pendentes de aprovacao;
- registro de quem aprovou e quando.

## Performance percebida

O frontend foi ajustado para operar melhor com bases grandes, com destaque para:

- paginacao de documentos;
- busca textual indexada;
- filtros mais leves;
- abertura mais rapida de documentos especificos;
- debounce na busca.
