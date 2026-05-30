from __future__ import annotations

import json
from typing import Any

from google.adk import Agent
from google.adk.agents.context import Context
from google.adk.events import RequestInput
from google.adk.events.event import Event

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
    RankedOption,
    SelectedOptionContext,
)
from agents.coordinator.recommendation_prompts import IMAGE_PROMPT_FORMAT
from agents.coordinator.utils import text

__all__ = [
    "CoordinatorRecommendation",
    "RankedOption",
    "SelectedOptionContext",
]

ROUTE_REPLAN = "replan"
ROUTE_SELECTED = "selected"
MAX_USER_VISIBLE_OPTIONS = 3

STATE_COORDINATOR_RECOMMENDATION = "coordinator_recommendation"
STATE_SELECTED_OPTION_ID = "selected_option_id"
STATE_SELECTED_OPTION_CONTEXT = "selected_option_context"
STATE_ITINERARY_MARKDOWN = "itinerary_markdown"
STATE_ILLUSTRATOR_PROMPT = "illustrator_prompt"
STATE_FINAL_ITINERARY_PRESENTATION = "final_itinerary_presentation"

PLANNER_AGENT_MODEL = "gemini-3.5-flash"
ILLUSTRATOR_PROMPT_AGENT_MODEL = "gemini-3.1-pro-preview"
ILLUSTRATOR_AGENT_MODEL = "gemini-3-pro-image"

planner_agent = Agent(
    name="planner",
    model=PLANNER_AGENT_MODEL,
    description="選ばれた候補だけを使って詳細な旅程をmarkdownで作る。",
    instruction=(
        "入力: 選択された旅行候補\n"
        "出力: 詳細旅程のmarkdown"
        "読みやすさを優先し、見出し、箇条書き、時間帯ごとの流れを自然に使います。"
        "日程には移動、食事、宿泊、雨天代替、注意点を含めてください。"
        "入力にない情報は断定せず「要確認」と書いてください。"
    ),
    mode="single_turn",
)

illustrator_prompt_agent = Agent(
    name="illustrator_prompt_writer",
    model=ILLUSTRATOR_PROMPT_AGENT_MODEL,
    description="plannerの旅程markdownから表紙画像生成用promptを作る。",
    instruction=(
        "入力: 旅行旅程\n"
        "出力: i枚の旅行しおり画像を生成するための英語のprompt\n"
        "- 画像生成プロンプト以外を出力するのは禁止です\n"
        "- 旅程ごとに最適なしおり画像は異なります\n"
        "- 入力された旅程情報を全て配置してください. 省略は禁止です.\n"
        "- この画像を見るだけで旅程と全く同じ旅行ができることが目標です\n"
        "- 画像のスタイルはこれをそのまま貼ってください: 'flat 2D cel-shaded anime illustration, hand-drawn line art, crisp black outlines, minimal gradients, no realistic skin texture, no 3D rendering, no photorealistic lighting, no glossy highlights, no cinematic color grading'"
        f"- プロンプトは以下のフォーマット例に従ってください\n{IMAGE_PROMPT_FORMAT}"
        
    ),
    mode="single_turn",
)

illustrator_agent = Agent(
    name="illustrator",
    model=ILLUSTRATOR_AGENT_MODEL,
    description="旅しおりの表紙画像を生成する。",
    instruction=(
        "旅しおり画像を生成してください"
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


def build_planner_input(ctx: Context, node_input: Any) -> str:
    context = build_selected_option_context(ctx, node_input)
    evaluation_summaries = []
    for evaluation in context.evaluations:
        selected_evaluation = next(
            (
                item
                for item in evaluation.option_evaluations
                if item.option_id == context.selected_option.option_id
            ),
            None,
        )
        evaluation_summaries.append(
            f"- {evaluation.agent_name}: "
            f"score={selected_evaluation.score if selected_evaluation else '要確認'}; "
            f"{selected_evaluation.comment if selected_evaluation else 'comment 要確認'}"
        )

    recommendation = context.recommendation
    recommendation_lines = []
    if recommendation is not None:
        cautions = ", ".join(recommendation.cautions) if recommendation.cautions else "なし"
        recommendation_lines = [
            f"- 推薦順位: {recommendation.rank}",
            f"- 推薦理由: {recommendation.reason}",
            f"- 注意点: {cautions}",
        ]

    return "\n\n".join(
        [
            "# Travel request",
            f"- 元の希望: {context.travel_request.raw_user_query}",
            f"- 出発地: {context.travel_request.origin or '要確認'}",
            f"- 期間: {context.travel_request.duration or '要確認'}",
            f"- 同行者: {context.travel_request.companions or '要確認'}",
            f"- 予算: {context.travel_request.budget or '要確認'}",
            f"- 交通手段: {context.travel_request.transport or '要確認'}",
            f"- 嗜好: {', '.join(context.travel_request.preferences) or '要確認'}",
            f"- 制約: {', '.join(context.travel_request.constraints) or 'なし'}",
            f"- 不足情報: {', '.join(context.travel_request.unknowns) or 'なし'}",
            "# Selected option",
            f"- ID: {context.selected_option.option_id}",
            f"- タイトル: {context.selected_option.title}",
            f"- 目的地: {context.selected_option.destination}",
            f"- コンセプト: {context.selected_option.concept}",
            f"- 適合仮説: {context.selected_option.fit_hypothesis}",
            "# Recommendation notes",
            "\n".join(recommendation_lines) if recommendation_lines else "- 推薦情報: 要確認",
            f"- 調整メモ: {context.coordinator_notes}",
            "# Research report",
            f"- 目的地概要: {context.research_report.destination_summary}",
            f"- アクセス: {context.research_report.access}",
            f"- 概算費用: {context.research_report.estimated_cost}",
            f"- 宿泊エリア: {context.research_report.lodging_area}",
            f"- おすすめスポット: {', '.join(context.research_report.recommended_spots)}",
            f"- 食事候補: {', '.join(context.research_report.food_options)}",
            f"- リスク: {', '.join(context.research_report.risks)}",
            f"- 天候・季節メモ: {', '.join(context.research_report.weather_or_season_notes)}",
            f"- 情報源メモ: {', '.join(context.research_report.source_notes)}",
            f"- 適合理由: {context.research_report.suitability_reason}",
            "# Specialist evaluations",
            "\n".join(evaluation_summaries) if evaluation_summaries else "- なし",
        ]
    )


def store_itinerary_markdown(ctx: Context, node_input: Any) -> str:
    markdown = text(node_input)
    ctx.state[STATE_ITINERARY_MARKDOWN] = markdown
    return markdown


def store_illustrator_prompt(ctx: Context, node_input: Any) -> str:
    prompt = text(node_input)
    ctx.state[STATE_ILLUSTRATOR_PROMPT] = prompt
    return prompt
