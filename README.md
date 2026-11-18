# Expertise.AI

[![GitHub](https://img.shields.io/badge/GitHub-ExpertiseAI-181717?logo=github)](https://github.com/gustavocaloi/ExpertiseAI)
[![License: MIT](https://img.shields.io/badge/License-MIT-4d2d5e.svg)](https://opensource.org/license/MIT)
[![Docling](https://img.shields.io/badge/Docling-Read%20Docs-0d7b58?logo=readthedocs&logoColor=white)](https://docling-project.github.io/docling/)

## Plataforma de base de conhecimento corporativa

`Expertise.AI` organiza conhecimento operacional em um ambiente multiempresa com governanca, versionamento, aprovacoes e busca rapida.

Foi pensada para times que precisam transformar documentos dispersos em uma base confiavel, rastreavel e pronta para consulta por pessoas e por agentes de IA.

## O que a plataforma entrega

- Centralizacao de conhecimento em uma unica base por empresa.
- Versionamento real de documentos com historico de publicacao.
- Fluxo de aprovacao para publicacao de conteudo sensivel.
- Controle de acesso por perfil e por area de documento.
- Conversao de PDF e DOCX para Markdown com `docling`.
- Busca, filtros e navegacao otimizados para alto volume de documentos.
- Servidor MCP autenticado para consulta da base publicada, operação da Monitoria e descoberta dos contratos das APIs.
- Modulo de **Monitoria** de atendimento: upload de áudios em lote com fila assíncrona persistida, transcricao, pilares/agentes de IA e telemetria por interacao (fase 1 com provedor `mock`).

## Casos de uso

- Operacoes e processos internos.
- Suporte e atendimento.
- Onboarding de equipes.
- Compliance e procedimentos auditaveis.
- Base de consulta para copilots e agentes de IA.

## Diferenciais

- Multiempresa com segregacao de dados por companhia.
- Persistencia de documentos baseada em `document_uuid`, preservando identidade mesmo com mudanca de metadados.
- Estrutura preparada para milhares de documentos com indice local por empresa.
- Jornada administrativa completa para usuarios, acessos e restricoes por area.
- Linha do tempo do documento com historico de versoes, pendencias e aprovacoes.

## Perfis de acesso

- `admin`: acesso total, incluindo gestao de usuarios, restricoes e criacao de empresas.
- `editor`: cria, edita e exclui documentos, areas e categorias.
- `aprovador`: revisa versoes pendentes e publica documentos.

Perfis do modulo Monitoria (por membership): `monitoria_admin`, `monitoria_supervisor`, `monitoria_analista`, `monitoria_operador`. A flag `EXPAI_MONITORIA_REAL_AI_ENABLED=false` (padrão) mantém o módulo disponível e força novas análises mockadas, sem chamadas externas. Com `true`, novos uploads exigem um provedor real implementado; os adapters reais ainda estão pendentes. `EXPAI_AI_PROVIDER` define o provedor inicial para empresas sem configuração própria. Consulte [Monitoria](docs/monitoria.md#flag-de-ia-real).

## Inicio rapido

### Desenvolvimento local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Como subir em container

Prepare o ambiente:

```bash
cp .env.example .env
```

#### Container com build rapido

Exemplo de compose:

```yaml
services:
  expertise-ai:
    image: lcaloi/expertiseai:latest
    container_name: expertise-ai
    env_file:
      - ../.env
    environment:
      EXPAI_DATA_DIR: /app/data
      DOCLING_CACHE_DIR: /app/data/docling_cache
      HF_HOME: /app/data/docling_cache/huggingface
      HUGGINGFACE_HUB_CACHE: /app/data/docling_cache/huggingface
      XDG_CACHE_HOME: /app/data/docling_cache
      # Proxy opcional para downloads e chamadas HTTP feitas pelo container.
      HTTP_PROXY: ${HTTP_PROXY:-}
      HTTPS_PROXY: ${HTTPS_PROXY:-}
      NO_PROXY: ${NO_PROXY:-}
      EXPAI_ACCESS_CONTROL_ENABLED: "false"
      EXPAI_BOOTSTRAP_DEFAULT_ADMIN: "true"
      EXPAI_DEFAULT_COMPANY_NAME: Expertise.AI
      EXPAI_DEFAULT_COMPANY_DESCRIPTION: Base de Conhecimento por Expertise Operacional
      EXPAI_DEFAULT_COMPANY_SLUG: expai
      EXPAI_DEFAULT_ADMIN_NAME: Administrador Expertise.AI
      EXPAI_DEFAULT_ADMIN_EMAIL: admin@expertise.ai.local
      EXPAI_DEFAULT_ADMIN_PASSWORD: Admin@123
      EXPAI_SUPER_ADMIN_USER: superadmin
      EXPAI_SUPER_ADMIN_PASSWORD: Admin@123
      EXPAI_SECRET_KEY: change-me
      EXPAI_JWT_ALGORITHM: HS256
      EXPAI_ACCESS_TOKEN_EXPIRE_MINUTES: "480"
      EXPAI_LOG_LEVEL: DEBUG
      EXPAI_DOCLING_ENABLED: "true"
      EXPAI_DOCLING_TIMEOUT_SECONDS: "1800"
      EXPAI_DOCLING_MAX_PAGES: "600"
      EXPAI_DOCLING_MAX_FILE_SIZE_MB: "50"
      EXPAI_DOCLING_PDF_PAGE_BATCH_SIZE: "10"
      EXPAI_DOCLING_THREADS: "2"
      # Controla a expectativa de operação offline para PDF nesta imagem publicada.
      # Para funcionar sem internet, a imagem precisa ter sido buildada com
      # EXPAI_DOCLING_PREFETCH_MODELS=true no Dockerfile.
      EXPAI_DOCLING_PREFETCH_MODELS: "true"
      EXPAI_DOCLING_OCR_ENABLED: "false"
      EXPAI_DOCLING_TABLE_STRUCTURE_ENABLED: "false"
    ports:
      - "8000:8000"
    mem_limit: 6g
    cpus: 2.0
    volumes:
      - expertise_ai_data:/app/data
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')\""]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 120s
    deploy:
      resources:
        limits:
          memory: 6g
          cpus: "2.0"
    restart: unless-stopped

volumes:
  expertise_ai_data:
```

```bash
docker compose -f docker/docker-compose.fast.yml up --build -d
```

Indicado para desenvolvimento local e iteracao rapida.

#### Container com build completo

Exemplo de compose:

```yaml
services:
  expertise-ai:
    build:
      context: ..
      dockerfile: Dockerfile
      args:
        EXPAI_DOCLING_PREFETCH_MODELS: "true"
    env_file:
      - ../.env
    ports:
      - "8000:8000"
    volumes:
      - ../data:/app/data
```

```bash
docker compose -f docker/docker-compose.build.yml up --build -d
```

Indicado para imagem completa, com foco em operacao offline.

## Documentacao tecnica

- [Visao geral da documentacao](./docs/README.md)
- [Arquitetura e persistencia](./docs/architecture.md)
- [Controle de acesso e aprovacao](./docs/access-control.md)
- [Deploy e operacao](./docs/deployment.md)
- [API principal](./docs/api.md)
- [MCP para agentes de IA](./docs/mcp.md)
- [Frontend e experiencia de uso](./docs/frontend.md)

## Repositorio oficial

- [github.com/gustavocaloi/ExpertiseAI](https://github.com/gustavocaloi/ExpertiseAI)

## Licenca

Este projeto esta licenciado sob a [MIT License](LICENSE).

O MVP simulado está disponível em **Monitoria → Carregar demonstração**. Consulte [fluxos, APIs e limitações](docs/monitoria.md).


### Docker local e arquivos sob demanda no macOS

Se o container reportar `disk I/O error` no SQLite ou nos documentos, verifique se os arquivos de `data/` estão disponíveis localmente. Nesta máquina, arquivos marcados `dataless` no diretório compartilhado impediram leituras pelo Docker. Materialize os arquivos pelo macOS antes de reiniciar; preserve o banco e faça backup antes de qualquer reparo. Reiniciar ou reconstruir a imagem não substitui a recuperação do acesso aos arquivos. O comando `ls -lO data/system.sqlite3` ajuda a identificar o estado do arquivo; `/health` sozinho não comprova a leitura completa da base.

## Backup e restauração

Administradores de todas as empresas podem exportar e restaurar a plataforma em JSON pelo menu do usuário → **Backup e restauração**. Inclui usuários, senhas protegidas por hash, permissões, documentos, anexos e Monitoria. Restaurar substitui os dados atuais e exige novo login. Consulte [formato, permissões, limites e recuperação](docs/backup.md).
