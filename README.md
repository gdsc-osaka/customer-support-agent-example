# AcmeDesk Customer Support Escalation Agent

This is the completed repository for the hands-on lab "ADK x A2A x Agent Runtime Customer Support Escalation Agent".

The app models a B2B SaaS support workflow for AcmeDesk. A Support Coordinator Agent receives a customer support inquiry, delegates research and response drafting to six specialist agents over A2A, and produces a Customer Support Escalation Brief for support operators.

## Architecture

```text
Support Coordinator Agent
  |- Ticket History Agent       (A2A, port 8101)
  |- Knowledge Base Agent       (A2A, port 8102)
  |- Account Context Agent      (A2A, port 8103)
  |- Incident Status Agent      (A2A, port 8104)
  |- Escalation Policy Agent     (A2A, port 8105)
  `- Customer Communication Agent (A2A, port 8106)
```

Each specialist is an ADK agent exposed as an A2A Starlette app with `to_a2a()`.
The coordinator is a graph-based `Workflow` that consumes the specialists through
direct `RemoteA2aAgent(use_legacy=False)` graph nodes. The first five graph
branches start from `START`, so ticket history, knowledge base, account context,
incident status, and escalation policy run concurrently. A `JoinNode` waits for
those research and policy branches to complete, then a local function node
assembles their event text for the coordinator synthesis agent. The customer
communication A2A agent drafts the customer-facing response package, another
function node assembles the final response input, and a final coordinator
synthesis agent produces the final brief. This keeps orchestration deterministic
and avoids exposing `transfer_to_agent(...)` choices from a coordinator LLM
agent.

For deterministic workshop checks, the shared `acmedesk_support` package also exposes local search and brief-building functions. The CLI sample cases use those functions so they can run without calling an LLM. That deterministic path is not registered as a coordinator ADK tool.

## Setup

Install [uv](https://docs.astral.sh/uv/) if it is not already available.

```bash
make setup
cp .env.example .env
```

Set either `GOOGLE_API_KEY` for Google AI Studio or Agent Platform environment variables in `.env`.

Important dependency note: ADK 2.1 requires `a2a-sdk>=0.3,<0.4` for the current A2A helper modules. This repo pins `a2a-sdk[http-server]==0.3.26` so the Starlette A2A server can serve agent cards and JSON-RPC routes.

Dependencies are managed with `uv` from `pyproject.toml` and `uv.lock`. Do not install them with `pip`; use `make setup` or `uv sync --extra dev`.

## Run locally

Start the six specialist A2A services:

```bash
make run-specialists
```

In another terminal, start the coordinator A2A service:

```bash
make run-coordinator
```

The agent cards are available at:

```text
http://localhost:8101/.well-known/agent-card.json
http://localhost:8102/.well-known/agent-card.json
http://localhost:8103/.well-known/agent-card.json
http://localhost:8104/.well-known/agent-card.json
http://localhost:8105/.well-known/agent-card.json
http://localhost:8106/.well-known/agent-card.json
http://localhost:8100/.well-known/agent-card.json
```

## Run sample cases without an LLM

```bash
make case-a
make case-b
make case-c
```

These commands generate the same Customer Support Escalation Brief shape expected from the coordinator:

- Case A: Contoso SAML SSO outage after IdP certificate rotation
- Case B: Globex billing discrepancy after seat increase
- Case C: Initech CRM webhook delivery delay

## Test and lint

```bash
make lint
make test
```

## Deploy to Agent Platform Agent Runtime

Authenticate with Google Cloud first:

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

Enable the Agent Platform API and Cloud Resource Manager API in the target Google Cloud project.

Then set the required environment variables:

```bash
export GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
export GOOGLE_CLOUD_LOCATION=us-central1
export GOOGLE_GENAI_USE_VERTEXAI=true
```

`GOOGLE_GENAI_USE_VERTEXAI` is the current google-genai switch for using the Agent Platform backend.
Set `TRACE_TO_CLOUD=true` or `ACMEDESK_TRACE_TO_CLOUD=true` before deployment to enable Cloud Trace.

Deploy every agent:

```bash
make deploy-all
```

The script exports dependencies from the uv lockfile:

```bash
uv export --format requirements.txt --no-dev --no-hashes --no-emit-project \
  --output-file .agent-runtime-temp/requirements.txt
```

Agents are deployed from source files with the Agent Runtime API. This source-file deployment path does not require a Cloud Storage staging bucket.

For each deployed agent, `scripts/deploy_all.sh` creates a clean temporary source directory outside the repository with a root `agent.py` that re-exports that agent's `root_agent`. Specialist temporary entrypoints wrap the ADK agent in an A2A Runtime `A2aAgent`; the coordinator temporary entrypoint wraps the ADK workflow in an Agent Runtime `AdkApp`.

After the specialist Agent Runtime resources are created, the script writes their authenticated A2A card URLs into the coordinator deployment environment variables.

Agent2Agent on Agent Runtime is currently a preview workflow. Keep local A2A URLs for workshop development and use runtime endpoints for the deployment exercise.

## Repository layout

```text
agents/                  ADK agent entrypoints
data/                    Fictional AcmeDesk support corpus
scripts/                 CLI runners and deployment helpers
src/acmedesk_support/    Deterministic data search and brief logic
tests/                   Unit and sample-case tests
```
