# Documentacao Tecnica

Esta pasta concentra a documentacao tecnica do `Expertise.AI`, separada por assunto para facilitar manutencao, onboarding e operacao.

## Indice

- [Arquitetura e persistencia](./architecture.md)
- [Controle de acesso e aprovacao](./access-control.md)
- [Deploy e operacao](./deployment.md)
- [Backup e restauração](./backup.md)
- [API principal](./api.md)
- [MCP para agentes de IA](./mcp.md)
- [Frontend e experiencia de uso](./frontend.md)

## Verificacao local

```bash
pip install -r requirements-dev.txt
pytest
python scripts/bench_document_search.py --sizes 1000,5000,10000
```

## Como navegar

- Comece por `architecture.md` para entender o modelo de dados e armazenamento.
- Use `access-control.md` para perfis, aprovacoes e restricoes por area.
- Consulte `deployment.md` para ambiente, container, bootstrap e operacao.
- Use `api.md` como referencia funcional das rotas principais.
- Use `mcp.md` para conectar agentes de IA ao conteudo publicado com controle de acesso.
- Consulte `frontend.md` para comportamento da interface administrativa e da jornada do usuario.

- [Monitoria — MVP simulado, APIs, permissões e verificação](monitoria.md)

- [Auditoria da Monitoria e comparação de mercado — 11/11/2026](audits/monitoria/2026-11-11-review.md)

- [Correções da auditoria de Monitoria e regressões](audits/monitoria/correcoes.md)
