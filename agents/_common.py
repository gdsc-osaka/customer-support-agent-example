from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]


def ensure_repo_path() -> None:
    repo = str(REPO_ROOT)
    if repo not in sys.path:
        sys.path.insert(0, repo)


ensure_repo_path()
load_dotenv(REPO_ROOT / ".env")


def env_bool(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes", "on"}


def remote_agent_card_url(env_name: str, default_base_url: str) -> str:
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
    if not env_bool("TRAVEL_AGENT_A2A_USE_ADC_AUTH"):
        return None
    return httpx.AsyncClient(auth=GoogleCloudAuth(), timeout=httpx.Timeout(timeout=60.0))


def build_a2a_app(agent, default_port: int):
    from a2a.types import AgentCapabilities, AgentCard, AgentSkill, TransportProtocol
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    host = os.getenv("A2A_HOST", "localhost")
    protocol = os.getenv("A2A_PROTOCOL", "http")
    port = int(os.getenv("PORT", str(default_port)))
    agent_card = None
    if not hasattr(agent, "sub_agents"):
        rpc_url = f"{protocol}://{host}:{port}/"
        agent_card = AgentCard(
            name=agent.name,
            description=agent.description or "An ADK workflow agent",
            url=rpc_url,
            version="1.0.0",
            default_input_modes=["text/plain"],
            default_output_modes=["text/plain"],
            capabilities=AgentCapabilities(streaming=False),
            skills=[
                AgentSkill(
                    id=f"{agent.name}_skill",
                    name=agent.name,
                    description=agent.description or "Runs the travel planning workflow.",
                    tags=["adk", "workflow", "a2a"],
                )
            ],
            preferred_transport=TransportProtocol.http_json,
            supports_authenticated_extended_card=False,
        )
    return to_a2a(agent, host=host, port=port, protocol=protocol, agent_card=agent_card)
