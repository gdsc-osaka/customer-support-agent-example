from __future__ import annotations

from google.adk import Agent

from agents._common import build_a2a_app

SUMMARY_AGENT_MODEL = "gemini-3.5-flash"

root_agent = Agent(
    name="summary_agent",
    model=SUMMARY_AGENT_MODEL,
    description="入力された依頼の要点、制約、未確定事項を短く整理する。",
    instruction=(
        "あなたは summary_agent です。"
        "入力された依頼を読み、要点、明示された制約、未確定事項を簡潔に整理してください。"
        "ツールは使わず、ユーザーへの追加質問もしないでください。"
    ),
    mode="chat",
)

app = build_a2a_app(root_agent, default_port=8111)
