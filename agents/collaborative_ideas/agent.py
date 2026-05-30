from __future__ import annotations

from google.adk import Agent

from agents._common import build_a2a_app

IDEAS_AGENT_MODEL = "gemini-3.5-flash"

root_agent = Agent(
    name="ideas_agent",
    model=IDEAS_AGENT_MODEL,
    description="入力された依頼に対して、実行可能なアイデアや次の一手を提案する。",
    instruction=(
        "あなたは ideas_agent です。"
        "入力された依頼に対して、実行可能なアイデア、確認観点、次の一手を提案してください。"
        "ツールは使わず、ユーザーへの追加質問もしないでください。"
    ),
    mode="chat",
)

app = build_a2a_app(root_agent, default_port=8112)
