from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional
from urllib.parse import urlparse

from . import db, services
from .config import (
    ACCESS_CONTROL_ENABLED,
    API_BASE_URL,
    MCP_ALLOWED_HOSTS,
    MCP_ALLOWED_ORIGINS,
    MCP_ENABLED,
    MCP_ISSUER_URL,
    MCP_MAX_CONTENT_CHARS,
    MCP_MAX_PAGE_SIZE,
    MCP_MAX_REQUEST_BODY_SIZE,
    MCP_MAX_SESSIONS,
    MCP_PATH,
    MCP_REQUIRED,
    MCP_REQUIRED_SCOPES,
    MCP_RESOURCE_SERVER_URL,
    MCP_SESSION_IDLE_TIMEOUT_SECONDS,
)
from .security import TokenData, decode_access_token, user_has_required_role

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class McpComponent:
    server: Any
    app: Any
    mount_path: str


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit or 1), max(1, MCP_MAX_PAGE_SIZE)))


def _safe_offset(offset: int) -> int:
    return max(0, int(offset or 0))


def _parse_iso_date(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} deve estar no formato YYYY-MM-DD.") from exc


def _is_valid_for_agents(data_validade: Any) -> bool:
    raw = str(data_validade or "").strip()
    if not raw:
        return True
    try:
        return date.fromisoformat(raw) >= date.today()
    except ValueError:
        return False


def _public_document_payload(item: dict[str, Any], include_content: bool = False) -> dict[str, Any]:
    allowed_keys = {
        "document_uuid",
        "empresa_id",
        "slug",
        "titulo",
        "area",
        "categoria",
        "tags",
        "ai_prompt",
        "data_validade",
        "attachments",
        "version",
        "published_version_uuid",
        "published_version",
        "satellite_document_id",
        "satellite_version_id",
        "created_at",
        "updated_at",
    }
    payload = {key: item.get(key) for key in allowed_keys if key in item}
    if include_content and "content" in item:
        content = str(item.get("content") or "")
        payload["content"] = content[:MCP_MAX_CONTENT_CHARS]
        payload["content_truncated"] = len(content) > MCP_MAX_CONTENT_CHARS
    return payload


def _allowed_areas_for_user(company_id: int, user: TokenData) -> Optional[set[str]]:
    if not ACCESS_CONTROL_ENABLED or user_has_required_role(user, "admin"):
        return None
    scope = db.get_effective_user_area_scope(user.user_id, company_id).get("effective_scope", {})
    if scope.get("mode") != "selected":
        return None
    allowed_areas = {services._sanitize(area) for area in (scope.get("areas") or []) if str(area or "").strip()}
    allowed_areas.add(services.DEFAULT_AREA)
    return allowed_areas


def _require_company_context(company_id: int) -> tuple[TokenData, Optional[set[str]]]:
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token
    except ImportError as exc:  # pragma: no cover - guarded by create_mcp_component.
        raise RuntimeError("MCP SDK indisponível.") from exc

    access_token = get_access_token()
    if access_token is None:
        raise PermissionError("Token MCP ausente ou inválido.")

    claims = access_token.claims or {}
    token_company_id = int(claims.get("company_id") or 0)
    if ACCESS_CONTROL_ENABLED and token_company_id != int(company_id):
        raise PermissionError("Token fora do contexto da empresa.")

    user_id = int(claims.get("user_id") or access_token.subject or 0)
    email = str(claims.get("email") or access_token.client_id or "")
    roles = db.get_user_roles_in_company(user_id, int(company_id)) if ACCESS_CONTROL_ENABLED else ["admin"]
    role = db.resolve_effective_role(roles) if ACCESS_CONTROL_ENABLED else "admin"
    if ACCESS_CONTROL_ENABLED and (not roles or not role or not db.get_user_by_id(user_id)):
        raise PermissionError("Usuário sem acesso ativo à empresa.")

    user = TokenData(
        sub=str(user_id),
        user_id=user_id,
        company_id=int(company_id),
        role=role or "admin",
        email=email,
        roles=roles,
    )
    return user, _allowed_areas_for_user(int(company_id), user)


def _assert_area_access(company_id: int, area: Optional[str], allowed_areas: Optional[set[str]]) -> None:
    if allowed_areas is None:
        return
    normalized_area = services._sanitize(area or services.DEFAULT_AREA)
    if normalized_area not in allowed_areas:
        raise PermissionError("Usuário sem acesso à área informada.")


def _assert_document_visible_to_user(
    company_id: int,
    meta: dict[str, Any],
    allowed_areas: Optional[set[str]],
    include_expired: bool,
) -> None:
    _assert_area_access(company_id, str(meta.get("area") or services.DEFAULT_AREA), allowed_areas)
    if not str(meta.get("published_version") or "").strip():
        raise FileNotFoundError("Documento ainda não possui versão publicada.")
    if not include_expired and not _is_valid_for_agents(meta.get("data_validade")):
        raise FileNotFoundError("Documento expirado indisponível para consumo MCP.")


class ExpertiseTokenVerifier:
    async def verify_token(self, token: str) -> Any:
        from mcp.server.auth.provider import AccessToken

        if not ACCESS_CONTROL_ENABLED:
            logger.warning("MCP recusou autenticação porque o controle de acesso está desabilitado.")
            return None

        try:
            token_data = decode_access_token(token, expected_token_type="access")
        except Exception:
            return None

        user = db.get_user_by_id(token_data.user_id)
        if not user:
            return None
        roles = db.get_user_roles_in_company(token_data.user_id, token_data.company_id)
        if not roles or not db.resolve_effective_role(roles):
            return None

        return AccessToken(
            token=token,
            client_id=token_data.email or str(token_data.user_id),
            scopes=list(MCP_REQUIRED_SCOPES or ["kb:read"]),
            subject=str(token_data.user_id),
            claims={
                "user_id": token_data.user_id,
                "company_id": token_data.company_id,
                "email": token_data.email,
                "roles": roles,
            },
        )


def _host_from_url(value: str) -> Optional[str]:
    parsed = urlparse(value)
    return parsed.netloc or None


def _origin_from_url(value: str) -> Optional[str]:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _transport_security_settings() -> Any:
    from mcp.server.transport_security import TransportSecuritySettings

    allowed_hosts = list(MCP_ALLOWED_HOSTS)
    for candidate in (API_BASE_URL, MCP_RESOURCE_SERVER_URL):
        host = _host_from_url(candidate)
        if host and host not in allowed_hosts:
            allowed_hosts.append(host)
    for host in ("127.0.0.1:*", "localhost:*", "[::1]:*"):
        if host not in allowed_hosts:
            allowed_hosts.append(host)

    allowed_origins = list(MCP_ALLOWED_ORIGINS)
    for candidate in (API_BASE_URL, MCP_RESOURCE_SERVER_URL):
        origin = _origin_from_url(candidate)
        if origin and origin not in allowed_origins:
            allowed_origins.append(origin)
    for origin in ("http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"):
        if origin not in allowed_origins:
            allowed_origins.append(origin)

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def create_mcp_component() -> Optional[McpComponent]:
    if not MCP_ENABLED:
        logger.info("MCP desabilitado por configuração.")
        return None

    try:
        from mcp.server.auth.settings import AuthSettings
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        message = "MCP habilitado, mas o pacote 'mcp' não está instalado."
        if MCP_REQUIRED:
            raise RuntimeError(message) from exc
        logger.warning("%s Endpoint MCP não será montado.", message)
        return None

    if not ACCESS_CONTROL_ENABLED:
        message = "MCP exige EXPAI_ACCESS_CONTROL_ENABLED=true para expor conteúdo a agentes."
        if MCP_REQUIRED:
            raise RuntimeError(message)
        logger.warning("%s Endpoint MCP não será montado.", message)
        return None

    mcp = FastMCP(
        name="Expertise.AI Knowledge Base",
        instructions=(
            "Use este servidor para consultar documentos publicados e estruturados da base Expertise.AI. "
            "Todas as chamadas exigem Bearer token e respeitam empresa, perfis e restrições por área."
        ),
        token_verifier=ExpertiseTokenVerifier(),
        auth=AuthSettings(
            issuer_url=MCP_ISSUER_URL,
            resource_server_url=MCP_RESOURCE_SERVER_URL,
            required_scopes=list(MCP_REQUIRED_SCOPES or ["kb:read"]),
            validate_token_resource=False,
        ),
        streamable_http_path="/",
        stateless_http=True,
        max_request_body_size=max(1024, MCP_MAX_REQUEST_BODY_SIZE),
        max_sessions=max(1, MCP_MAX_SESSIONS),
        session_idle_timeout=max(60, MCP_SESSION_IDLE_TIMEOUT_SECONDS),
        transport_security=_transport_security_settings(),
    )

    @mcp.tool(structured_output=True)
    def describe_knowledge_base(company_id: int) -> dict[str, Any]:
        """Describe the authenticated user's visible knowledge-base scope for one company."""
        user, allowed_areas = _require_company_context(company_id)
        areas = db.list_taxonomies(company_id, "area")
        categories = db.list_taxonomies(company_id, "categoria")
        if allowed_areas is not None:
            areas = [area for area in areas if services._sanitize(str(area)) in allowed_areas]
            categories = [
                item
                for item in categories
                if services._sanitize(str(item.get("area") or services.DEFAULT_AREA)) in allowed_areas
            ]
        return {
            "empresa_id": company_id,
            "user": {
                "user_id": user.user_id,
                "email": user.email,
                "role": user.role,
                "roles": user.roles,
            },
            "limits": {
                "max_page_size": MCP_MAX_PAGE_SIZE,
                "max_content_chars": MCP_MAX_CONTENT_CHARS,
            },
            "areas": areas,
            "categorias": categories,
        }

    @mcp.tool(structured_output=True)
    def search_documents(
        company_id: int,
        query: Optional[str] = None,
        area: Optional[str] = None,
        categoria: Optional[str] = None,
        tag: Optional[str] = None,
        data_validade_de: Optional[str] = None,
        data_validade_ate: Optional[str] = None,
        include_expired: bool = False,
        include_content: bool = False,
        limit: int = 20,
        offset: int = 0,
        sort: str = "created_desc",
    ) -> dict[str, Any]:
        """Search published documents visible to the authenticated user."""
        _, allowed_areas = _require_company_context(company_id)
        if area is not None:
            _assert_area_access(company_id, area, allowed_areas)
        validade_de = _parse_iso_date(data_validade_de, "data_validade_de")
        validade_ate = _parse_iso_date(data_validade_ate, "data_validade_ate")
        if not include_expired and not validade_de and not validade_ate:
            validade_de = date.today().isoformat()
        safe_limit = _clamp_limit(limit)
        safe_offset = _safe_offset(offset)
        payload = services.read_published_documents(
            company_id=company_id,
            area=area,
            categoria=categoria,
            tag=tag,
            busca=query,
            data_validade_de=validade_de,
            data_validade_ate=validade_ate,
            limit=safe_limit,
            offset=safe_offset,
            include_content=include_content,
            include_unpublished=False,
            sort_by=sort,
            return_total=True,
            allowed_areas=allowed_areas,
        )
        total = int(payload.get("total", 0) if isinstance(payload, dict) else 0)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        return {
            "empresa_id": company_id,
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
            "has_next": safe_offset + len(items) < total,
            "next_offset": safe_offset + safe_limit if safe_offset + len(items) < total else None,
            "documentos": [_public_document_payload(item, include_content=include_content) for item in items],
        }

    @mcp.tool(structured_output=True)
    def get_document_metadata(
        company_id: int,
        document_uuid: str,
        include_expired: bool = False,
    ) -> dict[str, Any]:
        """Get public metadata for one published document by stable document_uuid."""
        _, allowed_areas = _require_company_context(company_id)
        meta = services.read_document_metadata_by_uuid(company_id, document_uuid)
        _assert_document_visible_to_user(company_id, meta, allowed_areas, include_expired)
        return {"documento": _public_document_payload(services._meta_to_index_entry(meta))}

    @mcp.tool(structured_output=True)
    def get_document_content(
        company_id: int,
        document_uuid: str,
        version: Optional[str] = None,
        include_expired: bool = False,
    ) -> dict[str, Any]:
        """Get Markdown content for one published document by stable document_uuid."""
        _, allowed_areas = _require_company_context(company_id)
        meta = services.read_document_metadata_by_uuid(company_id, document_uuid)
        _assert_document_visible_to_user(company_id, meta, allowed_areas, include_expired)
        payload = services.read_published_document_content_by_uuid(company_id, document_uuid, version=version)
        content = str(payload.get("content") or "")
        logger.info(
            "MCP content read company_id=%s document_uuid=%s version=%s chars=%s truncated=%s",
            company_id,
            document_uuid,
            payload.get("versao"),
            len(content),
            len(content) > MCP_MAX_CONTENT_CHARS,
        )
        payload["content"] = content[:MCP_MAX_CONTENT_CHARS]
        payload["content_truncated"] = len(content) > MCP_MAX_CONTENT_CHARS
        return {"documento": payload}

    @mcp.tool(structured_output=True)
    def list_taxonomies(company_id: int) -> dict[str, Any]:
        """List areas and categories visible to the authenticated user."""
        _, allowed_areas = _require_company_context(company_id)
        areas = db.list_taxonomies(company_id, "area")
        categories = db.list_taxonomies(company_id, "categoria")
        if allowed_areas is not None:
            areas = [area for area in areas if services._sanitize(str(area)) in allowed_areas]
            categories = [
                item
                for item in categories
                if services._sanitize(str(item.get("area") or services.DEFAULT_AREA)) in allowed_areas
            ]
        return {"empresa_id": company_id, "areas": areas, "categorias": categories}

    mcp_app = mcp.streamable_http_app()
    logger.info("MCP montado em %s com escopos %s.", MCP_PATH, MCP_REQUIRED_SCOPES)
    return McpComponent(server=mcp, app=mcp_app, mount_path=MCP_PATH)
