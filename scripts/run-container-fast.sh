#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="docker/docker-compose.fast.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Compose rápido não encontrado: $COMPOSE_FILE"
  exit 1
fi

export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
export COMPOSE_DOCKER_CLI_BUILD="${COMPOSE_DOCKER_CLI_BUILD:-1}"

if ! docker compose -f "$COMPOSE_FILE" build; then
  echo "Fallback para build direto com docker (BuildKit/Bake falhou)."
  docker build \
    --build-arg EXPAI_DOCLING_PREFETCH_MODELS=false \
    -t expertise-ai:fast-local \
    -f "$ROOT_DIR/Dockerfile" \
    "$ROOT_DIR"
fi

docker compose -f "$COMPOSE_FILE" up -d "$@"

echo "Container iniciado com o fluxo rápido."
echo "Build com cache habilitado e sem prefetch de modelos do Docling no build."
