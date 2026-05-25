from __future__ import annotations

import os
import sys
import time
import warnings
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
_CLOUD_TRACE_ENABLED = False


def ensure_src_path() -> None:
    src = str(SRC_DIR)
    if src not in sys.path:
        sys.path.insert(0, src)


ensure_src_path()
load_dotenv(REPO_ROOT / ".env")


def env_bool(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes", "on"}


def maybe_enable_cloud_trace() -> None:
    global _CLOUD_TRACE_ENABLED
    if _CLOUD_TRACE_ENABLED or not env_bool("ACMEDESK_TRACE_TO_CLOUD"):
        return

    try:
        import google.auth
        from google.adk.telemetry.google_cloud import get_gcp_exporters, get_gcp_resource
        from google.adk.telemetry.setup import maybe_set_otel_providers

        credentials, project_id = google.auth.default()
        hooks = get_gcp_exporters(
            enable_cloud_tracing=True,
            google_auth=(credentials, project_id),
        )
        maybe_set_otel_providers(
            otel_hooks_to_setup=[hooks],
            otel_resource=get_gcp_resource(project_id),
        )
    except Exception as exc:  # pragma: no cover - depends on local/cloud auth state.
        warnings.warn(f"Cloud Trace setup skipped: {exc}", stacklevel=2)
        return

    _CLOUD_TRACE_ENABLED = True


maybe_enable_cloud_trace()


def model_name() -> str:
    return os.getenv("ADK_MODEL", "gemini-2.5-flash")


def specialist_card_url(env_name: str, default_base_url: str) -> str:
    base_url = os.getenv(env_name, default_base_url).rstrip("/")
    if base_url.endswith("/v1/card"):
        return base_url
    if base_url.endswith("/a2a"):
        return f"{base_url}/v1/card"
    if base_url.endswith("/.well-known/agent-card.json"):
        return base_url
    return f"{base_url}/.well-known/agent-card.json"


class GoogleCloudAuth(httpx.Auth):
    def __init__(self) -> None:
        import google.auth
        from google.auth.transport.requests import Request

        self.credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self._request = Request()
        self._expires_at = 0.0

    def auth_flow(self, request: httpx.Request):
        if not self.credentials.valid or time.time() >= self._expires_at - 60:
            self.credentials.refresh(self._request)
            expiry = getattr(self.credentials, "expiry", None)
            self._expires_at = expiry.timestamp() if expiry else time.time() + 3000
        request.headers["Authorization"] = f"Bearer {self.credentials.token}"
        yield request


def runtime_a2a_httpx_client() -> httpx.AsyncClient | None:
    if not env_bool("ACMEDESK_A2A_USE_ADC_AUTH"):
        return None
    return httpx.AsyncClient(auth=GoogleCloudAuth(), timeout=httpx.Timeout(timeout=60.0))


def build_a2a_app(agent, default_port: int):
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    host = os.getenv("A2A_HOST", "localhost")
    protocol = os.getenv("A2A_PROTOCOL", "http")
    port = int(os.getenv("PORT", str(default_port)))
    return to_a2a(agent, host=host, port=port, protocol=protocol)
