from __future__ import annotations

from google.adk import Agent

from agents._common import build_a2a_app

RISK_AGENT_MODEL = "gemini-3.5-flash"

root_agent = Agent(
    name="risk_agent",
    model=RISK_AGENT_MODEL,
    description="旅行候補を休業、混雑、天候、予約困難、交通遅延、不確実性で評価する。",
    instruction=(
        "あなたは risk_agent です。初回評価では EvaluationReport を返してください。"
        "候補ごとの評価は option_evaluations に option_id, score, "
        "comment, concerns を入れてください。"
        "休業、混雑、天候、予約困難、交通遅延、不確実性を重視します。"
        "Revision を求められた場合は RevisionReport を返し、修正不要なら revision_note に "
        "'no change' と明記してください。revised_report も option_evaluations 形式です。"
    ),
    mode="chat",
)

app = build_a2a_app(root_agent, default_port=8102)
