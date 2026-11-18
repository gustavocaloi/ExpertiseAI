"""Server-owned feature flag and effective provider selection for Monitoria."""
from . import config
from .ai_providers.registry import validate_provider


def require_processing(settings):
    if not settings.get("is_enabled"):
        raise ValueError("Processamento de monitoria pausado nas configurações da empresa")


def upload_provider(settings):
    require_processing(settings)
    if not config.MONITORIA_REAL_AI_ENABLED:
        return "mock"
    name = str(settings.get("provider") or "mock").strip().lower()
    if name == "mock":
        raise ValueError("IA real ativada: configure um provedor real antes de enviar áudios")
    validate_provider(name)
    return name


def runtime_status(settings):
    enabled = config.MONITORIA_REAL_AI_ENABLED
    configured = str(settings.get("provider") or "mock")
    try:
        effective = upload_provider(settings)
        ready, reason = True, ""
    except ValueError as exc:
        effective = configured if enabled else "mock"
        ready, reason = False, str(exc)
    return {
        "real_ai_enabled": enabled,
        "mode": "real" if enabled else "mock",
        "configured_provider": configured,
        "effective_provider": effective,
        "ready": ready,
        "reason": reason,
    }
