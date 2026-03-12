#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  echo "Arquivo .env não encontrado na raiz do projeto."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Ambiente virtual não encontrado. Criando .venv..."
  python3 -m venv .venv
fi

source .venv/bin/activate

set -a
while IFS='=' read -r key value; do
  [[ -z "$key" || "$key" == \#* ]] && continue
  if [[ "$key" == *\ * || "$key" == *\	* ]]; then
    continue
  fi
  value="${value%$'\r'}"
  value="$(echo "$value" | sed 's/^ *//; s/ *$//')"
  value="${value%\"}"
  value="${value#\"}"
  export "$key=$value"
done < .env
set +a

if [ "${EXPAI_DATA_DIR:-}" = "/app/data" ]; then
  export EXPAI_DATA_DIR="$(pwd)/data"
fi
export EXPAI_DATA_DIR="${EXPAI_DATA_DIR:-$(pwd)/data}"
export EXPAI_KB_ROOT="${EXPAI_DATA_DIR}/kb_store"
mkdir -p "$EXPAI_DATA_DIR"
mkdir -p "$EXPAI_KB_ROOT"

echo "Using data dir: $EXPAI_DATA_DIR"
echo "Using kb root:  $EXPAI_KB_ROOT"

uvicorn app.main:app --host "${EXPAI_HOST:-0.0.0.0}" --port "${EXPAI_PORT:-8000}" --reload
