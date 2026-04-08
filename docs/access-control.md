# Controle de Acesso e Aprovacao

## Modelo multiempresa

Cada usuario pertence a uma ou mais empresas e opera sempre dentro do contexto de uma empresa selecionada.

## Perfis

- `admin`: acesso total, incluindo gestao de usuarios, criacao de empresas e configuracao de restricoes.
- `editor`: cria, edita e exclui documentos, areas e categorias.
- `aprovador`: visualiza versoes pendentes e publica documentos.

Os perfis podem ser acumulativos. Quando houver mais de um perfil, prevalece o maior nivel de acesso, sem perda das demais permissoes.

## Administracao de usuarios

A sessao administrativa permite:

- criar ou vincular usuarios;
- atribuir perfis acumulativos;
- redefinir nome e senha;
- revogar e reativar acesso por empresa;
- consultar auditoria recente;
- exportar auditoria em CSV;
- paginar usuarios e auditoria.

## Troca obrigatoria de senha

- novos usuarios recebem senha provisoria;
- redefinicoes administrativas tambem podem exigir troca no primeiro acesso;
- o `superadmin` e a excecao operacional prevista.

## Restricao por area

Administradores podem limitar a visibilidade de documentos por area para usuarios nao admin.

O modelo suporta:

- perfil padrao de restricao por usuario;
- perfis reutilizaveis de restricao por area;
- atribuicao de um ou mais perfis ao mesmo usuario.

Administradores mantem acesso total.

## Fluxo de aprovacao

### Comportamento

- `editor` cria ou altera uma versao;
- se o usuario nao puder publicar, a nova versao fica como `pendente de aprovacao`;
- `aprovador` ou `admin` visualiza o documento, abre a versao e executa a publicacao.

### Sinalizacoes

- a home indica quantas pendencias de aprovacao existem;
- os cards de documento mostram o estado pendente;
- a timeline do documento destaca versoes pendentes;
- a timeline registra quem aprovou e quando.

## Seguranca operacional

- o backend revalida o acesso atual do usuario no banco;
- o contexto da empresa e validado nas rotas protegidas;
- em producao, ha guardrails para evitar modo sem controle de acesso e criacao publica de empresa por engano.
