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

O botão `Novo documento` permanece visível, mas fica desabilitado para o perfil `aprovador`.

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

## Sistema visual

A interface usa fontes do sistema e ícones SVG locais, sem requisições externas de tipografia ou ícones.
Os tokens ficam no início de `app/static/styles.css`. Evite adicionar cores isoladas em componentes.

| Uso | Token | Cor |
| --- | --- | --- |
| Fundo da página | `--canvas` | `#f4f7f8` |
| Superfícies | `--surface` | `#ffffff` |
| Superfície suave | `--surface-muted` | `#fafbfc` |
| Texto principal | `--ink` | `#172b33` |
| Texto secundário | `--ink-soft` | `#52636b` |
| Ação principal | `--primary` | `#146956` |
| Borda / fundo da ação | `--primary-border` / `--primary-soft` | `#c8dfd5` / `#eaf5f0` |
| Publicado / sucesso | `--success` / `--success-border` | `#166345` / `#c4e4d2` |
| Pendente / atenção | `--warning` / `--warning-border` | `#86520b` / `#eddbb5` |
| Erro / exclusão | `--danger` / `--danger-border` | `#ad323b` / `#edc6c8` |
| Rascunho / processamento | `--info` / `--info-border` | `#275e99` / `#d1dff1` |
| Foco de teclado | `--focus` | `#217dbe` |
| Altura de controle | `--control-h` / `--control-h-sm` | `44px` / `40px` |

- Ação principal no cabeçalho à direita em desktop; em mobile, abaixo do título e com largura completa.
- Formulários terminam com ações à direita: cancelar antes de salvar. Ações destrutivas usam vermelho no estado de interação.
- Filtros têm rótulos visíveis e uma ação de limpeza. A busca fica no cabeçalho da biblioteca.
- A contagem da biblioteca representa os documentos nos filtros atuais. Importações em andamento e com falha são exibidas à parte, conforme a API existente.
- Badges compartilham dimensões e tipografia, sempre com texto além da cor.
- Controles principais têm 44 px de altura; ações de documento usam 40 px em desktop e 44 px em mobile.
- Abaixo de 800 px a navegação passa para uma linha própria. Formulários passam para uma coluna em telas pequenas.
- Modais rolam dentro da tela, contêm o foco e devolvem o foco ao controle de origem ao fechar.
- A biblioteca diferencia carregamento, ausência de conteúdo, busca sem resultados, preparação do índice e falha com nova tentativa.
- Respostas antigas de busca são descartadas quando uma requisição mais recente já foi iniciada.

## Critérios de revisão profissional

1. **Além do visual:** revisar a jornada por perfil, hierarquia das ações, estados de erro/vazio/carregamento, teclado e leitura em telas pequenas. Validar com usuários reais a facilidade para encontrar, criar e aprovar documentos.
2. **Material de origem:** código HTML/CSS/JavaScript, contratos e respostas de API, metadados e títulos reais (incluindo longos), permissões, observação de tarefas e relatos brutos dos usuários. Capturas e resumos são complementos.
3. **Métodos e ferramentas:** inventário de componentes, análise dos fluxos, tokens CSS, Flexbox/Grid, HTML semântico, SVG, Playwright/Chromium, inspeção visual e cálculo de contraste.
4. **Evidência independente:** testes reproduzíveis, ausência de erros de JavaScript, ausência de rolagem horizontal de 320 a 1440 px, contraste medido, comportamento por perfil e testes de tarefa com usuários representativos. Uma revisão visual ou teste automatizado isolado não demonstra conformidade completa nem usabilidade.

Referências: [contraste de texto](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html),
[reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) e
[tamanho dos alvos](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).

## Verificação reproduzível do frontend

Com o container local em execução e Playwright disponível no ambiente de desenvolvimento:

```bash
FRONTEND_URL=http://localhost:8000/ node scripts/check_frontend.cjs
```

Se usar o Chrome instalado em vez do Chromium do Playwright, acrescente `PLAYWRIGHT_CHANNEL=chrome`.
Para salvar capturas fora do repositório, acrescente `UI_SCREENSHOTS=/tmp/expertise-ui`.
Com `@axe-core/playwright` disponível, acrescente `UI_A11Y=1` para auditar automaticamente as telas capturadas pelos critérios WCAG A/AA selecionados. Isso não substitui uma auditoria manual completa.

O script intercepta as APIs com dados fictícios e testa login, busca e respostas fora de ordem,
paginação, limpeza de filtros, menu, retorno do editor, teclado, modais, estados de importação,
falha/recuperação, preparação do índice, permissões de editor/aprovador e telas de administração.
Percorre larguras de 320, 390, 768, 1024 e 1440 px e falha em caso de overflow horizontal.
Não grava documentos ou usuários reais e não substitui a verificação de integração com o backend.

## Monitoria

O módulo usa os mesmos tokens visuais e oferece balões de conversa, player autenticado, telemetria por pilar e filtros com indicadores calculados no servidor. O aviso de simulação permanece visível. Confira o fluxo e o teste de integração em [Monitoria](monitoria.md).

O filtro de pilares distingue todas as versões e versões específicas (inclusive inativas). A conversa permite expandir “Critérios usados nesta avaliação”, com os critérios persistidos na análise ou um aviso de ausência no histórico legado.


### Revisão com timeline proporcional

A revisão da Monitoria reúne o player, a timeline e a transcrição. O player permanece abaixo do cabeçalho durante a rolagem; a altura do cabeçalho é medida para acompanhar sua quebra de linhas no celular. Controles incluem reproduzir/pausar, voltar 10 segundos, posição por slider e velocidade de 1× a 2×.

- A timeline usa os timestamps da API para posicionar e dimensionar cada trecho. Há faixas separadas para cliente, operador e cada pilar, com régua, marcador de reprodução, zoom 1×/2×/4× e rolagem interna. Não há waveform: nenhum dado de amplitude é inventado.
- Cliques ou ativação por teclado em uma nota exibem sua evidência e localizam a fala. Clicar no balão também posiciona a reprodução. A evidência selecionada permanece identificada mesmo quando o áudio avança ou o zoom muda.
- Durante a reprodução, o marcador e as falas ativas acompanham o tempo do áudio. Intervalos sem fala não recebem destaque; falas sobrepostas podem ser destacadas juntas. “Acompanhar reprodução” permite desligar a rolagem automática interna. A página não rola automaticamente.
- Sem áudio carregado, é possível explorar a timeline e as falas. Ao carregar, a posição selecionada é aplicada dentro da duração disponível. Se áudio e transcrição simulada tiverem durações diferentes, um aviso explica a diferença; o eixo considera a maior duração.
- Os filtros ficam recolhidos com uma contagem dos filtros ativos. Até 1000 px, a seleção abre uma área de revisão dedicada, ocultando lista e indicadores; “Voltar aos atendimentos” pausa o áudio e devolve o foco à conversa. O retorno fica disponível também durante carregamento e falha.
- Trocar de conversa descarta respostas atrasadas de áudio, libera a URL temporária e reinicia os controles. Sair da aba ou do módulo pausa a reprodução. Erros de download e decodificação têm mensagens em português e permitem nova tentativa.

Verificação: `scripts/check_monitoria.cjs` cobre integração, timestamps proporcionais, sincronização, teclado, velocidade, zoom e navegação de 320 a 1440 px. Após esse teste, `scripts/check_monitoria_review.cjs` verifica falhas/retentativa, resposta atrasada, arquivo inválido, pausas/sobreposições, player fixo, acompanhamento opcional e seleção preservada no zoom. O segundo script altera apenas respostas GET no navegador para os cenários sintéticos. Testes e capturas não substituem validação de usabilidade com analistas; não há alegação de auditoria completa de acessibilidade nem de desempenho para gravações extensas.

A Monitoria exibe o modo efetivo retornado pelo servidor (`runtime`). Com a flag de IA real desligada, os novos uploads usam mocks e o seletor de provedor fica bloqueado. Com a flag ligada, o administrador pode salvar o provedor desejado; a interface informa quando sua implementação está indisponível. A opção de processamento pausado é independente da flag.


### Envio em lote

O formulário de Monitoria permite selecionar até 20 áudios, revisar/remover arquivos e definir ticket, cliente, tipo e responsáveis individualmente. Campos individuais vazios usam os metadados comuns, disponíveis numa seção recolhível. O formulário fica bloqueado somente durante a transferência; após a confirmação 202, libera um novo envio enquanto os jobs continuam no servidor.

O acompanhamento separa fila, análise, conclusão, falha e rejeição, com progresso acessível e acesso à conversa. O histórico é recuperado pela API ao recarregar; polling pausa fora da aba. Respostas atrasadas são descartadas após troca de contexto/logout, e dados anteriores são removidos em erro de autorização. Uma tentativa não confirmada preserva a chave de idempotência até editar os dados ou recarregar a página.

`scripts/check_monitoria_batches.cjs`, executado depois do smoke inicial na mesma instância temporária, verifica seleção múltipla, remoção, herança e substituição dos metadados, rejeição parcial, recuperação após reload, abertura da conversa e ausência de overflow de 320 a 1440 px. As capturas ficam em `/tmp/expertise-monitoria-screens/lotes-*.png`.


### Permissões de módulo e taxonomias

Cadastro e edição de usuários mostram checkboxes para Gestão de Conteúdo e Monitoria, com seleção do perfil de Monitoria. Menus de módulos não permitidos ficam ocultos; usuários apenas de Monitoria entram diretamente nesse módulo. Usuários sem módulos acessam o perfil; administradores mantêm Gestão de Acessos.

A aba Organização foi substituída por **Áreas e categorias**, usando o cadastro existente. Filtros e upload em lote oferecem seletores vinculados: categoria depende da área. No detalhe, administradores podem classificar conversas antigas sem mudar a avaliação. `scripts/check_module_access.cjs` verifica criação/edição das permissões, navegação exclusiva de Monitoria e upload restrito por área/categoria.

### Backup e restauração

O menu do usuário mostra **Backup e restauração** quando a sessão retorna `can_manage_backup=true`. A tela oferece download do JSON completo e importação com confirmação digitada `RESTAURAR`, limite de tamanho, mensagens de progresso/erro, bloqueio contra duplo envio e novo login após concluir. A confirmação informa a substituição de todas as empresas, usuários e senhas. A API valida novamente a autorização. `scripts/check_backup.cjs` verifica o fluxo com respostas simuladas e layout de 320 a 1440 px. Veja [backup e restauração](backup.md) para os detalhes operacionais.
