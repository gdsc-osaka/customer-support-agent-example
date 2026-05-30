from __future__ import annotations

from google.adk import Workflow
from google.adk.workflow import DEFAULT_ROUTE

from agents._common import build_a2a_app
from agents.coordinator.candidates import (
    store_travel_options,
    strategist_agent,
    travel_research_workflow,
)
from agents.coordinator.evaluation import build_evaluation_input, evaluation_agent
from agents.coordinator.intake import (
    ROUTE_CLARIFY,
    analyst_agent,
    build_reanalysis_input,
    capture_user_query,
    request_clarification,
    route_after_analysis,
)
from agents.coordinator.recommendation import (
    ROUTE_REPLAN,
    ROUTE_SELECTED,
    build_replan_input,
    planning_workflow,
    request_user_selection,
    route_user_selection,
    store_recommendation,
)

candidate_workflow = Workflow(
    name="travel_candidate_workflow",
    description="Creates candidates, researches them, evaluates them, and requests user selection.",
    edges=[
        (
            "START",
            strategist_agent,
            store_travel_options,
            travel_research_workflow,
            build_evaluation_input,
            evaluation_agent,
            store_recommendation,
            request_user_selection,
            route_user_selection,
        ),
        (
            route_user_selection,
            {
                ROUTE_SELECTED: planning_workflow,
                ROUTE_REPLAN: build_replan_input,
            },
        ),
        (build_replan_input, analyst_agent),
    ],
)

root_agent = Workflow(
    name="dynamic_travel_planning_agent",
    description=(
        "Dynamic Research + Multi-Agent Evaluation 型の国内1泊2日旅行計画AIエージェント。"
    ),
    edges=[
        ("START", capture_user_query, analyst_agent),
        (
            route_after_analysis,
            {
                ROUTE_CLARIFY: request_clarification,
                DEFAULT_ROUTE: candidate_workflow,
            },
        ),
        (request_clarification, build_reanalysis_input, analyst_agent),
        (analyst_agent, route_after_analysis),
    ],
)

app = build_a2a_app(root_agent, default_port=8100)
