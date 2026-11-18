# Controle de Acesso e Aprovacao

## Modelo multiempresa

Cada usuario pertence a uma ou mais empresas e opera sempre dentro do contexto de uma empresa selecionada.

## Perfis

- `admin`: acesso total, incluindo gestao de usuarios, criacao de empresas e configuracao de restricoes.
- `editor`: cria, edita e exclui documentos, areas e categorias.
- `aprovador`: visualiza versoes pendentes e publica documentos.

Os perfis podem ser acumulativos. Quando houver mais de um perfil, prevalece o maior nivel de acesso, sem perda das demais permissoes.

## Monitoria (modulo separado)

Alem dos perfis da base de conhecimento, o modulo de monitoria possui memberships proprios por empresa:

- `monitoria_admin` sem restrição de central: configura centrais, equipes, pilares e settings; vê todas as conversas da empresa. Um vínculo restrito à central/equipe permite apenas acesso ao respectivo escopo e não às configurações globais.
- `monitoria_supervisor`: ve conversas das centrais/equipes vinculadas.
- `monitoria_analista`: ve o escopo da central/equipe ou conversas atribuidas.
- `monitoria_operador`: ve apenas conversas em que e o operador.

Administradores da KB (`admin`) tem acesso total ao modulo sem membership explicito.
`cliente` e metadado de filtro do ticket, nao no de ACL.

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


## Acesso por módulo

O cadastro e a edição de usuários aceitam `modules: ["conteudo", "monitoria"]` e `monitoria_role` (`monitoria_admin`, `monitoria_supervisor`, `monitoria_analista` ou `monitoria_operador`). A lista pode conter um, ambos ou nenhum módulo. Omitir os campos na atualização preserva a configuração anterior. Valores desconhecidos retornam 422 antes de alterar o usuário.

`GET /auth/me` e a listagem de usuários incluem os módulos efetivos e o perfil de Monitoria. O backend reconsulta as permissões em cada requisição REST e MCP; ocultar menus é apenas uma ajuda de navegação. Administradores continuam podendo gerenciar usuários mesmo sem acesso a um módulo, evitando perda da capacidade de corrigir permissões.

As restrições de áreas existentes são compartilhadas com a Monitoria. Um operador precisa simultaneamente ser o responsável e ter acesso à área; analistas/supervisores acessam as áreas do seu escopo efetivo. Categoria é validada dentro da área e usada como filtro. Não existem novos cadastros organizacionais no módulo. Veja [migração e conversas antigas](monitoria.md#migração-e-registros-antigos).

Verificação: `tests/test_module_access.py` e `tests/test_monitoria_mcp.py`. O fluxo visual está em `scripts/check_module_access.cjs`, executado após o smoke de Monitoria numa instância isolada.

## Administração global de backup

Backup e restauração são globais e exigem perfil `admin` ativo em todas as empresas. Administradores locais de uma parte das empresas e o perfil `monitoria_admin` não recebem acesso. A API consulta as permissões atuais e não habilita esse recurso no modo sem autenticação. Após restaurar, uma nova geração de sessão invalida tokens de acesso e refresh anteriores em todos os processos. Consulte [backup e restauração](backup.md).
