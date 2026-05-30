from __future__ import annotations

from typing import Any

from google.adk import Agent
from google.adk.agents.context import Context
from google.adk.events import RequestInput
from google.adk.events.event import Event
from google.adk.workflow import DEFAULT_ROUTE

from agents.coordinator.clarify_models import TravelRequest
from agents.coordinator.utils import text

__all__ = [
    "TravelRequest",
]

ROUTE_CLARIFY = "clarify"
MAX_CLARIFICATION_ROUNDS = 2
CLARIFY_AGENT_MODEL = "gemini-3.5-flash"

STATE_RAW_USER_QUERY = "raw_user_query"
STATE_TRAVEL_REQUEST = "travel_request"
STATE_CLARIFICATION_ROUNDS = "clarification_rounds"


# --- Agents -----------------------------------------------------------------

clarify_agent = Agent(
    name="clarify",
    model=CLARIFY_AGENT_MODEL,
    description="旅行希望を構造化し、不足情報を抽出する。",
    output_schema=TravelRequest,
    instruction=(
        "ユーザーの旅行希望を TravelRequest に構造化してください。"
        "期間、出発地、予算、交通手段、同行者、旅行嗜好、制約を抽出します。"
        "origin, duration, budget, transport など旅程品質に重大な影響がある情報が"
        "不明な場合のみ unknowns に入れてください。"
        "推測で補える軽微な項目は unknowns に入れすぎないでください。"
    ),
    mode="single_turn",
)


# --- Workflow nodes ---------------------------------------------------------

def capture_user_query(ctx: Context, node_input: Any) -> str:
    raw_query = text(node_input) or _latest_user_text(ctx)
    ctx.state[STATE_RAW_USER_QUERY] = raw_query
    ctx.state.setdefault(STATE_CLARIFICATION_ROUNDS, 0)
    return raw_query


def route_after_clarification(ctx: Context, node_input: TravelRequest):
    ctx.state[STATE_TRAVEL_REQUEST] = node_input.model_dump()
    rounds = int(ctx.state.get(STATE_CLARIFICATION_ROUNDS, 0))
    material_unknowns = [
        unknown
        for unknown in node_input.unknowns
        if any(key in unknown.lower() for key in ["origin", "duration", "budget", "transport"])
        or any(word in unknown for word in ["出発", "期間", "予算", "交通"])
    ]

    if material_unknowns and rounds < MAX_CLARIFICATION_ROUNDS:
        ctx.state[STATE_CLARIFICATION_ROUNDS] = rounds + 1
        yield Event(route=ROUTE_CLARIFY, output=node_input)
        return

    yield Event(route=DEFAULT_ROUTE, output=node_input)


def request_clarification(ctx: Context, node_input: TravelRequest):
    unknowns = node_input.unknowns[:4]
    unknown_text = "\n".join(f"- {unknown}" for unknown in unknowns) or "- 旅行条件の不足"
    message = (
        "旅行候補の精度に影響する情報が不足しています。次の項目に答えてください。\n"
        f"{unknown_text}"
    )
    yield RequestInput(
        message=message,
        payload={"travel_request": node_input.model_dump(), "unknowns": unknowns},
        response_schema=str,
    )


def build_reclarify_input(ctx: Context, node_input: Any) -> str:
    return "\n\n".join(
        [
            "元の旅行希望:",
            text(ctx.state.get(STATE_RAW_USER_QUERY)),
            "前回の構造化結果:",
            text(ctx.state.get(STATE_TRAVEL_REQUEST)),
            "ユーザーの追加回答:",
            text(node_input),
            "追加回答を反映して TravelRequest を更新してください。",
        ]
    )


# --- Helpers ----------------------------------------------------------------

def _event_text(event: Event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return "".join(part.text for part in event.content.parts if part.text).strip()


def _latest_user_text(ctx: Context) -> str:
    for event in reversed(ctx.session.events):
        if event.author == "user":
            event_text = _event_text(event)
            if event_text:
                return event_text
    return ""
