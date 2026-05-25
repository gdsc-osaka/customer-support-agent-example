from __future__ import annotations

from typing import Any

from google.adk import Agent, Workflow
from google.adk.agents.context import Context
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.events import RequestInput
from google.adk.events.event import Event
from google.adk.workflow import DEFAULT_ROUTE, JoinNode
from pydantic import BaseModel, Field

from agents._common import build_a2a_app, model_name, runtime_a2a_httpx_client, specialist_card_url

ROUTE_RETRY = "retry"

INVESTIGATION_AGENT_NAMES = (
    "account_context_agent",
    "ticket_history_agent",
    "incident_status_agent",
    "knowledge_base_agent",
    "diagnostics_agent",
)

STATE_SYNTHESIS_BRIEF = "temp:synthesis_brief"
STATE_ESCALATION_POLICY = "temp:escalation_policy"
STATE_INVESTIGATION_PLAN = "temp:investigation_plan"
STATE_CLARIFICATION_QUESTIONS = "temp:clarification_questions"
STATE_CLARIFICATION_REQUEST = "temp:clarification_request"


class SpecialistDirective(BaseModel):
    agent_name: str = Field(description="Specialist agent this directive is for.")
    focus: str = Field(description="What this specialist should investigate.")
    priority: str = Field(description="high, medium, or low.")


class InvestigationPlan(BaseModel):
    case_category: str = Field(description="The best current case category.")
    urgency: str = Field(description="Initial urgency or severity estimate.")
    business_impact: str = Field(description="Known or inferred business impact.")
    ready_for_investigation: bool = Field(
        description="Whether enough information exists to run parallel investigation."
    )
    clarification_questions: list[str] = Field(
        description="Questions to ask before investigation if important information is missing."
    )
    initial_hypotheses: list[str] = Field(description="Current working hypotheses.")
    specialist_directives: list[SpecialistDirective] = Field(
        description="Directives for Account Context, Ticket History, Incident Status, "
        "Knowledge Base, and Diagnostics."
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


def _session_user_messages(ctx: Context) -> list[str]:
    messages: list[str] = []
    for event in ctx.session.events:
        if event.author != "user":
            continue
        text = _event_text(event)
        if text:
            messages.append(text)
    return messages


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return repr(value)


def _canonical_agent_name(name: str) -> str:
    for agent_name in INVESTIGATION_AGENT_NAMES:
        if agent_name in name:
            return agent_name
    return name


def _format_joined_findings(node_input: Any) -> str:
    if not isinstance(node_input, dict):
        return _stringify(node_input)

    sections: list[str] = []
    for name, value in node_input.items():
        sections.append(f"{_canonical_agent_name(name)} findings:\n{_stringify(value)}")
    return "\n\n".join(sections)


def _plan_text(plan: Any) -> str:
    if isinstance(plan, InvestigationPlan):
        return plan.model_dump_json(indent=2)
    return _stringify(plan)


def _format_clarification_request(questions: list[str]) -> str:
    formatted_questions = "\n".join(f"- {question}" for question in questions)
    return (
        "I need a little more information before running the support investigation:\n"
        f"{formatted_questions}"
    )


def route_investigation_plan(ctx: Context, node_input: InvestigationPlan):
    ctx.state[STATE_INVESTIGATION_PLAN] = node_input.model_dump()
    if not node_input.ready_for_investigation:
        questions = [
            question.strip()
            for question in node_input.clarification_questions
            if question.strip()
        ]
        ctx.state[STATE_CLARIFICATION_QUESTIONS] = questions
        ctx.state[STATE_CLARIFICATION_REQUEST] = _format_clarification_request(questions)
        yield Event(route=ROUTE_RETRY)
        return

    yield Event(output=node_input, route=DEFAULT_ROUTE)


def request_retry_clarification(ctx: Context, node_input: Any):
    questions = ctx.state.get(STATE_CLARIFICATION_QUESTIONS, [])
    message = ctx.state.get(STATE_CLARIFICATION_REQUEST)
    if not message:
        message = _format_clarification_request([_stringify(node_input)] if node_input else [])

    yield RequestInput(
        message=message,
        payload={
            "investigation_plan": ctx.state.get(STATE_INVESTIGATION_PLAN),
            "clarification_questions": questions,
        },
        response_schema=str,
    )


def build_retry_planning_input(ctx: Context, node_input: Any) -> str:
    clarification_questions = ctx.state.get(STATE_CLARIFICATION_QUESTIONS, [])
    return "\n\n".join(
        [
            "Customer inquiry and session context:",
            "\n\n".join(_session_user_messages(ctx)),
            "Previous triage / investigation plan:",
            _stringify(ctx.state.get(STATE_INVESTIGATION_PLAN, "")),
            "Clarification questions asked:",
            "\n".join(f"- {question}" for question in clarification_questions),
            "Human clarification response:",
            _stringify(node_input),
            "Update the InvestigationPlan using the clarification response.",
        ]
    )


def build_synthesis_input(ctx: Context, node_input: Any) -> str:
    customer_messages = "\n\n".join(_session_user_messages(ctx))
    plan = _latest_text_by_author(ctx, "triage_planning_agent")
    if not plan:
        plan = _stringify(ctx.state.get(STATE_INVESTIGATION_PLAN, ""))
    findings = _format_joined_findings(node_input)
    return "\n\n".join(
        [
            "Customer inquiry and session context:",
            customer_messages,
            "Triage / Investigation Plan:",
            plan,
            "Parallel specialist findings:",
            findings,
        ]
    )


def store_synthesis_brief(ctx: Context, node_input: Any) -> str:
    synthesis = _stringify(node_input)
    ctx.state[STATE_SYNTHESIS_BRIEF] = synthesis
    return synthesis


def build_escalation_policy_input(ctx: Context, node_input: Any) -> str:
    customer_messages = "\n\n".join(_session_user_messages(ctx))
    return "\n\n".join(
        [
            "Customer inquiry and session context:",
            customer_messages,
            "Synthesis / hypothesis update:",
            _stringify(node_input),
            "Apply escalation policy to the synthesized case.",
        ]
    )


def build_customer_communication_input(ctx: Context, node_input: Any) -> str:
    escalation_policy = _stringify(node_input)
    ctx.state[STATE_ESCALATION_POLICY] = escalation_policy
    return "\n\n".join(
        [
            "Synthesis / hypothesis update:",
            str(ctx.state.get(STATE_SYNTHESIS_BRIEF, "")),
            "Escalation policy check:",
            escalation_policy,
            "Draft a customer-safe response package from these approved facts.",
        ]
    )


def build_final_package_input(ctx: Context, node_input: Any) -> str:
    return "\n\n".join(
        [
            "Synthesis / hypothesis update:",
            str(ctx.state.get(STATE_SYNTHESIS_BRIEF, "")),
            "Escalation policy check:",
            str(ctx.state.get(STATE_ESCALATION_POLICY, "")),
            "Customer communication draft:",
            _stringify(node_input),
        ]
    )


_remote_a2a_httpx_client = runtime_a2a_httpx_client()

triage_planning_agent = Agent(
    name="triage_planning_agent",
    model=model_name(),
    description="Classifies the support case and creates an adaptive investigation plan.",
    output_schema=InvestigationPlan,
    instruction=(
        "You are the Triage / Planning Agent for AcmeDesk Support. "
        "Read the customer inquiry and any prior user turns in the session. "
        "Return an InvestigationPlan. Classify the case, identify urgency and business "
        "impact, list initial hypotheses, and produce specialist directives for Account "
        "Context, Ticket History, Incident Status, Knowledge Base, and Diagnostics. "
        "Use your judgment to decide what each specialist should focus on. "
        "If the customer, affected workflow, impact scope, or symptom is too ambiguous to "
        "investigate, set ready_for_investigation=false and include concrete clarification "
        "questions. Do not fabricate missing facts."
    ),
    mode="single_turn",
)

account_context_agent = RemoteA2aAgent(
    name="account_context_agent",
    agent_card=specialist_card_url("ACCOUNT_CONTEXT_A2A_URL", "http://localhost:8103"),
    httpx_client=_remote_a2a_httpx_client,
    description="Looks up customer account, contract, entitlement, SLA, and health context.",
    use_legacy=False,
)
ticket_history_agent = RemoteA2aAgent(
    name="ticket_history_agent",
    agent_card=specialist_card_url("TICKET_HISTORY_A2A_URL", "http://localhost:8101"),
    httpx_client=_remote_a2a_httpx_client,
    description="Finds similar support tickets and historical resolutions.",
    use_legacy=False,
)
incident_status_agent = RemoteA2aAgent(
    name="incident_status_agent",
    agent_card=specialist_card_url("INCIDENT_STATUS_A2A_URL", "http://localhost:8104"),
    httpx_client=_remote_a2a_httpx_client,
    description="Checks active and historical incidents for correlation.",
    use_legacy=False,
)
knowledge_base_agent = RemoteA2aAgent(
    name="knowledge_base_agent",
    agent_card=specialist_card_url("KNOWLEDGE_BASE_A2A_URL", "http://localhost:8102"),
    httpx_client=_remote_a2a_httpx_client,
    description="Finds FAQ, troubleshooting, runbook, product, and policy references.",
    use_legacy=False,
)
diagnostics_agent = RemoteA2aAgent(
    name="diagnostics_agent",
    agent_card=specialist_card_url("DIAGNOSTICS_A2A_URL", "http://localhost:8107"),
    httpx_client=_remote_a2a_httpx_client,
    description="Suggests diagnostic checks, evidence gaps, and next troubleshooting probes.",
    use_legacy=False,
)
escalation_policy_agent = RemoteA2aAgent(
    name="escalation_policy_agent",
    agent_card=specialist_card_url("ESCALATION_POLICY_A2A_URL", "http://localhost:8105"),
    httpx_client=_remote_a2a_httpx_client,
    description="Recommends severity, SLA deadline, escalation target, and safe wording.",
    use_legacy=False,
)
customer_communication_agent = RemoteA2aAgent(
    name="customer_communication_agent",
    agent_card=specialist_card_url("CUSTOMER_COMMUNICATION_A2A_URL", "http://localhost:8106"),
    httpx_client=_remote_a2a_httpx_client,
    description="Generates safe customer-facing response packages from structured briefs.",
    use_legacy=False,
)

parallel_investigation_join = JoinNode(name="parallel_investigation_join")

synthesis_hypothesis_agent = Agent(
    name="synthesis_hypothesis_agent",
    model=model_name(),
    description="Synthesizes parallel findings and updates the working hypotheses.",
    instruction=(
        "You are the Synthesis / Hypothesis Update Agent for AcmeDesk Support. "
        "Use the triage plan and all parallel specialist findings. "
        "Update the hypotheses, explain which evidence supports or weakens each hypothesis, "
        "identify whether clarification is needed, and prepare an internal support brief. "
        "Do not make final severity or customer-response decisions; those are handled later."
    ),
    mode="single_turn",
)

final_package_agent = Agent(
    name="support_case_resolution_package_agent",
    model=model_name(),
    description="Generates the final Support Case Resolution Package.",
    instruction=(
        "You are the Support Case Resolution Package Agent for AcmeDesk. "
        "Combine the synthesis, escalation policy check, and customer communication draft. "
        "Produce the final package with these sections: Case Summary, Triage / Planning, "
        "Parallel Investigation Findings, Hypothesis Update, Escalation Policy Check, "
        "Customer Communication Draft, Clarification Questions, and Internal Next Steps. "
        "Never include raw logs, internal-only timelines, tenant IDs, or sensitive account "
        "value and health signals in customer-facing text."
    ),
    mode="single_turn",
)

support_resolution_workflow = Workflow(
    name="support_case_resolution_workflow",
    description="Runs parallel investigation through final package generation.",
    edges=[
        ("START", account_context_agent, parallel_investigation_join),
        ("START", ticket_history_agent, parallel_investigation_join),
        ("START", incident_status_agent, parallel_investigation_join),
        ("START", knowledge_base_agent, parallel_investigation_join),
        ("START", diagnostics_agent, parallel_investigation_join),
        (
            parallel_investigation_join,
            build_synthesis_input,
            synthesis_hypothesis_agent,
            store_synthesis_brief,
            build_escalation_policy_input,
            escalation_policy_agent,
            build_customer_communication_input,
            customer_communication_agent,
            build_final_package_input,
            final_package_agent,
        ),
    ],
)

root_agent = Workflow(
    name="support_coordinator_agent",
    description="Runs the generic Support Case Resolution Workflow over specialist A2A agents.",
    edges=[
        ("START", triage_planning_agent, route_investigation_plan),
        (
            route_investigation_plan,
            {
                ROUTE_RETRY: request_retry_clarification,
                DEFAULT_ROUTE: support_resolution_workflow,
            },
        ),
        (request_retry_clarification, build_retry_planning_input, triage_planning_agent),
    ],
)

app = build_a2a_app(root_agent, default_port=8100)
