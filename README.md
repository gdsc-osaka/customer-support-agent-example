# Dynamic Travel Planning Agent

ADK 2.0 Graph Workflow と A2A specialist agents を使った「Dynamic Research + Multi-Agent Evaluation 型 旅行計画AIエージェント」です。ユーザーの旅行希望から国内1泊2日の候補を3から5案作り、候補ごとに検索リサーチし、複数観点の評価と1ラウンドの revision を経て、ユーザーが選んだ案だけを詳細旅程と旅しおり画像にします。

## Architecture

```text
Coordinator Agent (port 8100)
  |- analyst
  |- clarification RequestInput (最大2回)
  |- strategist
  |- research_agent_1..5 + google_search (fan-out / fan-in)
  |- budget_agent
  |- Comfort Agent     (RemoteA2aAgent, port 8101)
  |- Risk Agent        (RemoteA2aAgent, port 8102)
  |- Experience Agent  (RemoteA2aAgent, port 8103)
  |- one-round revision debate
  |- coordinator recommendation
  |- user selection RequestInput
  |- BuildSelectedOptionContext FunctionNode
  |- planner
  `- illustrator (gemini-3-pro-image)
```

`research_agent` の結果は会話コンテキストに依存せず、join 後に `session.state["research_reports"]` へ `option_id` keyed dict として保存します。`planner` には State 全体ではなく `session.state["selected_option_context"]` だけを渡します。

## Setup

Install [uv](https://docs.astral.sh/uv/) first.

```bash
make setup
cp .env.example .env
```

Required environment variables:

```bash
# Google AI Studio
GOOGLE_API_KEY=...

# or Vertex AI / Agent Platform
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=...
GOOGLE_CLOUD_LOCATION=us-central1
```

Optional environment variables:

```bash
COMFORT_A2A_URL=http://localhost:8101
RISK_A2A_URL=http://localhost:8102
EXPERIENCE_A2A_URL=http://localhost:8103
```

## Run

Start the remote evaluation specialists, coordinator, and ADK Web:

```bash
make run
```

Or run them separately:

```bash
make run-specialists
make run-coordinator
make web
```

ADK Web listens on `http://localhost:8000`.

AG-UI clients can connect to the coordinator through a separate streaming endpoint:

```bash
make run-ag-ui
```

The AG-UI server listens on `http://localhost:8200` and accepts `POST /ag-ui`
requests using the Agent User Interaction Protocol event stream format.

Agent cards:

```text
http://localhost:8100/.well-known/agent-card.json
http://localhost:8101/.well-known/agent-card.json
http://localhost:8102/.well-known/agent-card.json
http://localhost:8103/.well-known/agent-card.json
```

## Deploy

Deploy the three A2A evaluation specialists first, then the coordinator with
their Agent Runtime A2A card URLs injected:

```bash
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=us-central1
export GOOGLE_GENAI_USE_VERTEXAI=true
make deploy-all
```

The deployed Reasoning Engine display names are prefixed with `Travel Planning`.
To inspect or remove deployed resources created by this repo:

```bash
./scripts/cleanup_all.sh --dry-run
./scripts/cleanup_all.sh
```

## Sample Input

```text
東京から一泊二日で、静かな田舎に行きたいです。公共交通で行けて、温泉があると嬉しいです。予算は3万円以内です。
```

## State

The workflow stores these intermediate artifacts in `session.state`:

- `raw_user_query`: 元のユーザー入力
- `travel_request`: analyst が作った `TravelRequest`
- `clarification_rounds`: RequestInput の実行回数
- `travel_options`: strategist が作った `TravelOption[]`
- `research_reports`: `option_id` keyed `ResearchReport` dict
- `evaluations`: 初回 `EvaluationReport[]`
- `revised_evaluations`: 1ラウンド debate 後の `EvaluationReport[]`
- `coordinator_recommendation`: 推薦順位、理由、注意点
- `selected_option_id`: ユーザーが選んだ候補ID
- `selected_option_context`: planner に渡す候補限定コンテキスト
- `itinerary_markdown`: planner が作成した詳細な1泊2日旅程
- `illustrator_prompt`: 旅しおり表紙画像を生成するための prompt
- `final_itinerary_presentation`: 旅程 markdown と生成画像をまとめた最終表示用ペイロード

## Repository Layout

```text
agents/coordinator/agent.py           全体の Graph Workflow wiring
agents/coordinator/intake.py          ユーザー希望の構造化と clarification
agents/coordinator/candidates.py      候補生成、検索 research fan-out / fan-in
agents/coordinator/evaluation.py      評価 agent と1ラウンド revision
agents/coordinator/recommendation.py  推薦、ユーザー選択、詳細旅程、画像生成
agents/comfort/                       RemoteA2aAgent 用 comfort specialist
agents/risk/                          RemoteA2aAgent 用 risk specialist
agents/experience/                    RemoteA2aAgent 用 experience specialist
```

## Implemented

- ADK Graph Workflow による旅行計画フロー
- Dynamic Workflow 風の research fan-out / fan-in
- RequestInput による不足情報確認と候補選択
- `session.state` への構造化中間成果物保存
- `google_search` tool を使う候補別 research agents
- RemoteA2aAgent による comfort / risk / experience 評価
- budget / comfort / risk / experience の1ラウンド revision
- planner の markdown 旅程生成と state 保存
- illustrator prompt writer agent
- `gemini-3-pro-image` を使う illustrator agent

## Not Implemented / Stretch Goals

- メール送信
- 長期 Memory 保存
- 宿泊予約、交通予約、施設営業日の確定 API 連携
- 画像生成結果をファイル化して配布用 PDF しおりに組版する処理
- 候補再提案時の高度な条件差分管理

## Development

```bash
make lint
make test
make lock
```

既存の決定論的なサポート業務テスト、`data/`、`src/` は旅行計画エージェント化に伴い削除済みです。
