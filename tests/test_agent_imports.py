from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_adk_agent_entrypoints_import_when_dependencies_exist() -> None:
    pytest.importorskip("google.adk")

    from agents.account_context.agent import root_agent as account_agent
    from agents.coordinator.agent import root_agent as coordinator_agent
    from agents.customer_communication.agent import root_agent as communication_agent
    from agents.diagnostics.agent import root_agent as diagnostics_agent
    from agents.escalation_policy.agent import root_agent as policy_agent
    from agents.incident_status.agent import root_agent as incident_agent
    from agents.knowledge_base.agent import root_agent as kb_agent
    from agents.ticket_history.agent import root_agent as ticket_agent

    assert ticket_agent.name == "ticket_history_agent"
    assert kb_agent.name == "knowledge_base_agent"
    assert account_agent.name == "account_context_agent"
    assert diagnostics_agent.name == "diagnostics_agent"
    assert incident_agent.name == "incident_status_agent"
    assert policy_agent.name == "escalation_policy_agent"
    assert communication_agent.name == "customer_communication_agent"
    assert coordinator_agent.name == "support_coordinator_agent"
    assert coordinator_agent.graph is not None

    graph_node_names = {node.name for node in coordinator_agent.graph.nodes}
    assert {
        "__START__",
        "triage_planning_agent",
        "route_investigation_plan",
        "request_retry_clarification",
        "build_retry_planning_input",
        "support_case_resolution_workflow",
    } <= graph_node_names

    graph_edges = {
        (edge.from_node.name, edge.to_node.name, edge.route)
        for edge in coordinator_agent.graph.edges
    }
    assert {
        ("__START__", "triage_planning_agent", None),
        ("triage_planning_agent", "route_investigation_plan", None),
        ("route_investigation_plan", "request_retry_clarification", "retry"),
        ("request_retry_clarification", "build_retry_planning_input", None),
        ("build_retry_planning_input", "triage_planning_agent", None),
        ("route_investigation_plan", "support_case_resolution_workflow", "__DEFAULT__"),
    } <= graph_edges

    resolution_workflow = next(
        node
        for node in coordinator_agent.graph.nodes
        if node.name == "support_case_resolution_workflow"
    )
    resolution_node_names = {node.name for node in resolution_workflow.graph.nodes}
    assert {
        "__START__",
        "account_context_agent",
        "ticket_history_agent",
        "incident_status_agent",
        "knowledge_base_agent",
        "diagnostics_agent",
        "parallel_investigation_join",
        "build_synthesis_input",
        "synthesis_hypothesis_agent",
        "store_synthesis_brief",
        "build_escalation_policy_input",
        "escalation_policy_agent",
        "build_customer_communication_input",
        "customer_communication_agent",
        "build_final_package_input",
        "support_case_resolution_package_agent",
    } <= resolution_node_names

    resolution_edges = {
        (edge.from_node.name, edge.to_node.name, edge.route)
        for edge in resolution_workflow.graph.edges
    }
    assert {
        ("__START__", "account_context_agent", None),
        ("__START__", "ticket_history_agent", None),
        ("__START__", "incident_status_agent", None),
        ("__START__", "knowledge_base_agent", None),
        ("__START__", "diagnostics_agent", None),
        ("account_context_agent", "parallel_investigation_join", None),
        ("ticket_history_agent", "parallel_investigation_join", None),
        ("incident_status_agent", "parallel_investigation_join", None),
        ("knowledge_base_agent", "parallel_investigation_join", None),
        ("diagnostics_agent", "parallel_investigation_join", None),
        ("parallel_investigation_join", "build_synthesis_input", None),
        ("synthesis_hypothesis_agent", "store_synthesis_brief", None),
        ("escalation_policy_agent", "build_customer_communication_input", None),
        ("customer_communication_agent", "build_final_package_input", None),
    } <= resolution_edges


def test_runtime_a2a_wrapper_registers_a2a_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("vertexai")

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    from agents._runtime_a2a import build_runtime_a2a_agent
    from agents.ticket_history.agent import root_agent as ticket_agent

    runtime_agent = build_runtime_a2a_agent(ticket_agent, description="Ticket history A2A")

    assert runtime_agent.agent_framework == "a2a"
    assert "handle_authenticated_agent_card" in runtime_agent.register_operations()[
        "a2a_extension"
    ]
    assert "on_message_send" in runtime_agent.register_operations()["a2a_extension"]


def test_coordinator_retry_route_requests_human_input() -> None:
    pytest.importorskip("google.adk")

    from google.adk.events import RequestInput

    from agents.coordinator.agent import (
        ROUTE_RETRY,
        STATE_CLARIFICATION_QUESTIONS,
        STATE_CLARIFICATION_REQUEST,
        STATE_INVESTIGATION_PLAN,
        InvestigationPlan,
        request_retry_clarification,
        route_investigation_plan,
    )

    ctx = SimpleNamespace(state={})
    plan = InvestigationPlan(
        case_category="authentication",
        urgency="unknown",
        business_impact="unknown",
        ready_for_investigation=False,
        clarification_questions=["Which tenant is affected?", "When did this begin?"],
        initial_hypotheses=[],
        specialist_directives=[],
    )

    route_event = next(route_investigation_plan(ctx, plan))

    assert route_event.actions.route == ROUTE_RETRY
    assert ctx.state[STATE_INVESTIGATION_PLAN] == plan.model_dump()
    assert ctx.state[STATE_CLARIFICATION_QUESTIONS] == [
        "Which tenant is affected?",
        "When did this begin?",
    ]

    request = next(request_retry_clarification(ctx, None))

    assert isinstance(request, RequestInput)
    assert request.message == ctx.state[STATE_CLARIFICATION_REQUEST]
    assert request.payload == {
        "investigation_plan": plan.model_dump(),
        "clarification_questions": [
            "Which tenant is affected?",
            "When did this begin?",
        ],
    }
    assert request.response_schema is str
