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


class AuthSession:
    def __init__(self, access_token: str, refresh_token: Optional[str] = None) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token or ""


def _request_json(method: str, url: str, payload: Optional[dict[str, Any]] = None, token: Optional[str] = None) -> Any:
    body = None
    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
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


def login(base_url: str, email: str, password: str, company_id: int) -> AuthSession:
    payload = {"email": email, "password": password, "company_id": company_id}
    data = _request_json("POST", f"{base_url}/api/v1/auth/login", payload)
    if not isinstance(data, dict):
        raise RuntimeError("Falha ao autenticar: resposta inválida.")
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if not access_token:
        raise RuntimeError("Falha ao autenticar: access_token não retornado.")
    return AuthSession(access_token=access_token, refresh_token=refresh_token)


def refresh_session(base_url: str, session: AuthSession) -> AuthSession:
    if not session.refresh_token:
        raise RuntimeError("Falha ao renovar sessão: refresh_token não retornado no login.")
    data = _request_json(
        "POST",
        f"{base_url}/api/v1/auth/refresh",
        {"refresh_token": session.refresh_token},
    )
    if not isinstance(data, dict):
        raise RuntimeError("Falha ao renovar sessão: resposta inválida.")
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if not access_token:
        raise RuntimeError("Falha ao renovar sessão: access_token não retornado.")
    session.access_token = access_token
    session.refresh_token = refresh_token or session.refresh_token
    return session


def request_json_with_auth(
    method: str,
    url: str,
    payload: Optional[dict[str, Any]],
    base_url: str,
    session: Optional[AuthSession],
) -> Any:
    if session is None:
        return _request_json(method, url, payload, None)
    try:
        return _request_json(method, url, payload, session.access_token)
    except RuntimeError as exc:
        message = str(exc)
        if "HTTP 401" not in message or not session.refresh_token:
            raise
        refresh_session(base_url, session)
        return _request_json(method, url, payload, session.access_token)


def create_area(base_url: str, company_id: int, name: str, session: Optional[AuthSession]) -> None:
    try:
        request_json_with_auth(
            "POST",
            f"{base_url}/api/v1/empresas/{company_id}/areas",
            {"name": name},
            base_url,
            session,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "já" in msg or "exist" in msg:
            return
        print(f"[warn] área '{name}' não criada: {msg}")


def create_category(base_url: str, company_id: int, name: str, area: str, session: Optional[AuthSession]) -> None:
    try:
        request_json_with_auth(
            "POST",
            f"{base_url}/api/v1/empresas/{company_id}/categorias",
            {"name": name, "area": area},
            base_url,
            session,
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
    session: Optional[AuthSession],
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
    request_json_with_auth(
        "POST",
        f"{base_url}/api/v1/empresas/{company_id}/documentos",
        payload,
        base_url,
        session,
    )


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

    session = None
    if args.email and args.password:
        session = login(args.base_url, args.email, args.password, args.company_id)

    random.seed(args.seed)

    areas = [f"Area {i + 1}" for i in range(max(1, args.areas))]
    categorias = []
    for area in areas:
        create_area(args.base_url, args.company_id, area, session)
        for j in range(max(1, args.categories_per_area)):
            cat = f"Categoria {area.split()[-1]}-{j + 1}"
            create_category(args.base_url, args.company_id, cat, area, session)
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
            session,
            args.publish,
            validade,
        )
        if (i + 1) % 10 == 0 or i + 1 == total_docs:
            print(f"Criados {i + 1}/{total_docs} documentos...")

    print("Concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
