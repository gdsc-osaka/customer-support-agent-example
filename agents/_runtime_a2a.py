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
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("GOOGLE_CLOUD_REGION")
    if project and location:
        vertexai.init(project=project, location=location)

    skill = AgentSkill(
        id=f"{adk_agent.name}_skill",
        name=adk_agent.name,
        description=description,
        tags=["a2a", "acmedesk"],
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
