UV ?= uv
UV_RUN := $(UV) run

.PHONY: setup lock lint test run run-specialists run-coordinator deploy-all web clean

setup:
	$(UV) sync --extra dev

lock:
	$(UV) lock

lint:
	$(UV_RUN) --extra dev ruff check .

test:
	$(UV_RUN) --extra dev pytest

run:
	@set -e; \
	trap 'for job in $$(jobs -p); do kill "$$job" 2>/dev/null || true; done' INT TERM EXIT; \
	$(MAKE) --no-print-directory run-specialists & \
	$(MAKE) --no-print-directory run-coordinator & \
	$(MAKE) --no-print-directory web & \
	echo "Specialists, coordinator, and ADK Web are starting."; \
	wait

run-specialists:
	@set -e; \
	trap 'kill 0' INT TERM EXIT; \
	PYTHONPATH=src $(UV_RUN) uvicorn agents.ticket_history.agent:app --host 0.0.0.0 --port 8101 & \
	PYTHONPATH=src $(UV_RUN) uvicorn agents.knowledge_base.agent:app --host 0.0.0.0 --port 8102 & \
	PYTHONPATH=src $(UV_RUN) uvicorn agents.account_context.agent:app --host 0.0.0.0 --port 8103 & \
	PYTHONPATH=src $(UV_RUN) uvicorn agents.incident_status.agent:app --host 0.0.0.0 --port 8104 & \
	PYTHONPATH=src $(UV_RUN) uvicorn agents.escalation_policy.agent:app --host 0.0.0.0 --port 8105 & \
	PYTHONPATH=src $(UV_RUN) uvicorn agents.diagnostics.agent:app --host 0.0.0.0 --port 8107 & \
	echo "Specialist A2A agents are running on ports 8101-8105 and 8107."; \
	wait

run-coordinator:
	PYTHONPATH=src $(UV_RUN) uvicorn agents.coordinator.agent:app --host 0.0.0.0 --port 8100

deploy-all:
	./scripts/deploy_all.sh

web:
	PYTHONPATH=src $(UV_RUN) adk web agents --port 8000

clean:
	rm -rf .venv .pytest_cache .ruff_cache .agent-runtime-temp .agent-engine-temp build dist *.egg-info
