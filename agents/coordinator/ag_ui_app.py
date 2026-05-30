from __future__ import annotations

from typing import Any

from ag_ui.core import RunAgentInput
from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents.coordinator.agent import root_agent

APP_NAME = root_agent.name or "dynamic_travel_planning_agent"
DEFAULT_USER_ID = "ag-ui-user"


def user_id_from_input(input_data: RunAgentInput) -> str:
    forwarded_props: Any = input_data.forwarded_props
    if isinstance(forwarded_props, dict):
        return str(
            forwarded_props.get("userId")
            or forwarded_props.get("user_id")
            or DEFAULT_USER_ID
        )
    return DEFAULT_USER_ID


app = FastAPI(
    title="Dynamic Travel Planning Agent AG-UI",
    description="AG-UI endpoint for the ADK travel planning coordinator.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

agent = ADKAgent(
    adk_agent=root_agent,
    app_name=APP_NAME,
    user_id_extractor=user_id_from_input,
    use_thread_id_as_session_id=True,
)
add_adk_fastapi_endpoint(app, agent, path="/ag-ui")


@app.get("/")
async def health() -> dict[str, str]:
    return {
        "name": APP_NAME,
        "protocol": "AG-UI",
        "endpoint": "/ag-ui",
    }
