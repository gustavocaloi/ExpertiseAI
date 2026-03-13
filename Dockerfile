# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir --no-compile -r requirements.txt

FROM python:3.11-slim

ARG EXPAI_DOCLING_PREFETCH_MODELS=true
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EXPAI_DATA_DIR=/app/data \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    HF_HOME=/app/data/docling_cache/huggingface \
    HUGGINGFACE_HUB_CACHE=/app/data/docling_cache/huggingface \
    DOCLING_CACHE_DIR=/app/data/docling_cache \
    EXPAI_DOCLING_BUNDLED_CACHE_DIR=/opt/docling-models \
    XDG_CACHE_HOME=/app/data/docling_cache

ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY app ./app
RUN mkdir -p /app/data/docling_cache/huggingface /opt/docling-models \
 && if [ "$EXPAI_DOCLING_PREFETCH_MODELS" = "true" ]; then python /app/app/prefetch_docling_models.py --cache-dir /opt/docling-models; fi

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
