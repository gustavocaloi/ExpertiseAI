# Expertise.AI

[![GitHub](https://img.shields.io/badge/GitHub-ExpertiseAI-181717?logo=github)](https://github.com/gustavocaloi/ExpertiseAI)
[![License: MIT](https://img.shields.io/badge/License-MIT-4d2d5e.svg)](https://opensource.org/license/MIT)
[![Docling](https://img.shields.io/badge/Docling-Read%20Docs-0d7b58?logo=readthedocs&logoColor=white)](https://docling-project.github.io/docling/)

## Plataforma de Base de Conhecimento

`Expertise.AI` é um sistema para centralizar, organizar e consultar conhecimento corporativo de forma rápida e rastreável.  
O objetivo é reduzir tempo de busca por informação, padronizar conteúdos e permitir reutilização de conhecimento em operações, suporte, onboarding e decisão.

A plataforma também pode ser utilizada como base de conhecimento para consulta de agentes de IA, favorecendo automação e respostas contextualizadas.

Repositório oficial no GitHub:
- [github.com/gustavocaloi/ExpertiseAI](https://github.com/gustavocaloi/ExpertiseAI)

## Estratégia de armazenamento

- **Base de conhecimento sem banco de dados relacional**: conteúdo armazenado em arquivos no sistema de arquivos.
- Estrutura principal:
  - `data/kb_store/` — diretório raiz da base.
  - `data/kb_store/<empresa_id>/_documents/<document_uuid>/` — pasta física do documento.
  - `data/kb_store/<empresa_id>/_documents/<document_uuid>/v1.md`, `v2.md`, ...
- `document.meta.json` em cada pasta de documento controla versão publicada e histórico.
- Cada versão é um arquivo independente e pode conter seu próprio frontmatter (version, data, autor, revisão).
- O estado "publicado" é definido por `document.meta.json` com o campo `published_version`.
- Também é possível controlar flags por versão dentro do próprio `frontmatter`.
- `área`, `categoria` e `slug` continuam existindo como metadados do documento, mas não definem mais sua identidade física em disco.
- A base de usuários e empresa é persistida em `SQLite` local (`data/system.sqlite3`).

Exemplo de separação:
- `data/kb_store/`: estrutura de arquivos Markdown por versão (conteúdo da base).
- `data/system.sqlite3` (SQLite): usuários, empresas, permissões, vínculos usuário-empresa e perfis.

### Modelo de multi-empresa e perfis

- **Multi-empresa (multi-tenant)**: cada usuário pertence a uma empresa (cliente) e enxerga somente dados administrativos e permissões da sua empresa, com escopo por organização.
- **Multi-usuários por empresa**: cada empresa pode ter vários usuários vinculados.
- Perfis de acesso fixos:
  - `admin`: administra usuários, perfis, políticas e configurações da empresa.
  - `editor`: cria e edita conteúdos, cria novas versões e solicita publicação.
  - `revisor`: valida e aprova versões para publicação.
- O vínculo `usuário -> empresa -> perfil` é persistido em SQLite e aplicado como filtro de permissão na API e na UI.

Exemplo de frontmatter:

```md
---
id: onboarding-mensageria
titulo: Guia de Onboarding da Mensageria
area: suporte
categoria: processos
tags: [onboarding, processos, suporte]
status: revisado
autor: equipe-ops
versao: 2
publicada: false
revisado_em: 2026-03-09
---

---
documento: onboarding-mensageria
publicado_em: 2026-03-09
versao_publicada: 2
arquivo_publicado: v2.md
---
```

## Funcionalidades

### 1. Gestão de documentos e fontes de conhecimento
- **Criação de base por upload**: página dedicada para importação de arquivos PDF ou Word (`.pdf`, `.docx`) durante a criação do documento.
- **Conversão automática com Docling**: ao subir o arquivo, a integração com a biblioteca `docling` gera a versão em Markdown padronizada para revisão e publicação.
- Possibilidade de o usuário revisar a formatação final antes de salvar a versão oficial no repositório de arquivos.
- Cadastro de documentos por tipo: texto, arquivos (PDF, DOCX, Markdown), links e páginas web.
- Extração automática de conteúdo e metadados (quando aplicável).
- Normalização de textos para indexação (limpeza, chunking e indexação).
- Controle de versão de conteúdos (histórico de edição por documento), com seleção manual da versão ativa.
- Status de validação por publicação (rascunho, revisado, publicado, arquivado).
- Campos de classificação (área, produto, equipe, prioridade, linguagem, tags).

### 2. Organização estrutural
- Estrutura hierárquica por pastas (área/categoria/subcategoria) para organizar o conteúdo da base.
- Organização visual e funcional por pastas é feita no lado da navegação e refletida no path dos arquivos.
- Sistema de tags (metadados por documento/versão) para organização alternativa e busca transversal.
- Painel de taxonomia para padronizar terminologias e evitar duplicidade de informação.
- Recomendação de links relacionados entre artigos.

3. Busca e descoberta de conhecimento
- Busca textual full-text (palavras-chave, frases e filtros).
- Busca semântica por significado (consultas em linguagem natural).
- Filtros por domínio, produto, equipe, autor, período e status.
- Ordenação por relevância, atualização e popularidade.
- Destaque (highlight) dos termos encontrados.

### 4. Chat interno / perguntas e respostas
- Consulta por pergunta livre com retorno de trechos mais relevantes.
- Exibição de fontes consultadas em cada resposta.
- Respostas com contexto (período, seção e confiança).
- Opção de solicitar aprofundamento para uma fonte específica.
- Feedback de usuário (útil / não útil) para melhoria contínua.

### 5. Acesso por times e perfis
- Controle de acesso por função (admin, editor, revisor) dentro do contexto de cada empresa.
- Permissões por coleção, categoria e documento.
- Trilhas de aprovação para publicação de conteúdos críticos.
- Auditoria de ações (quem criou, alterou, revisou e aprovou).

### 6. Colaboração e revisão
- Edição colaborativa de artigos.
- Comentários e sugestões de melhoria por trecho.
- Aprovação por múltiplos revisores antes de publicar.
- Menções e solicitações de revisão entre colegas.
- Alertas de expiração e revisão periódica de conteúdos sensíveis.

### 7. Integrações
- API para integração com bots, CRM, help desk e dashboards.
- Webhooks para eventos (novo documento, atualização, revisão pendente, publicação).
- Importação automática de dados de outras fontes internas.
- Sincronização com ferramentas de autenticação corporativa.
- Rota de consulta de publicação por empresa:
  - `GET /api/v1/empresas/{empresaId}/documentos/publicados`
  - Retorna apenas as versões ativas/publicadas da base de conhecimento daquela empresa.
  - Suporte recomendado de filtros: `?area=`, `?categoria=`, `?tag=`, `?busca=`, `?limit=`, `?offset=`.
  - Controle de acesso por JWT/API token + validação de escopo da empresa.
  - Campo adicional por documento: `data_validade` (formato `YYYY-MM-DD`) para controle de expiração.

### 8. Observabilidade e governança
- Métricas de uso: acessos, busca mais frequente, artigos críticos.
- Relatórios de gargalos (perguntas sem resposta, tempo de resposta, artigos obsoletos).
- Logs de trilha de auditoria.
- Painel administrativo com visão de saúde de conteúdo.

### 9. Qualidade da informação
- Deteção automática de conteúdo duplicado.
- Alertas de links quebrados e referências inválidas.
- Check de consistência terminológica e estrutura de resposta.
- Gestão de versões para rollback.

## Benefícios esperados
- Redução de tempo de busca por informação.
- Menos retrabalho por falta de padrão.
- Conhecimento centralizado e menos dependente de pessoas específicas.
- Maior previsibilidade nas respostas de times de atendimento e operações.
- Tomada de decisão mais baseada em informação consolidada.

## Estrutura sugerida (futuras seções técnicas)
- Arquitetura geral
- Requisitos e instalação
- Variáveis de ambiente
- Documentação da API
- Padrões de contribuição
- Políticas de segurança e compliance

---

`Expertise.AI` — Sistema de base de conhecimento para escalar inteligência organizacional.

## Implementação da plataforma (MVP)

Este projeto já possui um esqueleto funcional em FastAPI com:

- Multi-empresa (cada empresa tem pasta dedicada na base de conhecimento).
- Autenticação por JWT com perfis: `admin`, `editor`, `revisor`.
- Base de conhecimento em arquivos `.md` versionados por documento.
- Banco SQLite local para usuários, empresas e relação usuário-empresa-perfil.
- Rota de consulta pública por empresa dos documentos publicados.
- Upload de PDF/DOCX com tentativa de conversão via `docling` para Markdown.

### Estrutura do projeto

- `app/`: código da API.
- `data/system.sqlite3`: banco SQLite para dados de administração.
- `data/kb_store/`: arquivos da base de conhecimento por empresa.

### Arquitetura de armazenamento

- `SQLite`:
  - `users`
  - `companies`
  - `user_company_roles` (`admin`, `editor`, `revisor`)
- Arquivos:
  - `data/kb_store/<empresa_id>/_documents/<document_uuid>/v{n}.md`
  - `data/kb_store/<empresa_id>/_documents/<document_uuid>/document.meta.json`

### Persistência e migração

- A identidade física do documento agora é baseada em `empresa_id + document_uuid`.
- `área`, `categoria` e `slug` são metadados editáveis e podem mudar sem criar um novo documento físico.
- O startup da aplicação executa uma migração automática dos documentos legados para o layout novo por empresa.
- A migração preserva `document_uuid`, versões, anexos e metadados existentes.
- As rotas atuais continuam compatíveis e ainda aceitam `área/categoria/slug` para localizar o documento.

### Como executar (desenvolvimento)

Pré-requisitos:

- Python 3.11+
- pip

Instalação:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Como executar em container (Docker)

Pré-requisitos:

- Docker
- Docker Compose

Comandos:

```bash
cp .env.example .env
docker compose up --build -d
```

### Modelos Docling offline no container

- A variável `EXPAI_DOCLING_PREFETCH_MODELS` controla o modo offline dos modelos usados pelo `docling` no processamento de PDF.
- Em build de imagem, `EXPAI_DOCLING_PREFETCH_MODELS=true` faz o download dos modelos durante o `docker build` e os empacota dentro da imagem.
- No startup do container, esse bundle é restaurado para `/app/data/docling_cache` quando o volume de dados estiver vazio.
- Com isso, o processamento de PDF pode funcionar sem internet na máquina de destino.
- Se `EXPAI_DOCLING_PREFETCH_MODELS=false`, a imagem não empacota os modelos e o primeiro processamento de PDF dependerá de acesso à internet para popular o cache.
- No compose com imagem publicada (`docker/docker-compose.yml`), a variável documenta essa expectativa operacional, mas o comportamento offline real depende de a imagem já ter sido buildada/publicada com o prefetch habilitado.
- Se a máquina tiver internet apenas via proxy, configure `HTTP_PROXY`, `HTTPS_PROXY` e `NO_PROXY`. No compose de build, essas variáveis são repassadas tanto para o `docker build` quanto para o runtime do container.

URL de acesso:

- http://127.0.0.1:8000

Comandos úteis:

```bash
docker compose logs -f
docker compose ps
docker compose down
```

Limites operacionais do container:

- Os composes do projeto limitam o serviço `expertise-ai` em:
  - `memory: 6g`
  - `cpus: 2.0`
- Esses limites foram definidos para manter o container estável durante conversão de PDF/DOCX com `docling`, reduzindo o risco de o processo web competir com a conversão pesada.

Persistência:

- O volume `expertise_ai_data` armazena:
  - `system.sqlite3`
  - `kb_store` e versões da base de conhecimento

Para resetar o estado dos dados (sem excluir código):

```bash
docker compose down -v
```

### Referência operacional para processamento de PDF

Baseado no histórico real deste projeto, com a configuração atual:

- `EXPAI_DOCLING_PDF_PAGE_BATCH_SIZE=10`
- `EXPAI_DOCLING_OCR_ENABLED=false`
- `EXPAI_DOCLING_TABLE_STRUCTURE_ENABLED=false`
- `EXPAI_DOCLING_THREADS=2`

Observações confirmadas:

- PDF pequeno concluiu com sucesso no container após os ajustes de chunking e redução de custo do pipeline.
- Um PDF de `359` páginas e aproximadamente `4 MB` chegou a falhar antes com `returncode=-9`, o que é compatível com `SIGKILL/OOM` no subprocesso do `docling`.
- Após ativar chunking real, batch de `10` páginas e desabilitar OCR/tabelas, o processamento grande voltou a funcionar de forma estável no ambiente atual.

Guia prático de capacidade:

- até `50` páginas:
  - tende a operar bem com `2 GB` a `3 GB` de RAM
  - `1` a `2` vCPUs
- de `50` a `200` páginas:
  - recomenda-se `4 GB` de RAM
  - `2` vCPUs
- de `200` a `400` páginas:
  - recomenda-se `6 GB` de RAM
  - `2` vCPUs
  - manter chunking em `10` páginas por lote
- acima de `400` páginas:
  - exige validação no ambiente real
  - pode requerer aumento de memória, redução adicional do batch ou processamento dedicado fora do processo web

Importante:

- Esses números não são benchmark científico; são uma referência operacional inferida a partir do comportamento observado nos logs e da estabilização obtida com os ajustes atuais.
- Se OCR ou estrutura de tabelas forem reativados, a necessidade de CPU e memória sobe significativamente.

### Endpoints principais

- `POST /api/v1/empresas` — cria empresa e usuário admin inicial.
- `POST /api/v1/auth/login` — autenticação e emissão de JWT.
- `POST /api/v1/empresas/{empresa_id}/documentos` — cria/atualiza documento via texto markdown.
- `POST /api/v1/empresas/{empresa_id}/documentos/upload` — upload de PDF/DOCX com conversão para `.md`.
- `PUT /api/v1/empresas/{empresa_id}/documentos/{area}/{categoria}/{slug}/publicar` — define a versão publicada.
- `GET /api/v1/empresas/{empresa_id}/documentos/publicados` — consulta documentos publicados da empresa (obrigatório).
- `GET /api/v1/config` — retorna configuração pública da plataforma (ex.: `access_control_enabled`).
- `GET /api/v1/empresas/{empresa_id}/documentos/{area}/{categoria}/{slug}` — lista versões do documento.
- `GET /api/v1/empresas/{empresa_id}/documentos/{area}/{categoria}/{slug}/conteudo` — retorna o conteúdo da versão publicada por padrão (popup de visualização) e aceita `?version=<n>` para carregar qualquer versão no preview da linha do tempo.
- `GET /api/v1/empresas/{empresa_id}/usuarios` — lista usuários da empresa (admin).
- `POST /api/v1/empresas/{empresa_id}/usuarios` — cria/vincula usuário com perfil (admin).

### Script de seed (teste)

Para cadastrar áreas, categorias e documentos automaticamente, use:

```bash
python3 scripts/seed_test_data.py --documents 50 --areas 3 --categories-per-area 4
```

Com autenticação:

```bash
python3 scripts/seed_test_data.py --documents 50 --email admin@expertise.ai.local --password Admin@123 --company-id 1
```

Parâmetros principais:

- `--documents` (obrigatório) — quantidade de documentos a criar.
- `--areas` — quantidade de áreas (padrão: `3`).
- `--categories-per-area` — categorias por área (padrão: `3`).
- `--publish` — publica todos os documentos criados.
- `--base-url` — URL base da API (padrão: `http://localhost:8000`).
- `--company-id` — empresa alvo (padrão: `1`).

### Exemplo de autenticação

```bash
POST /api/v1/auth/login
{
  "email": "admin@empresa.com",
  "password": "senha",
  "company_id": 1
}
```

## Acesso inicial com admin padrão

Ao iniciar a plataforma sem dados de base, é criado automaticamente um tenant padrão com admin padrão:

- Empresa padrão: `EXPAI_DEFAULT_COMPANY_NAME` (slug `expai`)
- Descrição padrão da empresa: `EXPAI_DEFAULT_COMPANY_DESCRIPTION`
- Usuário padrão:
  - email: `admin@expertise.ai.local`
  - senha: `Admin@123`

Esses valores podem ser alterados por variáveis de ambiente:

- `EXPAI_DEFAULT_COMPANY_NAME`
- `EXPAI_DEFAULT_COMPANY_DESCRIPTION`
- `EXPAI_DEFAULT_COMPANY_SLUG`
- `EXPAI_DEFAULT_ADMIN_NAME`
- `EXPAI_DEFAULT_ADMIN_EMAIL`
- `EXPAI_DEFAULT_ADMIN_PASSWORD`
- `EXPAI_SUPER_ADMIN_USER`
- `EXPAI_SUPER_ADMIN_PASSWORD`
- `EXPAI_BOOTSTRAP_DEFAULT_ADMIN` (`true` ou `false`)
- `EXPAI_ACCESS_CONTROL_ENABLED` (`true` ou `false`)
- `EXPAI_API_BASE_URL` (ex.: `http://localhost:8000`, usada na documentação Swagger/OpenAPI)

Recomenda-se alterar a senha padrão logo no primeiro acesso.

Também é possível definir a identidade padrão do super admin para operações em modo sem autenticação:

- `EXPAI_SUPER_ADMIN_USER` (padrão: `superadmin`)
- `EXPAI_SUPER_ADMIN_PASSWORD` (padrão: `Admin@123`)

### Acesso sem autenticação

Ao definir:
- `EXPAI_ACCESS_CONTROL_ENABLED=false`

o sistema entra em modo sem controle de usuários:

- A interface carrega diretamente no painel principal sem exigir login.
- As rotas continuam operando sem token/JWT.
- Toda alteração em documentos grava autoria como `anônimo`.
- A sessão de administração de usuários é ocultada no frontend.

### Usuário e senha padrão (desenvolvimento)

Para ambiente local novo, a primeira autenticação pode ser feita com:

- Usuário: `admin@expertise.ai.local`
- Senha: `Admin@123`

Observações:

- O usuário padrão é criado apenas no bootstrap inicial (`BOOTSTRAP_DEFAULT_ADMIN=true`).
- Se você rodar a plataforma sem esse valor habilitado, crie o tenant e admin via fluxo administrativo antes do primeiro login.
- Troque a senha padrão no primeiro acesso para produção.

## Interface gráfica (frontend)

Foi adicionada uma interface web em `app/static/` com visual moderno, neutro e suave, voltada para a operação da base de conhecimento.

- Acesso:
  - `http://127.0.0.1:8000/`
- Funcionalidades disponíveis:
  - Login por empresa (JWT).
- Consulta de documentos publicados por filtros (`área`, `categoria`, `tag`, `busca`).
- Sessão de administração de usuários no menu do avatar (visível apenas para perfil `admin`) para criar novos usuários e visualizar usuários da empresa.
- Visualização rápida: clique em um documento publicado para abrir popup com o conteúdo.
- Criação/edição de documento em Markdown.
- Timeline de versões na sessão de edição mostrando histórico de alterações e marcador da versão publicada.
- Upload de arquivo PDF/DOCX com conversão via Docling.
- Publicação de versão específica por slug.

Arquivos da interface:
- `app/static/index.html`
- `app/static/styles.css`
- `app/static/app.js`

A interface foi organizada em **sessões separadas** com menu horizontal no topo. Cada sessão mostra apenas a funcionalidade solicitada pelo usuário:
- Início (lista de publicados + filtros)
- Criar/Editar documento
- Upload com Docling
- Publicar versão

Estrutura visual:
- Paleta neutra de papel, pedra, grafite e dourado discreto.
- Tipografia com contraste de leitura e hierarquia editorial.
- Cards limpos, animações leves e separação clara por tarefas.

### Convenção de versão publicada

- Cada documento possui `document.meta.json` com `published_version`.
- Só a versão marcada como publicada é retornada na rota de consulta publicada.

### Upload e conversão (Docling)

- O upload de PDF/DOCX aciona conversor:
  - Tenta usar `docling.document_converter.DocumentConverter`.
  - Se indisponível, retorna erro de conversão com mensagem explícita para instalação/configuração.

## Licença

Este projeto está licenciado sob a [MIT License](LICENSE).
