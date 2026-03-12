#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="docker/docker-compose.build.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Compose de build não encontrado: $COMPOSE_FILE"
  exit 1
fi

docker compose -f "$COMPOSE_FILE" build --no-cache
docker compose -f "$COMPOSE_FILE" up -d "$@"
