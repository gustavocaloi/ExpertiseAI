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

- a primeira subida apos mudancas estruturais pode executar migracoes e rebuild de indice;
- bases grandes podem levar mais tempo no primeiro boot e depois estabilizam;
- o `.env` deve permanecer local, enquanto `.env.example` segue como referencia versionada.
