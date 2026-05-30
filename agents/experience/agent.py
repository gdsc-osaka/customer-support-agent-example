from __future__ import annotations

from google.adk import Agent
from agents._common import to_a2a_app

EXPERIENCE_AGENT_MODEL = "gemini-3.5-flash"

root_agent = Agent(
    name="experience_agent",
    model=EXPERIENCE_AGENT_MODEL,
    description="旅行候補を非日常性、記憶に残る体験、嗜好一致で評価する。",
    instruction=(
        "あなたは experience_agent です。初回評価では EvaluationReport を返してください。"
        "候補ごとの評価は option_evaluations に option_id, score, "
        "comment, concerns を入れてください。"
        "非日常性、記憶に残る体験、ユーザー嗜好との一致を重視します。"
        "Revision を求められた場合は RevisionReport を返し、修正不要なら revision_note に "
        "'no change' と明記してください。revised_report も option_evaluations 形式です。"
    ),
    mode="chat",
)

app = to_a2a_app(root_agent, default_port=8103)