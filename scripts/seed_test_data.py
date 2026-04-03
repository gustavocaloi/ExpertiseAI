#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _request_json(method: str, url: str, payload: Optional[dict[str, Any]] = None, token: Optional[str] = None) -> Any:
    body = None
    headers = {
        "Accept": "application/json",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Erro de conexão: {exc}") from exc


def login(base_url: str, email: str, password: str, company_id: int) -> str:
    payload = {"email": email, "password": password, "company_id": company_id}
    data = _request_json("POST", f"{base_url}/api/v1/auth/login", payload)
    token = data.get("access_token") if isinstance(data, dict) else None
    if not token:
        raise RuntimeError("Falha ao autenticar: token não retornado.")
    return token


def create_area(base_url: str, company_id: int, name: str, token: Optional[str]) -> None:
    try:
        _request_json("POST", f"{base_url}/api/v1/empresas/{company_id}/areas", {"name": name}, token)
    except RuntimeError as exc:
        msg = str(exc)
        if "já" in msg or "exist" in msg:
            return
        print(f"[warn] área '{name}' não criada: {msg}")


def create_category(base_url: str, company_id: int, name: str, area: str, token: Optional[str]) -> None:
    try:
        _request_json(
            "POST",
            f"{base_url}/api/v1/empresas/{company_id}/categorias",
            {"name": name, "area": area},
            token,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "já" in msg or "exist" in msg:
            return
        print(f"[warn] categoria '{name}' não criada: {msg}")


def create_document(
    base_url: str,
    company_id: int,
    area: str,
    categoria: str,
    title: str,
    content: str,
    token: Optional[str],
    publish: bool,
    data_validade: Optional[str],
) -> None:
    payload = {
        "area": area,
        "categoria": categoria,
        "title": title,
        "slug": None,
        "content": content,
        "tags": ["seed", area.lower().replace(" ", "-")],
        "publicar": bool(publish),
        "data_validade": data_validade,
    }
    _request_json("POST", f"{base_url}/api/v1/empresas/{company_id}/documentos", payload, token)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed de áreas, categorias e documentos.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--company-id", type=int, default=1)
    parser.add_argument("--email", default=None, help="Email para login (opcional).")
    parser.add_argument("--password", default=None, help="Senha para login (opcional).")
    parser.add_argument("--documents", type=int, required=True, help="Quantidade de documentos a criar.")
    parser.add_argument("--areas", type=int, default=3, help="Quantidade de áreas.")
    parser.add_argument("--categories-per-area", type=int, default=3, help="Categorias por área.")
    parser.add_argument("--publish", action="store_true", help="Publicar todos os documentos.")
    parser.add_argument("--seed", type=int, default=42, help="Seed de aleatoriedade.")
    args = parser.parse_args()

    token = None
    if args.email and args.password:
        token = login(args.base_url, args.email, args.password, args.company_id)

    random.seed(args.seed)

    areas = [f"Area {i + 1}" for i in range(max(1, args.areas))]
    categorias = []
    for area in areas:
        create_area(args.base_url, args.company_id, area, token)
        for j in range(max(1, args.categories_per_area)):
            cat = f"Categoria {area.split()[-1]}-{j + 1}"
            create_category(args.base_url, args.company_id, cat, area, token)
            categorias.append((area, cat))

    total_docs = max(0, args.documents)
    for i in range(total_docs):
        area, categoria = categorias[i % len(categorias)]
        title = f"Documento {i + 1} - {area}/{categoria}"
        content = f"# {title}\n\nConteúdo gerado automaticamente para testes.\n"
        validade = (datetime.utcnow() + timedelta(days=(i % 60))).date().isoformat()
        create_document(
            args.base_url,
            args.company_id,
            area,
            categoria,
            title,
            content,
            token,
            args.publish,
            validade,
        )
        if (i + 1) % 10 == 0 or i + 1 == total_docs:
            print(f"Criados {i + 1}/{total_docs} documentos...")

    print("Concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
