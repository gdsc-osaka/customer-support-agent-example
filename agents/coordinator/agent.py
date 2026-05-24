from __future__ import annotations

from google.adk import Workflow
from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.events.event import Event
from google.adk.workflow import JoinNode

from agents._common import build_a2a_app, model_name, specialist_card_url

RESEARCH_AGENT_NAMES = (
    "ticket_history_agent",
    "knowledge_base_agent",
    "account_context_agent",
    "incident_status_agent",
    "escalation_policy_agent",
)


def _event_text(event: Event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return "".join(part.text for part in event.content.parts if part.text).strip()


def _latest_text_by_author(ctx: Context, author: str) -> str:
    for event in reversed(ctx.session.events):
        if event.invocation_id != ctx.invocation_id or event.author != author:
            continue
        text = _event_text(event)
        if text:
            return text
    return ""


def _current_user_request(ctx: Context) -> str:
    for event in ctx.session.events:
        if event.invocation_id != ctx.invocation_id or event.author != "user":
            continue
        text = _event_text(event)
        if text:
            return text
    return ""


def build_support_brief_input(ctx: Context) -> str:
    sections = [f"Customer request:\n{_current_user_request(ctx)}"]
    for agent_name in RESEARCH_AGENT_NAMES:
        findings = _latest_text_by_author(ctx, agent_name) or "No findings returned."
        sections.append(f"{agent_name} findings:\n{findings}")
    return "\n\n".join(sections)


def build_final_response_input(ctx: Context) -> str:
    support_brief = _latest_text_by_author(ctx, "support_brief_agent")
    communication_package = _latest_text_by_author(ctx, "customer_communication_agent")
    return (
        "Support brief:\n"
        f"{support_brief}\n\n"
        "Customer communication package:\n"
        f"{communication_package}"
    )


ticket_history_agent = RemoteA2aAgent(
    name="ticket_history_agent",
    agent_card=specialist_card_url("TICKET_HISTORY_A2A_URL", "http://localhost:8101"),
    description="Finds similar support tickets and historical resolutions.",
    use_legacy=False,
)
knowledge_base_agent = RemoteA2aAgent(
    name="knowledge_base_agent",
    agent_card=specialist_card_url("KNOWLEDGE_BASE_A2A_URL", "http://localhost:8102"),
    description="Finds FAQ, troubleshooting, runbook, product, and policy references.",
    use_legacy=False,
)
account_context_agent = RemoteA2aAgent(
    name="account_context_agent",
    agent_card=specialist_card_url("ACCOUNT_CONTEXT_A2A_URL", "http://localhost:8103"),
    description="Looks up customer account, contract, entitlement, SLA, and health context.",
    use_legacy=False,
)
incident_status_agent = RemoteA2aAgent(
    name="incident_status_agent",
    agent_card=specialist_card_url("INCIDENT_STATUS_A2A_URL", "http://localhost:8104"),
    description="Checks active and historical incidents for correlation.",
    use_legacy=False,
)
escalation_policy_agent = RemoteA2aAgent(
    name="escalation_policy_agent",
    agent_card=specialist_card_url("ESCALATION_POLICY_A2A_URL", "http://localhost:8105"),
    description="Recommends severity, SLA deadline, escalation target, and safe customer wording.",
    use_legacy=False,
)
customer_communication_agent = RemoteA2aAgent(
    name="customer_communication_agent",
    agent_card=specialist_card_url("CUSTOMER_COMMUNICATION_A2A_URL", "http://localhost:8106"),
    description="Generates safe customer-facing response packages from structured briefs.",
    use_legacy=False,
)

research_join_node = JoinNode(name="support_information_gathering_join")

support_brief_agent = Agent(
    name="support_brief_agent",
    model=model_name(),
    description="Synthesizes specialist findings into a Customer Support Escalation Brief.",
    instruction=(
        "You are the Support Coordinator Agent for AcmeDesk. "
        "Use only the user request and the findings already returned by "
        "ticket_history_agent, knowledge_base_agent, account_context_agent, "
        "incident_status_agent, and escalation_policy_agent. "
        "Do not transfer to another agent and do not ask for additional specialist work. "
        "Synthesize a Customer Support Escalation Brief with these exact sections: "
        "Case Summary, Customer Account Context, Similar Historical Tickets, "
        "Relevant Knowledge Base / Runbook References, Incident Correlation, "
        "Severity Recommendation, Escalation Decision, Draft Customer Response, "
        "and Internal Escalation Note. "
        "Never include internal logs, raw identifiers, or internal incident timelines "
        "in the customer response."
    ),
    mode="single_turn",
)

final_response_agent = Agent(
    name="support_coordinator_final_response_agent",
    model=model_name(),
    description="Combines the support brief and communication package into the final answer.",
    instruction=(
        "You are the Support Coordinator Agent for AcmeDesk. "
        "Use the support brief and the customer_communication_agent output already present "
        "in the conversation. Do not transfer to another agent and do not call tools. "
        "Produce the final Customer Support Escalation Brief with these exact sections: "
        "Case Summary, Customer Account Context, Similar Historical Tickets, "
        "Relevant Knowledge Base / Runbook References, Incident Correlation, "
        "Severity Recommendation, Escalation Decision, Draft Customer Response, "
        "Customer Response Package, and Internal Escalation Note. "
        "Use the customer_communication_agent output for Draft Customer Response and "
        "Customer Response Package. "
        "Never include internal logs, raw identifiers, or internal incident timelines "
        "in the customer response."
    ),
    mode="single_turn",
)

root_agent = Workflow(
    name="support_coordinator_agent",
    description="Coordinates specialist A2A agents and creates Customer Support Escalation Briefs.",
    edges=[
        ("START", ticket_history_agent, research_join_node),
        ("START", knowledge_base_agent, research_join_node),
        ("START", account_context_agent, research_join_node),
        ("START", incident_status_agent, research_join_node),
        ("START", escalation_policy_agent, research_join_node),
        (
            research_join_node,
            build_support_brief_input,
            support_brief_agent,
            customer_communication_agent,
            build_final_response_input,
            final_response_agent,
        ),
    ],
)

app = build_a2a_app(root_agent, default_port=8100)
