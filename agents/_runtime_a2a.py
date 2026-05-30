"""Adapters that expose ADK agents through the Vertex AI Reasoning Engine A2A runtime.

The Reasoning Engine A2A template (``vertexai.preview.reasoning_engines.templates.a2a``)
expects an ``A2aAgentExecutor`` factory plus an ``AgentCard``. This module
provides:

* :class:`AdkRuntimeA2aExecutor` — an ``A2aAgentExecutor`` that lazily builds
  an ADK :class:`~google.adk.runners.Runner` backed by in-memory session,
  artifact, memory, and credential services (suitable for the stateless
  Reasoning Engine deployment model).
* :func:`build_runtime_a2a_agent` — wraps an ADK agent into an ``A2aAgent`` so
  it can be deployed via ``scripts/deploy_all.sh``.
"""

from __future__ import annotations

import os

import vertexai
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, TransportProtocol
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.agents.base_agent import BaseAgent
from google.adk.artifacts import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import (
    InMemoryCredentialService,
)
from google.adk.memory import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from vertexai.preview.reasoning_engines.templates.a2a import A2aAgent


class AdkRuntimeA2aExecutor(A2aAgentExecutor):
    """A2A executor that runs an ADK agent inside Vertex AI Reasoning Engine.

    The parent class invokes the supplied ``runner`` factory per request, which
    keeps the in-memory services (session/artifact/memory/credential) scoped to
    a single invocation — matching the stateless deployment model of Reasoning
    Engine.
    """

    def __init__(self, adk_agent: BaseAgent) -> None:
        def create_runner() -> Runner:
            return Runner(
                app_name=adk_agent.name or "adk_a2a_agent",
                agent=adk_agent,
                artifact_service=InMemoryArtifactService(),
                session_service=InMemorySessionService(),
                memory_service=InMemoryMemoryService(),
                credential_service=InMemoryCredentialService(),
            )

        super().__init__(runner=create_runner, use_legacy=False)


def build_runtime_a2a_agent(adk_agent: BaseAgent, *, description: str) -> A2aAgent:
    """Wrap an ADK agent in a Reasoning Engine ``A2aAgent`` for deployment.

    Initializes the Vertex AI SDK when ``GOOGLE_CLOUD_PROJECT`` and a location
    env var are present, then builds an ``AgentCard`` (the ``url`` field is a
    placeholder — Reasoning Engine rewrites it at deploy time) wired to
    :class:`AdkRuntimeA2aExecutor`.
    """
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("GOOGLE_CLOUD_REGION")
    if project and location:
        vertexai.init(project=project, location=location)

    skill = AgentSkill(
        id=f"{adk_agent.name}_skill",
        name=adk_agent.name,
        description=description,
        tags=["a2a", "travel-planning"],
    )
    agent_card = AgentCard(
        name=adk_agent.name,
        description=description,
        url="http://localhost:9999/",
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
        preferred_transport=TransportProtocol.http_json,
        supports_authenticated_extended_card=True,
    )
    return A2aAgent(
        agent_card=agent_card,
        agent_executor_builder=AdkRuntimeA2aExecutor,
        agent_executor_kwargs={"adk_agent": adk_agent},
    )
