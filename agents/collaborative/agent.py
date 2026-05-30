from __future__ import annotations

from typing import Any

from google.adk import Agent, Workflow
from google.adk.agents.context import Context
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.workflow import node

from agents._common import build_a2a_app, remote_agent_card_url, runtime_a2a_httpx_client

COLLABORATIVE_AGENT_MODEL = "gemini-3.5-flash"

_remote_a2a_httpx_client = runtime_a2a_httpx_client()

summary_agent = RemoteA2aAgent(
    name="summary_agent",
    agent_card=remote_agent_card_url(
        "SUMMARY_A2A_URL",
        "http://localhost:8111",
    ),
    httpx_client=_remote_a2a_httpx_client,
    description="入力された依頼の要点、制約、未確定事項を短く整理する。",
    use_legacy=False,
)

ideas_agent = RemoteA2aAgent(
    name="ideas_agent",
    agent_card=remote_agent_card_url(
        "IDEAS_A2A_URL",
        "http://localhost:8112",
    ),
    httpx_client=_remote_a2a_httpx_client,
    description="入力された依頼に対して、実行可能なアイデアや次の一手を提案する。",
    use_legacy=False,
)

collaborative_agent = Agent(
    name="collaborative_workflow_agent",
    model=COLLABORATIVE_AGENT_MODEL,
    description=(
        "2つの single_turn サブエージェントを並列に呼び出す "
        "collaborative workflow サンプル。"
    ),
    instruction=(
        "あなたは collaborative workflow の動作確認用 coordinator です。"
        "ユーザーの依頼を受けたら、自分だけで回答を作らず、必ず summary_agent と "
        "ideas_agent の両方へ同じ依頼文を渡してください。"
        "summary_agent と ideas_agent のツール呼び出しは、可能な限り並列に実行します。"
        "summary_agent には依頼の要点、制約、未確定事項の整理を任せます。"
        "ideas_agent には実行可能なアイデア、確認観点、次の一手の提案を任せます。"
        "2つの結果が返ったら、重複を省き、次の形式で日本語の短い回答に統合してください。"
        "1. 要点: 依頼内容を1から3行でまとめる。"
        "2. 提案: 実行可能な案を箇条書きで示す。"
        "3. 注意点: 未確定事項や仮定があれば短く示す。"
        "ユーザーへの追加質問はせず、不足情報がある場合は合理的な仮定を置いてください。"
    ),
    tools=[AgentTool(summary_agent), AgentTool(ideas_agent)],
    mode="chat",
)

response_review_agent = Agent(
    name="response_review_agent",
    model=COLLABORATIVE_AGENT_MODEL,
    description="collaborative workflow agent の出力を読みやすい最終回答に整える。",
    instruction=(
        "あなたは response_review_agent です。"
        "前段の collaborative_workflow_agent が作成した回答を読み、内容を変えずに整理してください。"
        "冗長な重複を削り、要点、提案、注意点が読みやすくなるように整えます。"
        "新しい事実やツール結果を追加せず、入力に含まれる内容だけを使ってください。"
        "最終回答は日本語で簡潔に返してください。"
    ),
    mode="single_turn",
)


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if hasattr(value, "model_dump_json"):
        return value.model_dump_json(indent=2)
    return repr(value)


@node(name="run_collaborative_agent", rerun_on_resume=True)
async def run_collaborative_agent(ctx: Context, node_input: Any) -> str:
    output = await ctx.run_node(collaborative_agent, node_input)
    if output:
        return text(output)

    for event in reversed(ctx.session.events):
        if event.author != collaborative_agent.name:
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


root_agent = Workflow(
    name="collaborative_workflow",
    description=(
        "collaborative_workflow_agent と response_review_agent を "
        "Workflow ノードとして実行するサンプル。"
    ),
    edges=[
        (
            "START",
            run_collaborative_agent,
            response_review_agent,
        ),
    ],
)

app = build_a2a_app(root_agent, default_port=8110)
