from __future__ import annotations

from typing import Any

from google.adk import Agent, Context
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

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
from agents.coordinator.recommendation_models import CoordinatorRecommendation
from agents.coordinator.intake import STATE_TRAVEL_REQUEST
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

evaluation_agent = Agent(
    name="multi_agent_evaluation",
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
        "4. 専門家分析とあなたの費用分析を統合し、評価軸の衝突を調停して推薦順位を決めてください。\n"
        "ユーザーに提示する ranked_options は最大3案です。"
        "comparison_summary には各候補の budget、comfort、risk、experience の"
        "観点ごとの分析サマリーを Markdown で書いてください。"
        "conflict_resolution には評価軸の衝突をどう調停したかを簡潔に書いてください。"
        "user_message にはユーザーに見せる Markdown の推薦文を書いてください。"
    ),
    sub_agents=[comfort_agent, risk_agent, experience_agent],
    mode="single_turn",
)
