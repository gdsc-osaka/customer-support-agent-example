from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"


def ensure_src_path() -> None:
    src = str(SRC_DIR)
    if src not in sys.path:
        sys.path.insert(0, src)


ensure_src_path()
load_dotenv(REPO_ROOT / ".env")


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
    use_auth = os.getenv("ACMEDESK_A2A_USE_ADC_AUTH", "").lower() in {"1", "true", "yes"}
    if not use_auth:
        return None
    return httpx.AsyncClient(auth=GoogleCloudAuth(), timeout=httpx.Timeout(timeout=60.0))


def build_a2a_app(agent, default_port: int):
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    host = os.getenv("A2A_HOST", "localhost")
    protocol = os.getenv("A2A_PROTOCOL", "http")
    port = int(os.getenv("PORT", str(default_port)))
    return to_a2a(agent, host=host, port=port, protocol=protocol)
