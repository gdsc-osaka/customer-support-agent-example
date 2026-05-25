from __future__ import annotations

from google.adk import Agent

from acmedesk_support.diagnostics import recommend_diagnostics
from agents._common import build_a2a_app, model_name


def recommend_case_diagnostics(inquiry: str) -> dict:
    """Return diagnostic checks, evidence gaps, and customer-safe next steps."""
    return recommend_diagnostics(inquiry)


root_agent = Agent(
    name="diagnostics_agent",
    model=model_name(),
    description="Recommends diagnostic checks, evidence gaps, and next troubleshooting probes.",
    instruction=(
        "You are the Diagnostics Agent for AcmeDesk Support. "
        "Use recommend_case_diagnostics for every request. Return diagnostic focus, evidence "
        "to collect, clarification questions, and customer-safe next diagnostic steps. "
        "Do not decide severity or write the final customer response."
    ),
    tools=[recommend_case_diagnostics],
)

app = build_a2a_app(root_agent, default_port=8107)
