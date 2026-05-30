from __future__ import annotations

import json
from typing import Any

from google.adk import Agent, Workflow
from google.adk.agents.context import Context
from google.adk.events import RequestInput
from google.adk.events.event import Event
from google.adk.workflow import FunctionNode

from agents.coordinator.candidates import (
    STATE_RESEARCH_REPORTS,
    STATE_TRAVEL_OPTIONS,
)
from agents.coordinator.candidates_models import ResearchReport, TravelOption
from agents.coordinator.evaluation import (
    STATE_REVISED_EVALUATIONS,
)
from agents.coordinator.evaluation_models import (
    EvaluationReport,
    EvaluationReports,
)
from agents.coordinator.intake import STATE_TRAVEL_REQUEST
from agents.coordinator.intake_models import TravelRequest
from agents.coordinator.recommendation_models import (
    CoordinatorRecommendation,
    DetailedItinerary,
    RankedOption,
    SelectedOptionContext,
)
from agents.coordinator.utils import text

__all__ = [
    "CoordinatorRecommendation",
    "DetailedItinerary",
    "RankedOption",
    "SelectedOptionContext",
]

ROUTE_REPLAN = "replan"
ROUTE_SELECTED = "selected"
MAX_USER_VISIBLE_OPTIONS = 3

STATE_COORDINATOR_RECOMMENDATION = "coordinator_recommendation"
STATE_SELECTED_OPTION_ID = "selected_option_id"
STATE_SELECTED_OPTION_CONTEXT = "selected_option_context"
STATE_DETAILED_ITINERARY = "detailed_itinerary"

PLANNER_AGENT_MODEL = "gemini-3.5-flash"
ILLUSTRATOR_AGENT_MODEL = "gemini-3-pro-image"

planner_agent = Agent(
    name="planner",
    model=PLANNER_AGENT_MODEL,
    description="選ばれた候補だけを使って詳細な1泊2日旅程を作る。",
    output_schema=DetailedItinerary,
    instruction=(
        "selected_option_context のみを根拠に詳細な1泊2日旅程を作ってください。"
        "時間帯、移動、食事、宿泊、雨天代替、注意点を含めます。"
        "research_report にない情報は断定せず「要確認」と書いてください。"
    ),
    mode="single_turn",
)

illustrator_agent = Agent(
    name="illustrator",
    model=ILLUSTRATOR_AGENT_MODEL,
    description="旅しおりの表紙画像を生成する。",
    instruction=(
        "あなたは旅行しおりのイラストレーターです。入力された詳細旅程と候補情報をもとに、"
        "国内1泊2日旅行の旅しおり表紙画像を生成してください。"
    ),
    mode="single_turn",
)

def store_recommendation(
    ctx: Context,
    node_input: CoordinatorRecommendation,
) -> CoordinatorRecommendation:
    ctx.state[STATE_COORDINATOR_RECOMMENDATION] = node_input.model_dump()
    return node_input


def request_user_selection(ctx: Context, node_input: CoordinatorRecommendation):
    ranked = node_input.ranked_options[:MAX_USER_VISIBLE_OPTIONS]
    lines = [f"{item.rank}. {item.title} - {item.reason}" for item in ranked]
    lines.append("4. 条件を変えて再提案")
    message_parts = []
    if node_input.user_message:
        message_parts.append(node_input.user_message)
    message_parts.append("どの案で詳細旅程を作りますか。\n" + "\n".join(lines))
    yield RequestInput(
        message="\n\n".join(message_parts),
        payload={"ranked_options": [item.model_dump() for item in ranked]},
        response_schema=str | int,
    )


def route_user_selection(ctx: Context, node_input: Any):
    response = text(node_input)
    if response.startswith("4") or "再提案" in response or "変えて" in response:
        yield Event(route=ROUTE_REPLAN, output=response)
        return

    recommendation = CoordinatorRecommendation.model_validate(
        ctx.state[STATE_COORDINATOR_RECOMMENDATION]
    )
    selected = recommendation.ranked_options[0]
    for item in recommendation.ranked_options:
        selected_by_rank = response.startswith(str(item.rank))
        selected_by_text = item.option_id in response or item.title in response
        if selected_by_rank or selected_by_text:
            selected = item
            break
    ctx.state[STATE_SELECTED_OPTION_ID] = selected.option_id
    yield Event(route=ROUTE_SELECTED, output=selected.option_id)


def build_replan_input(ctx: Context, node_input: Any) -> str:
    return "\n\n".join(
        [
            "現在のTravelRequest:",
            text(ctx.state.get(STATE_TRAVEL_REQUEST)),
            "現在の推薦:",
            text(ctx.state.get(STATE_COORDINATOR_RECOMMENDATION)),
            "ユーザーの変更希望:",
            text(node_input),
            "条件変更を反映した TravelRequest を作り直してください。",
        ]
    )


def parse_evaluation_reports(value: Any) -> list[EvaluationReport]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("```json"):
            stripped = stripped.removeprefix("```json").removesuffix("```").strip()
        elif stripped.startswith("```"):
            stripped = stripped.removeprefix("```").removesuffix("```").strip()
        if not stripped:
            return []
        value = json.loads(stripped)

    if isinstance(value, dict):
        return EvaluationReports.model_validate(value).reports

    return [EvaluationReport.model_validate(item) for item in value or []]


def build_selected_option_context(ctx: Context, node_input: Any) -> SelectedOptionContext:
    selected_option_id = ctx.state.get(STATE_SELECTED_OPTION_ID) or text(node_input)
    options = [
        TravelOption.model_validate(item)
        for item in ctx.state.get(STATE_TRAVEL_OPTIONS, [])
    ]
    reports = {
        key: ResearchReport.model_validate(value)
        for key, value in ctx.state.get(STATE_RESEARCH_REPORTS, {}).items()
    }
    evaluations = parse_evaluation_reports(ctx.state.get(STATE_REVISED_EVALUATIONS))
    recommendation = CoordinatorRecommendation.model_validate(
        ctx.state[STATE_COORDINATOR_RECOMMENDATION]
    )
    selected_option = next(option for option in options if option.option_id == selected_option_id)
    selected_recommendation = next(
        (item for item in recommendation.ranked_options if item.option_id == selected_option_id),
        None,
    )
    selected_evaluations = [
        evaluation
        for evaluation in evaluations
        if evaluation.score_for(selected_option_id) is not None
    ]
    context = SelectedOptionContext(
        travel_request=TravelRequest.model_validate(ctx.state[STATE_TRAVEL_REQUEST]),
        selected_option=selected_option,
        research_report=reports[selected_option_id],
        evaluations=selected_evaluations,
        recommendation=selected_recommendation,
        coordinator_notes=recommendation.conflict_resolution,
    )
    ctx.state[STATE_SELECTED_OPTION_CONTEXT] = context.model_dump()
    return context


build_selected_option_context_node = FunctionNode(
    name="build_selected_option_context",
    func=build_selected_option_context,
    parameter_binding="state",
)


def build_planner_input(ctx: Context, node_input: SelectedOptionContext) -> str:
    return "\n\n".join(
        [
            "selected_option_context のみを根拠に、詳細な1泊2日旅程を作ってください。",
            "selected_option_context:",
            node_input.model_dump_json(indent=2),
            "research_report にない情報は断定せず、「要確認」と書いてください。",
        ]
    )


def store_detailed_itinerary(ctx: Context, node_input: DetailedItinerary) -> DetailedItinerary:
    ctx.state[STATE_DETAILED_ITINERARY] = node_input.model_dump()
    return node_input


def build_illustrator_input(ctx: Context, node_input: DetailedItinerary) -> str:
    return "\n\n".join(
        [
            "gemini-3-pro-image を使い、旅行しおりの表紙画像を生成してください。",
            "画像には目的地の雰囲気、公共交通、温泉、静かな国内旅行の印象を反映してください。",
            "文字情報を画像内に詰め込みすぎないでください。",
            "DetailedItinerary:",
            node_input.model_dump_json(indent=2),
            "SelectedOptionContext:",
            text(ctx.state.get(STATE_SELECTED_OPTION_CONTEXT)),
        ]
    )


planning_workflow = Workflow(
    name="selected_option_planning_workflow",
    description="Builds selected option context, detailed itinerary, and bookmark image.",
    edges=[
        (
            "START",
            build_selected_option_context_node,
            build_planner_input,
            planner_agent,
            store_detailed_itinerary,
            build_illustrator_input,
            illustrator_agent,
        )
    ],
)
