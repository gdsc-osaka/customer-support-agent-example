# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.11 ADK/A2A customer support escalation example. Core deterministic logic lives in `src/hirenest_support/`, including ticket search, account context, incident status, diagnostics, policy lookup, communication drafting, and redaction. ADK agent entrypoints live in `agents/`, with one package per specialist plus `agents/coordinator/`. The coordinator is split across `agent.py`, `nodes.py`, `schemas.py`, `steps.py`, and `constants.py`; keep workflow changes explicit there. Fictional support corpora and policy fixtures live in `data/`, grouped by domain such as `tickets/`, `accounts/`, `incidents/`, `knowledge_base/`, `product/`, and `policies/`. Helper scripts are in `scripts/`, and tests are in `tests/`.

## Build, Test, and Development Commands

Use `uv` through the Makefile; dependencies are pinned in `pyproject.toml` and `uv.lock`.

- `make setup`: install runtime and dev dependencies.
- `make lock`: refresh `uv.lock` after dependency changes.
- `make lint`: run Ruff checks.
- `make test`: run the pytest suite.
- `make run`: start specialists, the coordinator, and ADK Web together.
- `make run-specialists`: start specialist A2A services on ports `8101`-`8105` and `8107`.
- `make run-coordinator`: start the coordinator service on port `8100`.
- `make deploy-all`: run `scripts/deploy_all.sh`.
- `make web`: start ADK Web for the `agents/` directory on port `8000`.

## Coding Style & Naming Conventions

Follow the existing Python style: 4-space indentation, type hints where useful, small pure functions in `src/hirenest_support/`, and explicit agent wiring in `agents/*/agent.py`. Ruff targets Python 3.11 with a 100-character line length and rules `E`, `F`, `I`, `UP`, and `B`; run `make lint` before submitting. Use snake_case for modules, functions, variables, and test names. Keep fixture names descriptive, for example `2026-q1-calendar-integration.jsonl` or `scheduling-integrations-runbook.md`.

## Testing Guidelines

Tests use `pytest` with `pytest-asyncio`; configuration sets `pythonpath = ["src", "."]` and discovers tests under `tests/`. Name test files `test_*.py` and test functions `test_*`. Add focused unit tests for search, policy, redaction, loaders, diagnostics, communication drafting, and coordinator input formatting changes. For workflow behavior, prefer assertions against deterministic coordinator helpers over live LLM calls.

## Commit & Pull Request Guidelines

Current history uses short, imperative, lower-case commit messages, such as `add example repo for create-multi-agent`. Keep commits focused and describe the behavior or asset changed. Pull requests should include a concise summary, tests run (`make lint` or `make test`), linked issue or lab step when applicable, and screenshots only for UI-facing ADK Web changes. Call out environment, port, or deployment changes.

## Security & Configuration Tips

Do not commit real credentials. Copy `.env.example` to `.env` for local work and set either `GOOGLE_API_KEY` or the Agent Platform variables described in `README.md`. Treat `data/` as fictional fixtures; keep any new customer examples synthetic and run redaction tests when modifying privacy-related logic.
