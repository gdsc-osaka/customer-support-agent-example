from __future__ import annotations

from google.adk import Agent

from acmedesk_support.communication import generate_customer_response_package
from agents._common import build_a2a_app, model_name


def draft_customer_communication(support_brief: str) -> dict:
    """Return a safe customer-facing response package from the coordinator's support brief."""
    return generate_customer_response_package(support_brief)


root_agent = Agent(
    name="customer_communication_agent",
    model=model_name(),
    description=(
        "Generates safe customer-facing support responses from coordinator-provided briefs."
    ),
    instruction=(
        "You are the Customer Communication Agent for AcmeDesk Support. "
        "Your job is to generate safe, customer-facing support responses from a structured "
        "support brief. You do not investigate tickets, incidents, accounts, or policies "
        "outside of communication policy yourself. Rely on the provided brief and "
        "communication policy context only. "
        "Use draft_customer_communication for every request and return its structured output. "
        "Use only facts explicitly provided as customer-facing or safe to disclose. If a fact "
        "appears internal, speculative, sensitive, or not explicitly approved, do not include "
        "it in the customer response. "
        "When cause is uncertain, say the team is investigating. Do not claim root cause "
        "unless it is explicitly marked as confirmed and customer-facing. "
        "For high-impact or high-severity cases, communicate urgency, next steps, and next "
        "update timing when available. Ask only for information necessary to progress the "
        "investigation. "
        "Always return structured output containing subject, customer_response, "
        "summary_for_agent, disclosure_check, assumptions, requires_human_review, and "
        "human_review_reason. "
        "Default to requiring human review for SEV1, SEV2, authentication issues, "
        "security/privacy issues, service availability issues, billing disputes, "
        "incident-related cases, broad-impact cases, Premier customers, or any uncertainty."
    ),
    tools=[draft_customer_communication],
)

app = build_a2a_app(root_agent, default_port=8106)
