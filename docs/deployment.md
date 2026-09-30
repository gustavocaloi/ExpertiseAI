# Deploy e Operacao

## Requisitos

### Desenvolvimento local

- Python 3.11+
- `pip`

### Container

- Docker
- Docker Compose

## Execucao local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Execucao em container

Antes de subir:

```bash
cp .env.example .env
```

### Build rapido local

```bash
./scripts/run-container-fast.sh
```

Caracteristicas:

- usa `docker/docker-compose.fast.yml`;
- reaproveita cache do Docker;
- nao usa `--no-cache`;
- nao faz prefetch dos modelos do `docling` no build;
- ideal para desenvolvimento e iteracao rapida.

### Build completo/offline

```bash
./scripts/run-container-build.sh
```

Caracteristicas:

- usa `docker/docker-compose.build.yml`;
- empacota os modelos do `docling` no build;
- mais lento;
- recomendado quando a imagem precisa subir pronta para operacao offline.

## Variaveis de ambiente importantes

- `EXPAI_APP_ENV`
- `EXPAI_ACCESS_CONTROL_ENABLED`
- `EXPAI_ALLOW_PUBLIC_COMPANY_CREATE`
- `EXPAI_BOOTSTRAP_DEFAULT_ADMIN`
- `EXPAI_DEFAULT_COMPANY_NAME`
- `EXPAI_DEFAULT_ADMIN_EMAIL`
- `EXPAI_DEFAULT_ADMIN_PASSWORD`
- `EXPAI_SUPER_ADMIN_USER`
- `EXPAI_SUPER_ADMIN_PASSWORD`
- `EXPAI_DOCLING_PREFETCH_MODELS`
- `EXPAI_MCP_ENABLED`
- `EXPAI_MCP_PATH`
- `EXPAI_MCP_ALLOWED_HOSTS`
- `EXPAI_MCP_ALLOWED_ORIGINS`

## Bootstrap inicial

Quando habilitado, o sistema cria empresa e admin padrao no primeiro startup sem base previa.

Credenciais padrao de desenvolvimento:

- usuario: `admin@expertise.ai.local`
- senha: `Admin@123`

## Persistencia

### Em volume de container

- `system.sqlite3`
- `kb_store`
- cache do `docling`

### Reset de ambiente

```bash
docker compose down -v
```

## Docling e operacao offline

- `EXPAI_DOCLING_PREFETCH_MODELS=true` empacota os modelos no build;
- `false` reduz tempo de build, mas exige download sob demanda no primeiro processamento.

## Observacoes operacionais

- `EXPAI_KB_STARTUP_MAINTENANCE_MODE=background` deixa o container responder ao healthcheck enquanto migracoes e rebuild de indice rodam em segundo plano;
- use `blocking` apenas quando quiser que a aplicacao espere a manutencao da base terminar antes de aceitar trafego;
- bases grandes podem emitir logs de migracao/rebuild no primeiro boot, mas o healthcheck nao deve mais falhar por causa desse trabalho;
- o MCP fica disponivel em `/mcp/` quando habilitado e exige controle de acesso ativo;
- o `.env` deve permanecer local, enquanto `.env.example` segue como referencia versionada.
