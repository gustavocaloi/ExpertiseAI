#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="docker/docker-compose.build.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Compose de build não encontrado: $COMPOSE_FILE"
  exit 1
fi

if ! docker compose -f "$COMPOSE_FILE" build --no-cache; then
  echo "Fallback para build direto com docker (BuildKit/Bake falhou)."
  docker build -t docker-expertise-ai -f "$ROOT_DIR/Dockerfile" "$ROOT_DIR"
fi

docker compose -f "$COMPOSE_FILE" up -d "$@"
