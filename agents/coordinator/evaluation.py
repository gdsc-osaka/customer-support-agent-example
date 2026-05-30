from __future__ import annotations

import json
from typing import Any

from google.adk import Agent, Context
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.workflow import node

from agents._common import remote_agent_card_url, runtime_a2a_httpx_client
from agents.coordinator.candidates import (
    STATE_RESEARCH_REPORTS,
    STATE_TRAVEL_OPTIONS,
)
from agents.coordinator.evaluation_models import (
    EvaluationReport,
    EvaluationReports,
    OptionEvaluation,
)
from agents.coordinator.intake import STATE_TRAVEL_REQUEST
from agents.coordinator.recommendation_models import CoordinatorRecommendation
from agents.coordinator.utils import text

__all__ = [
    "EvaluationReport",
    "EvaluationReports",
    "OptionEvaluation",
]

STATE_REVISED_EVALUATIONS = "revised_evaluations"
EVALUATION_AGENT_MODEL = "gemini-3.1-pro-preview"


_remote_a2a_httpx_client = runtime_a2a_httpx_client()

comfort_agent = RemoteA2aAgent(
    name="comfort_agent",
    agent_card=remote_agent_card_url("COMFORT_A2A_URL", "http://localhost:8101"),
    httpx_client=_remote_a2a_httpx_client,
    description="移動負荷、休憩、宿泊快適性、疲労しにくさで候補を評価する。",
    output_schema=EvaluationReport,
    use_legacy=False,
)

risk_agent = RemoteA2aAgent(
    name="risk_agent",
    agent_card=remote_agent_card_url("RISK_A2A_URL", "http://localhost:8102"),
    httpx_client=_remote_a2a_httpx_client,
    description="休業、混雑、天候、予約困難、交通遅延、不確実性で候補を評価する。",
    output_schema=EvaluationReport,
    use_legacy=False,
)

experience_agent = RemoteA2aAgent(
    name="experience_agent",
    agent_card=remote_agent_card_url("EXPERIENCE_A2A_URL", "http://localhost:8103"),
    httpx_client=_remote_a2a_httpx_client,
    description="非日常性、記憶に残る体験、嗜好一致で候補を評価する。",
    output_schema=EvaluationReport,
    use_legacy=False,
)


def build_evaluation_input(ctx: Context, node_input: Any) -> str:
    research_reports = node_input or ctx.state.get(STATE_RESEARCH_REPORTS)
    return "\n\n".join(
        [
            "TravelRequest、TravelOptions、ResearchReports を根拠に全候補を比較評価してください。",
            "TravelRequest:",
            text(ctx.state.get(STATE_TRAVEL_REQUEST)),
            "TravelOptions:",
            text(ctx.state.get(STATE_TRAVEL_OPTIONS)),
            "ResearchReports keyed by option_id:",
            text(research_reports),
        ]
    )


evaluation_coordinator_agent = Agent(
    name="multi_agent_evaluation_coordinator",
    model=EVALUATION_AGENT_MODEL,
    description="Evaluates travel candidates with specialists and reconciles them into rankings.",
    output_schema=CoordinatorRecommendation,
    instruction=(
        "あなたは旅行候補評価の coordinator です。\n"
        "以下のワークフローに従ってください。\n"
        "1. comfort_agent、risk_agent、experience_agent の全員に分析を依頼する\n"
        "  - comfort_agent には移動負荷、休憩、宿泊快適性、疲労しにくさを分析させてください。\n"
        "  - risk_agent には休業、混雑、天候、予約困難、交通遅延、不確実性を分析させてください。\n"
        "  - experience_agent には非日常性、記憶に残る体験、嗜好一致を分析させてください。\n"
        "2. 各エージェントの結果を元に、費用、費用対効果、隠れコストを分析してください。\n"
        "3. 各 agent の分析が不足、矛盾、曖昧な場合は、1 に戻って再分析を依頼してください。\n"
        "4. 専門家分析とあなたの費用分析を統合し、"
        "評価軸の衝突を調停して推薦順位を決めてください。\n"
        "ユーザーに提示する ranked_options は最大3案です。"
        "comparison_summary には各候補の budget、comfort、risk、experience の"
        "観点ごとの分析サマリーを Markdown で書いてください。"
        "conflict_resolution には評価軸の衝突をどう調停したかを簡潔に書いてください。"
        "user_message にはユーザーに見せる Markdown の推薦文を書いてください。"
        "最終出力は CoordinatorRecommendation の JSON オブジェクトだけにしてください。"
    ),
    tools=[
        AgentTool(comfort_agent),
        AgentTool(risk_agent),
        AgentTool(experience_agent),
    ],
    mode="chat",
)


def parse_coordinator_recommendation(value: Any) -> CoordinatorRecommendation:
    if isinstance(value, CoordinatorRecommendation):
        return value
    if isinstance(value, dict):
        return CoordinatorRecommendation.model_validate(value)

    raw = text(value)
    if raw.startswith("```json"):
        raw = raw.removeprefix("```json").removesuffix("```").strip()
    elif raw.startswith("```"):
        raw = raw.removeprefix("```").removesuffix("```").strip()

    try:
        return CoordinatorRecommendation.model_validate_json(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return CoordinatorRecommendation.model_validate(json.loads(raw[start : end + 1]))


def last_model_text(ctx: Context, author: str) -> str:
    for event in reversed(ctx.session.events):
        if event.author != author:
            continue
        if event.get_function_calls() or event.get_function_responses():
            continue
        if not event.content or not event.content.parts:
            continue
        event_text = "".join(
            part.text or "" for part in event.content.parts if not part.thought
        ).strip()
        if event_text:
            return event_text
    return ""


@node(name="multi_agent_evaluation", rerun_on_resume=True)
async def evaluation_agent(ctx: Context, node_input: Any) -> CoordinatorRecommendation:
    output = await ctx.run_node(evaluation_coordinator_agent, node_input)
    if output:
        return parse_coordinator_recommendation(output)
    return parse_coordinator_recommendation(
        last_model_text(ctx, evaluation_coordinator_agent.name)
    )
