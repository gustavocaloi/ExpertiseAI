#!/usr/bin/env python3
"""Mede p50/p95 de listagem e busca local (sem HTTP) em 1k/5k/10k documentos."""
from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    rank = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[rank]


def _setup_store(data_dir: Path) -> None:
    from app import config, db, services

    kb_root = data_dir / "kb_store"
    db_path = data_dir / "system.sqlite3"
    data_dir.mkdir(parents=True, exist_ok=True)
    kb_root.mkdir(parents=True, exist_ok=True)
    config.DATA_DIR = data_dir
    config.KB_ROOT = kb_root
    config.DB_PATH = db_path
    db.DB_PATH = db_path
    services.KB_ROOT = kb_root
    db.init_db()


def _seed(company_id: int, total: int) -> None:
    """Grava documentos e rebuilda o indice uma vez (evita O(n^2) no seed)."""
    from uuid import uuid4

    from app import services

    marker_every = max(1, total // 20)
    rebuilding = getattr(services._DOCUMENT_INDEX_REBUILDING, "companies", None)
    if rebuilding is None:
        rebuilding = set()
        services._DOCUMENT_INDEX_REBUILDING.companies = rebuilding
    rebuilding.add(company_id)
    try:
        for index in range(total):
            token = f"marcaunica{index}" if index % marker_every == 0 else f"conteudo{index}"
            document_uuid = str(uuid4())
            area = "geral"
            categoria = "ops"
            slug = f"doc-{index:05d}"
            title = f"Documento {index:05d}"
            content = f"Documento de carga {index}. Termo {token}. " + ("lorem ipsum " * 40)
            version = "1"
            meta = {
                "document_uuid": document_uuid,
                "storage_version": getattr(services, "DOCUMENT_STORAGE_VERSION", 2),
                "slug": slug,
                "title": title,
                "empresa_id": company_id,
                "area": area,
                "categoria": categoria,
                "tags": ["bench", f"tag{index % 7}"],
                "ai_prompt": "",
                "data_validade": "",
                "created_at": services._now(),
                "updated_at": services._now(),
                "published_version": version,
                "versions": [
                    {
                        "version": version,
                        "version_uuid": str(uuid4()),
                        "file": f"v{version}.md",
                        "author": "bench@example.com",
                        "created_at": services._now(),
                        "published": True,
                        "published_at": services._now(),
                        "approved_by": "bench@example.com",
                        "pending_approval": False,
                        "pending_approval_at": None,
                        "ai_prompt": "",
                    }
                ],
                "attachments": [],
            }
            version_path = services._version_path(
                company_id, area, categoria, slug, version, document_uuid=document_uuid
            )
            version_path.parent.mkdir(parents=True, exist_ok=True)
            now = services._now()
            payload = services._frontmatter(
                content,
                {
                    "title": title,
                    "slug": slug,
                    "empresa_id": company_id,
                    "area": area,
                    "categoria": categoria,
                    "version": version,
                    "author": "bench@example.com",
                    "published": True,
                    "published_at": now,
                    "approved_by": "bench@example.com",
                    "pending_approval": False,
                    "pending_approval_at": "",
                    "created_at": now,
                    "updated_at": now,
                    "data_validade": "",
                    "tags": meta["tags"],
                    "ai_prompt": "",
                },
            )
            version_path.write_text(payload, encoding="utf-8")
            services._write_meta(
                services._meta_path(company_id, area, categoria, slug, document_uuid=document_uuid),
                meta,
            )
            if (index + 1) % 500 == 0:
                print(f"  seed {index + 1}/{total}", flush=True)
    finally:
        rebuilding.discard(company_id)

    services._rebuild_documents_index(company_id)
    print(f"  indice rebuildado para {total} documentos", flush=True)


def _measure(label: str, rounds: int, fn) -> dict[str, float]:
    samples: list[float] = []
    for _ in range(rounds):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000.0)
    return {
        "label": label,
        "rounds": float(rounds),
        "p50_ms": statistics.median(samples),
        "p95_ms": _percentile(samples, 95),
        "avg_ms": statistics.fmean(samples) if hasattr(statistics, "fmean") else (sum(samples) / len(samples)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", default="1000,5000,10000", help="Totais de documentos separados por virgula")
    parser.add_argument("--rounds", type=int, default=30, help="Repeticoes por cenario")
    parser.add_argument("--keep-dir", default="", help="Diretorio persistente (padrao: temp)")
    args = parser.parse_args()

    sizes = [int(item.strip()) for item in str(args.sizes).split(",") if item.strip()]
    if not sizes:
        raise SystemExit("Informe ao menos um tamanho em --sizes")

    from app import services

    rows: list[dict[str, float]] = []
    for total in sizes:
        base = Path(args.keep_dir) if args.keep_dir else Path(tempfile.mkdtemp(prefix=f"expai-bench-{total}-"))
        company_dir = base / f"n{total}"
        print(f"\n=== {total} documentos em {company_dir} ===", flush=True)
        _setup_store(company_dir)
        company_id = 1
        _seed(company_id, total)

        rows.append(
            _measure(
                f"list page n={total}",
                args.rounds,
                lambda: services.read_published_documents(
                    company_id=company_id,
                    limit=10,
                    offset=0,
                    include_content=False,
                    return_total=True,
                ),
            )
        )
        rows.append(
            _measure(
                f"search hit n={total}",
                args.rounds,
                lambda: services.read_published_documents(
                    company_id=company_id,
                    busca="marcaunica0",
                    limit=10,
                    offset=0,
                    include_content=False,
                    return_total=True,
                ),
            )
        )
        rows.append(
            _measure(
                f"search miss n={total}",
                args.rounds,
                lambda: services.read_published_documents(
                    company_id=company_id,
                    busca="termoinexistentezzz",
                    limit=10,
                    offset=0,
                    include_content=False,
                    return_total=True,
                ),
            )
        )

    print("\nresultado (ms)")
    print(f"{'cenario':40} {'p50':>10} {'p95':>10} {'avg':>10}")
    for row in rows:
        print(
            f"{row['label']:40} {row['p50_ms']:10.2f} {row['p95_ms']:10.2f} {row['avg_ms']:10.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
