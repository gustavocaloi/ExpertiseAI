# ExpertiseAI.Monitoria — MVP simulado

O módulo está integrado à navegação da plataforma. Entre como administrador, abra **Monitoria** e clique em **Carregar demonstração**. A ação cria três conversas fictícias (cobrança, suporte e cancelamento), reutiliza as áreas/categorias cadastradas e, se ainda não existirem pilares ativos, quatro agentes: Empatia, Clareza, Profissionalismo e Resolutividade. Repetir a ação reutiliza as mesmas conversas. O administrador atual é o operador e analista dos exemplos; nenhum usuário ou permissão é criado automaticamente.

## Fluxo disponível

- Upload multipart em lote, com até 20 áudios, 25 MiB por arquivo e 200 MiB no total. Cada arquivo tem ticket, cliente, tipo, área, categoria, operador e analista próprios. Formatos: WAV, MP3, OGG, M4A, FLAC, WEBM ou AAC.
- Transcrição fictícia separando cliente e operador, com tempos por fala.
- Notas simuladas de 0 a 100 para cada fala e pilar. A nota do pilar é a média das falas; a nota da conversa usa os pesos dos pilares. O painel calcula a média das notas das conversas nos filtros, independente da página.
- Revisão com player fixo, controles de posição/velocidade, conversa em balões e timeline proporcional ao tempo, com faixas de cliente/operador e notas por pilar. Áudio, marcador e falas se acompanham durante a reprodução. Cliques nas notas revelam as evidências; zoom e acompanhamento opcional permitem explorar a conversa. No celular, o detalhe tem navegação própria de retorno à lista. [Detalhes visuais e de interação](frontend.md#revisão-com-timeline-proporcional).
- Filtros por área, categoria, cliente, tipo, operador, analista, pilar e status. A API também aceita datas (`created_from`, `created_to`). IDs de operador e analista correspondem aos usuários existentes da empresa. O filtro de pilar oferece todas as versões ou uma versão específica, inclusive inativa.
- Administração de pilares e classificação pelas taxonomias existentes. Permissões são administradas na Gestão de Acessos. Salvar um pilar com o mesmo nome cria uma nova versão e desativa a anterior. Alterar descrição, prompt ou peso por PATCH também cria uma versão automaticamente. Resultados, pesos e cópias dos critérios usados nas novas avaliações são preservados. A seção “Critérios usados nesta avaliação” permite consultar essas cópias; avaliações antigas sem essa informação são identificadas explicitamente.

**Limitação explícita:** o simulador ignora os bytes do áudio. Os exemplos de áudio contêm 40 segundos de silêncio; as falas e notas são fictícias. O hash determinístico usa pilar, prompt e ticket para variar os scores; não mede o atendimento real nem interpreta as instruções do agente. Alterar um pilar afeta novas análises, não reprocessa resultados existentes. Não há chat analítico com IA neste MVP; a exploração dos resultados usa filtros e indicadores.

## APIs

Prefixo: `/api/v1/empresas/{company_id}/monitoria`. Use o token Bearer obtido no login da plataforma.

| Método / rota | Função |
| --- | --- |
| `POST /demo` | Carregar as três conversas de demonstração (administrador da empresa) |
| `POST /conversas/exemplo` | Carregar apenas o primeiro exemplo |
| `POST /conversas/upload` | Receber `file`, `ticket_id`, `cliente`, `tipo`, `area`, `categoria`, `operador_user_id`, `analista_user_id`; retorna 202 com UUID e job |
| `POST /conversas/upload-lote` | Receber `files` repetido, `metadata` como array JSON na mesma ordem e `request_id` UUID opcional; retorna 202 com lote e resultado por arquivo |
| `GET /lotes`, `GET /lotes/{batch_id}` | Histórico recente e acompanhamento persistido de lotes autorizados |
| `GET /conversas` | Lista paginada, `summary` calculado sobre todos os resultados autorizados; filtros `area`, `categoria`, `cliente`, `tipo`, `operador_user_id`, `analista_user_id`, `pillar_id` (versão exata), `pillar_family_id` (todas as versões do pilar), `status`, datas |
| `GET /conversas/{uuid}` | Metadados, `is_mock`, score ponderado, turnos, pilares com snapshots, telemetria e `evaluation_config` |
| `GET /conversas/{uuid}/audio` | Arquivo com o mesmo controle de acesso da conversa |
| `GET /jobs`, `GET /jobs/{id}` | Acompanhamento limitado ao escopo do usuário |
| `GET /escopo` | Papéis e escopo efetivo |
| `GET, POST /pilares` | Consulta e criação/versionamento de pilares |
| `PATCH /pilares/{id}` | Alterar critérios cria nova versão; `bump_version: true` força nova versão. Apenas ativação/desativação pode alterar a revisão existente |
| `GET /taxonomias` | Áreas e categorias existentes, respeitando o escopo do usuário |
| `PATCH /conversas/{uuid}/taxonomia` | Administrador classifica a conversa sem alterar avaliações |
| `GET /centrais`, `GET /equipes`, `GET /memberships` | Consulta legada; novos acessos são configurados em Gestão de Acessos |
| `GET, PUT /ai-settings` | Configuração por empresa e estado `runtime`; com flag desligada, só permite selecionar `mock`. Com flag ligada, permite cadastrar um provedor conhecido, mas o upload verifica se está implementado. `is_enabled: false` pausa o processamento |

Os resultados não expõem caminhos locais dos arquivos. Metadados de área/categoria e usuários são validados na empresa antes de armazenar o upload. A validação de extensão não é decodificação de áudio; isso faz parte da integração real futura.

## Módulos e restrições de áreas

Em **Gestão de Acessos → Usuários**, tanto o cadastro quanto o popup de edição oferecem os módulos **Gestão de Conteúdo** (`conteudo`) e **Monitoria** (`monitoria`), além do perfil na Monitoria. É possível habilitar um, ambos ou nenhum. Administradores da plataforma mantêm a gestão de usuários, mas também precisam do módulo habilitado para consultar seus dados.

A Monitoria reutiliza o cadastro de áreas e categorias da Gestão de Conteúdo. Não há uma segunda organização de centrais/equipes. `GET /taxonomias` retorna somente as áreas permitidas e suas categorias. Os perfis de restrição e o escopo efetivo de áreas existentes são aplicados às conversas, indicadores, áudio, jobs, lotes e MCP.

- Analistas e supervisores consultam/enviam conversas nas áreas permitidas.
- Operadores consultam somente suas próprias conversas **dentro das áreas permitidas**, sem upload.
- Administradores da plataforma têm acesso completo dentro do módulo habilitado. Administradores da Monitoria com escopo de todas as áreas também podem configurar o módulo; um perfil restrito a áreas não concede administração global.
- Categoria deve pertencer à área ativa da empresa. As restrições existentes são por área; categorias servem para classificar e filtrar, não criam uma segunda regra de permissão.
- Bloqueios são verificados no servidor em cada requisição/tool call, mesmo com token anterior à alteração. A navegação é atualizada ao carregar a sessão.

### Migração e registros antigos

A migração adiciona `area` e `categoria` sem alterar UUIDs, scores, áudios ou critérios usados. Conversas antigas sem classificação ficam disponíveis somente aos administradores globais da Monitoria. No detalhe, **Classificação da conversa** permite escolher uma área/categoria existente; também existe `PATCH /conversas/{uuid}/taxonomia`. A classificação não reprocessa a avaliação. Nenhuma correspondência entre central/equipe e área/categoria é presumida.

Usuários sem configuração explícita de módulos preservam o acesso anterior à Gestão de Conteúdo; acesso prévio à Monitoria é reconhecido pelos vínculos legados ou administração. Ao salvar módulos, essa seleção passa a prevalecer. O perfil legado de Monitoria de maior nível é usado como padrão até a configuração explícita. Centrais/equipes antigas permanecem armazenadas apenas como histórico; suas rotas de criação/alteração e criação de memberships retornam **410**, orientando a usar a Gestão de Acessos. Novos uploads com `central_id`/`team_id` são rejeitados; envie `area`/`categoria`.

Novos uploads sem área são aceitos somente por administradores globais e ficam sem classificação, fora da visibilidade dos demais perfis. Demonstrações usam taxonomias existentes; se não houver áreas, permanecem sem classificação. Não são criadas taxonomias automaticamente.

## Provedores e operação

A interface `AIProvider` separa `transcribe()` e `evaluate_pillar()`. Os adapters OpenAI, Anthropic/Claude e Groq continuam não implementados. A flag abaixo controla a seleção efetiva sem implementar essas integrações. Nenhuma chave é necessária para o modo mock.

### Flag de IA real

```dotenv
EXPAI_MONITORIA_REAL_AI_ENABLED=false
EXPAI_AI_PROVIDER=mock
```

| Flag | Novos uploads | Demonstração |
| --- | --- | --- |
| `false` (padrão) | Sempre `mock`, mesmo se houver um provedor real salvo na empresa | Sempre mock |
| `true` | Exigem provedor real configurado e implementado; caso contrário HTTP 409, antes de armazenar áudio/job | Sempre mock e identificada como tal |

A flag é global do servidor, não um campo editável na API da empresa. Reinicie todos os processos após alterá-la; no Docker, recrie os containers para carregar o novo ambiente. Os arquivos Compose existentes já recebem `.env` via `env_file`. No desenvolvimento com Uvicorn, exporte a variável no ambiente ou use `--env-file .env` com suporte a dotenv instalado; `app/config.py` não carrega `.env` automaticamente. Todas as instâncias devem usar o mesmo valor. Apenas `true`, `1` e `yes` (ignorando maiúsculas/espaços) ativam IA real; valor ausente ou inválido mantém mocks.

O módulo permanece visível nos dois modos. `is_enabled` continua sendo uma configuração independente por empresa para **pausar todo o processamento**, inclusive mocks/demonstrações. A flag de IA real não sobrescreve o provedor salvo. Com a flag desligada, a interface informa o provedor efetivo `mock` e preserva a configuração anterior ao salvar apenas o estado de pausa.

O provedor efetivo é persistido na criação da conversa, e o resultado registra `real_ai_enabled` em `evaluation_config`. Desativar a flag bloqueia jobs reais ainda pendentes antes de construir um adapter; eles falham com uma mensagem explícita, sem serem reclassificados como mock. Resultados históricos permanecem com sua origem original e não são apagados ou ocultados. Jobs mockados já criados mantêm a origem mock após ativar a flag.

`GET /escopo` e `GET/PUT /ai-settings` expõem `runtime`: `real_ai_enabled`, `mode`, `configured_provider`, `effective_provider`, `ready` e `reason`. `ready` refere-se a novos uploads. Assim, com IA real ativada e sem adapter implementado, a interface informa a indisponibilidade enquanto a demonstração continua acessível. Provedores desconhecidos são rejeitados; não há fallback silencioso de um erro real para mocks.

Ativar `true` **não basta para analisar áudios reais** nesta versão. Ainda é necessário implementar adapters, validação de áudio/diarização, configuração de modelos e gestão de credenciais.

Dados ficam em SQLite e em `EXPAI_MONITORIA_ROOT` (padrão `data/monitoria_store`). Os jobs têm posse persistida no SQLite: lease de 60 segundos, renovada a cada 15 segundos. Um worker não invalida trabalho ativo de outro. Jobs do endpoint individual legado têm 60 segundos de tolerância para iniciar. Os jobs de lote aguardam em fila persistida, sem expirar enquanto estão aguardando; a limpeza periódica marca apenas leases de execução expiradas como falha, em lotes de até 200. Resultados são gravados atomicamente e apenas pelo proprietário com lease válida. Cada chamada do provedor tem timeout de 120 segundos. Reenviar a execução de um job concluído não altera seus resultados. A fila de lotes retoma itens ainda não iniciados após reiniciar a aplicação. Itens interrompidos durante a execução terminam como falha por cancelamento ou expiração da lease; não há retry automático nem endpoint de reprocessamento.

## Envio em lote e processamento assíncrono

Em **Monitoria → Envio**, selecione vários arquivos, remova os indesejados e preencha os metadados individuais. Os campos individuais vazios herdam os valores da seção de metadados comuns. Após o HTTP 202, o servidor continua processando mesmo que a página seja fechada. Aguarde essa confirmação antes de sair durante a transferência.

A seção **Acompanhar envios** mostra o progresso e cada ocorrência, permite selecionar lotes recentes e abrir a conversa de cada áudio aceito. A página recupera os lotes do servidor após recarregar; consulta a cada dois segundos enquanto houver trabalho pendente e a aba estiver aberta. Rascunhos locais são limpos ao sair da conta ou mudar de empresa.

- A requisição inteira é recusada se ultrapassar 20 arquivos/200 MiB, se o array de metadados não corresponder aos arquivos ou se o processamento não estiver configurado. O JSON de metadados tem limite de 64 KiB.
- Arquivo vazio, extensão inválida, tamanho acima de 25 MiB ou metadados sem permissão rejeitam somente aquele item. Um lote pode ter todos os itens rejeitados; 202 confirma o registro, não sucesso de análise.
- Estados de item: `queued`, `processing`, `completed`, `failed`, `rejected`. Estados do lote: `queued`, `processing`, `completed`, `completed_with_errors`. `counts` separa cada estado; `total` considera apenas os itens ainda visíveis ao usuário.
- `request_id` é um UUID de idempotência por empresa e usuário. Reenviar a mesma chave, arquivos e metadados retorna o mesmo lote; alteração com a mesma chave retorna 409. Sem chave, cada requisição é um novo envio. O formulário preserva a chave em falhas de rede enquanto os dados não forem editados; esse rascunho não sobrevive ao recarregamento.
- O histórico pertence ao autor do envio; administradores podem consultar todos. Ambos respeitam o escopo atual das conversas. Operadores não enviam nem consultam lotes. A listagem retorna até 20 lotes por padrão, ajustável até 50.
- Cada processo da API executa até **dois jobs de lote simultâneos**. O limite não inclui o upload individual legado. Vários processos multiplicam a concorrência; todos precisam compartilhar SQLite e o armazenamento dos áudios. A posse atômica impede execução simultânea do mesmo job.
- O recebimento usa arquivos temporários; lote, conversas e jobs são registrados numa transação. Arquivos desta tentativa são removidos em rollback. A fila é local ao armazenamento persistido, não um broker distribuído; não há retry automático de falhas nem garantia de ordem de conclusão.

Para integrações, veja o [exemplo multipart](api.md#monitoria-upload-em-lote) e as [tools MCP](mcp.md#monitoria-e-integrações).

## Verificação

```bash
.venv/bin/python -m pytest tests/test_monitoria*.py -q
```

Para testar a interface sem alterar dados reais, inicie uma instância com diretório **novo e temporário**:

```bash
EXPAI_DATA_DIR=/tmp/monitoria-qa \
EXPAI_MCP_ENABLED=false EXPAI_DOCLING_ENABLED=false \
EXPAI_DOCLING_PREFETCH_MODELS=false EXPAI_AI_PROVIDER=mock \
.venv/bin/python -m uvicorn app.main:app --port 8766
```

Com Playwright e Chrome disponíveis, em outro terminal:

```bash
node scripts/check_monitoria.cjs
# Na mesma instância, depois do teste acima:
node scripts/check_monitoria_review.cjs
node scripts/check_monitoria_batches.cjs
```

O teste usa o administrador padrão apenas dessa instância temporária, cria exemplos, faz upload e cria um pilar. Verifica o fluxo real de API, evidências, player e todas as abas em larguras de 320 a 1440 px. Capturas ficam em `/tmp/expertise-monitoria-screens`. Use um diretório temporário novo para repetir o cenário inicial. Testes automatizados não substituem validação com supervisores e analistas reais.


## Integridade e migração após a auditoria

Os cinco achados técnicos da auditoria foram corrigidos; detalhes em [correções e verificação](audits/monitoria/correcoes.md).

- Upload sem pilar ativo retorna **409 Configuração pendente**, antes de criar conversa/job/arquivo permanente. O worker também verifica a configuração. Pilares padrão são criados apenas pela ação explícita de demonstração.
- Transcrições exigem texto, falante reconhecido, índices únicos/ordenados e timestamps finitos e coerentes. Avaliações exigem notas finitas de 0 a 100, identidade correta do pilar/versão, justificativa e cobertura de todas as interações com referências válidas e evidências não vazias. Resultados inválidos/incompletos falham; nenhum resultado parcial é publicado.
- A publicação de turnos, notas, configuração usada e estados de job/conversa ocorre numa única transação. Erros de persistência desfazem toda essa gravação.
- Os metadados enviados ao avaliador incluem tipo, área, categoria e analista. O registro de configuração informa provider, idioma e versão da implementação mock usada; não afirma ter utilizado modelos externos configurados que o mock não executa.
- Inicialização aplica migração aditiva: `family_id`, cópias de prompt/descrição, `evaluation_config` e colunas de lease. UUIDs, notas e pesos existentes permanecem. Não se inventam snapshots antigos: `snapshot_available: false` informa sua ausência.
- Na atualização, encerre instâncias antigas antes de iniciar a versão corrigida. Processos da versão antiga não renovam leases. Jobs legados pendentes recebem uma janela de 60 segundos na migração e expiram se não houver execução válida.

Testes de regressão: `.venv/bin/python -m pytest tests/test_monitoria_regressions.py -q`. O caminho histórico `docs/audits/monitoria/reproduce_findings.py` agora executa as regressões corrigidas: PASS significa proteção verificada.

Regressões da flag: `.venv/bin/python -m pytest tests/test_monitoria_mode.py -q`. Os testes usam doubles locais; nenhuma API externa é chamada.

Verificação visual da flag: execute `MONITORIA_EXPECT_REAL=false node scripts/check_monitoria_mode.cjs` contra uma instância temporária com a flag desligada; repita com `MONITORIA_EXPECT_REAL=true` contra outra instância com a flag ligada. Use `MONITORIA_TEST_URL` para o endereço e `MONITORIA_TEST_PASSWORD` se a senha do administrador temporário já foi alterada. O script grava apenas nessa instância de teste: configura provedor, cria demonstração e verifica bloqueio de upload real sem adapter, indicação do modo e responsividade.

Os testes de lote verificam falhas parciais, limites, isolamento por empresa/escopo, idempotência, concorrência e retomada da fila. `tests/test_monitoria_mcp.py` requer Python 3.10+ e o SDK MCP instalado; valida as tools reais, permissões e transporte HTTP autenticado. Sem o SDK, esse arquivo é explicitamente ignorado pelo pytest.
