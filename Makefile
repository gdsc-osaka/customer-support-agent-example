UV ?= uv
UV_RUN := $(UV) run

.PHONY: setup lock lint test run run-specialists run-coordinator run-ag-ui deploy-all web clean

setup:
	$(UV) sync --extra dev

lock:
	$(UV) lock

lint:
	$(UV_RUN) --extra dev ruff check .

test:
	$(UV_RUN) python -m compileall agents

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
	PYTHONPATH=. $(UV_RUN) uvicorn agents.comfort.agent:app --host 0.0.0.0 --port 8101 & \
	PYTHONPATH=. $(UV_RUN) uvicorn agents.risk.agent:app --host 0.0.0.0 --port 8102 & \
	PYTHONPATH=. $(UV_RUN) uvicorn agents.experience.agent:app --host 0.0.0.0 --port 8103 & \
	PYTHONPATH=. uv run uvicorn agents.collaborative_summary.agent:app --host 0.0.0.0 --port 8111 & \
	PYTHONPATH=. uv run uvicorn agents.collaborative_ideas.agent:app --host 0.0.0.0 --port 8112 & \
	PYTHONPATH=. uv run uvicorn agents.collaborative.agent:app --host 0.0.0.0 --port 8110 & \
	echo "Specialist A2A agents are running on ports 8101-8103."; \
	wait

run-coordinator:
	PYTHONPATH=. $(UV_RUN) uvicorn agents.coordinator.agent:app --host 0.0.0.0 --port 8100

run-ag-ui:
	PYTHONPATH=. $(UV_RUN) uvicorn agents.coordinator.ag_ui_app:app --host 0.0.0.0 --port 8200

deploy-all:
	./scripts/deploy_all.sh

web:
	PYTHONPATH=. $(UV_RUN) adk web agents --port 8000

clean:
	rm -rf .venv .pytest_cache .ruff_cache .agent-runtime-temp .agent-engine-temp build dist *.egg-info
