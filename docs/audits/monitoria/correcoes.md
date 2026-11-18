# Correções da auditoria de Monitoria

Escopo desta entrega: os cinco achados técnicos reproduzidos em [11/11/2026](2026-11-11-review.md). O módulo permanece mockado.

| Achado | Correção | Evidência de regressão |
| --- | --- | --- |
| F1: critério mutável sem versionamento | Mudanças de descrição, prompt ou peso criam nova versão em transação; resultados guardam cópia do critério usado. Alterações concorrentes durante a análise não mudam seu snapshot. | Versão anterior preservada; snapshot inalterado; versões concorrentes únicas; edição de revisão inativa não desativa revisão ativa. |
| F2: filtro perdia histórico | `family_id` identifica o pilar ao longo das versões; filtro por família e por revisão exata; seletor inclui versões inativas. | Avaliações antigas continuam visíveis por família e v1, mas não aparecem indevidamente em v2. Filtros de outra empresa não retornam resultados. |
| F3: worker recriava critério desativado | Upload sem pilar ativo responde 409. Worker falha com configuração pendente e não cria pilares. Defaults apenas na demonstração explícita. | Nenhuma conversa/job nova no upload rejeitado; nenhum pilar reativado pelo processamento. |
| F4: resposta inválida aceita como concluída | Validação de transcrição, notas, versão, justificativas, timestamps, referências, duplicidades, cobertura e evidências. Publicação atômica após validar tudo. | Scores negativos, >100, NaN/Inf; referências inválidas; lacunas de cobertura; transcrições inválidas; falha de escrita causa rollback total. |
| F5: limpeza invalidava worker alheio | Claim exclusivo, lease persistida e heartbeat, expiração limitada e conclusão condicionada à posse ainda válida. Conclusão e dados na mesma transação. | Segundo processo não invalida job vivo; apenas um claim vence; lease expirada não publica nem renova; limpeza idempotente; reenvio de job concluído preserva resultado. |

## Dados existentes

Migração aditiva e repetível mantém UUIDs, notas e pesos. Famílias são agrupadas pelo nome dentro da mesma empresa, conforme o modelo pré-existente. Snapshots ausentes não são reconstruídos: a UI informa que o critério histórico não está disponível. Repetição da migração e preservação de dados são cobertas por teste.

## Verificação

```bash
.venv/bin/python -m pytest -q
node --check app/static/app.js
```

**Resultado desta entrega:** 42 testes Python aprovados; JavaScript validado; fluxo de integração aprovado de 320 a 1440 px, sem erros de JavaScript.

O teste de integração `scripts/check_monitoria.cjs`, executado em uma base temporária nova, inclui criar nova versão de Empatia, filtrar por v1/v2/todas e consultar o snapshot da avaliação anterior, além de upload, áudio, evidências e responsividade. Para executar, siga [Monitoria](../../monitoria.md).

Os antigos testes que confirmavam falhas agora esperam o comportamento corrigido. O arquivo `reproduce_findings.py` foi mantido como entrada compatível para essas regressões.

## Limites que continuam explícitos

Esta correção não conecta provedores reais nem valida acurácia semântica. Notas e transcrições continuam simuladas. O contrato atual exige uma nota/evidência para cada interação; aplicabilidade/N/A, eventos críticos e política de avaliação real continuam decisões da próxima etapa.

Leases protegem a execução concorrente em processos que usam o mesmo SQLite, mas não implementam fila distribuída, retomada automática, retry ou nova tentativa de uma avaliação concluída. Jobs realmente abandonados passam a falha após expiração. Workers antigos devem ser encerrados na atualização.

Calibração com humanos, contestação, coaching, retenção e sincronização contínua da linha do tempo continuam itens de evolução descritos na auditoria, não funcionalidades entregues por esta correção.
