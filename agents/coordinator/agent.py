from __future__ import annotations

from google.adk import Workflow
from google.adk.workflow import DEFAULT_ROUTE

from agents._common import to_a2a_app
from agents.coordinator.candidates import (
    store_travel_options,
    strategist_agent,
    travel_research_workflow,
)
from agents.coordinator.evaluation import build_evaluation_input, evaluation_agent
from agents.coordinator.clarify import (
    ROUTE_CLARIFY,
    clarify_agent,
    build_reclarify_input,
    capture_user_query,
    request_clarification,
    route_after_clarification,
)
from agents.coordinator.recommendation import (
    ROUTE_REPLAN,
    ROUTE_SELECTED,
    build_planner_input,
    build_replan_input,
    illustrator_agent,
    illustrator_prompt_agent,
    planner_agent,
    request_user_selection,
    route_user_selection,
    store_illustrator_prompt,
    store_itinerary_markdown,
    store_recommendation,
)


# --- Workflows ---------------------------------------------------------

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
                ROUTE_SELECTED: build_planner_input,
                ROUTE_REPLAN: build_replan_input,
            },
        ),
        (
            build_planner_input,
            planner_agent,
            store_itinerary_markdown,
            illustrator_prompt_agent,
            store_illustrator_prompt,
            illustrator_agent,
        ),
        (build_replan_input, clarify_agent),
    ],
)

root_agent = Workflow(
    name="dynamic_travel_planning_agent",
    description=(
        "Dynamic Research + Multi-Agent Evaluation 型の国内1泊2日旅行計画AIエージェント。"
    ),
    edges=[
        ("START", capture_user_query, clarify_agent),
        (
            route_after_clarification,
            {
                ROUTE_CLARIFY: request_clarification,
                DEFAULT_ROUTE: candidate_workflow,
            },
        ),
        (request_clarification, build_reclarify_input, clarify_agent),
        (clarify_agent, route_after_clarification),
    ],
)

app = to_a2a_app(root_agent, default_port=8100)
