from ag_ui.core import RunAgentInput, UserMessage
from fastapi.testclient import TestClient

from agents.coordinator.ag_ui_app import app, user_id_from_input


def test_health_exposes_ag_ui_endpoint():
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert response.json()["endpoint"] == "/ag-ui"


def test_ag_ui_endpoint_is_registered():
    paths = {route.path for route in app.routes}

    assert "/ag-ui" in paths
    assert "/ag-ui/capabilities" in paths


def test_user_id_from_input_reads_forwarded_props():
    run_input = RunAgentInput(
        threadId="thread-1",
        runId="run-1",
        messages=[UserMessage(id="message-1", content="東京から温泉")],
        state={},
        tools=[],
        context=[],
        forwardedProps={"userId": "user-123"},
    )

    assert user_id_from_input(run_input) == "user-123"
