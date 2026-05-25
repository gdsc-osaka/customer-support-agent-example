#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "${REPO_ROOT}/.env"
  set +a
fi

if [[ -z "${GOOGLE_CLOUD_PROJECT:-}" ]]; then
  echo "GOOGLE_CLOUD_PROJECT is required" >&2
  exit 2
fi

REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
UV_BIN="${UV_BIN:-uv}"
LOG_DIR="${REPO_ROOT}/.agent-runtime-temp"
DEPLOY_WORK_DIR="${TMPDIR:-/tmp}/acmedesk-agent-runtime-deploy"
REQ_FILE="${LOG_DIR}/requirements.txt"

mkdir -p "${LOG_DIR}" "${DEPLOY_WORK_DIR}"
rm -rf "${DEPLOY_WORK_DIR}"/source_* "${DEPLOY_WORK_DIR}"/acmedesk_agent_runtime_*
"${UV_BIN}" export \
  --format requirements.txt \
  --no-dev \
  --no-hashes \
  --no-emit-project \
  --output-file "${REQ_FILE}"

# Build a deploy-only env file: drop AI-Studio API key and force Vertex mode so
# the runtime uses its service account ADC (Vertex SessionService rejects API keys).
DEPLOY_ENV_FILE="${LOG_DIR}/deploy.env"
if [[ -f "${REPO_ROOT}/.env" ]]; then
  grep -v -E '^[[:space:]]*(GOOGLE_API_KEY|GOOGLE_GENAI_USE_VERTEXAI)[[:space:]]*=' \
    "${REPO_ROOT}/.env" > "${DEPLOY_ENV_FILE}"
else
  : > "${DEPLOY_ENV_FILE}"
fi
echo "GOOGLE_GENAI_USE_VERTEXAI=true" >> "${DEPLOY_ENV_FILE}"

slugify() {
  printf "%s" "$1" \
    | tr "[:upper:]" "[:lower:]" \
    | sed -E "s/[^a-z0-9_]+/_/g; s/^_+//; s/_+$//"
}

prepare_deploy_source() {
  local source_dir="$1"
  local agent_module="$2"

  rm -rf "${source_dir}"
  mkdir -p "${source_dir}"
  rsync -a \
    --exclude ".git/" \
    --exclude ".venv/" \
    --exclude "__pycache__/" \
    --exclude ".pytest_cache/" \
    --exclude ".ruff_cache/" \
    --exclude ".env" \
    --exclude ".agent-runtime-temp/" \
    --exclude ".agent-engine-temp/" \
    "${REPO_ROOT}/" "${source_dir}/"

  cat > "${source_dir}/agent.py" <<PY
import os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ${agent_module} import root_agent
PY
}

deploy_agent() {
  local name="$1"
  local agent_module="$2"
  local description="$3"
  local agent_slug
  agent_slug="$(slugify "${name}")"
  local source_dir="${DEPLOY_WORK_DIR}/source_${agent_slug}"
  local staging_dir="acmedesk_agent_runtime_${agent_slug}"
  local log_file="${LOG_DIR}/${agent_slug}.deploy.log"
  local env_args=()

  if [[ -f "${DEPLOY_ENV_FILE}" ]]; then
    env_args=(--env_file "${DEPLOY_ENV_FILE}")
  fi

  prepare_deploy_source "${source_dir}" "${agent_module}"

  echo "Deploying ${name} to Gemini Enterprise Agent Platform Agent Runtime..."
  "${UV_BIN}" run adk deploy agent_engine "${source_dir}" \
    --project "${GOOGLE_CLOUD_PROJECT}" \
    --region "${REGION}" \
    --display_name "AcmeDesk ${name}" \
    --description "${description}" \
    --adk_app_object root_agent \
    "${env_args[@]}" \
    --requirements_file "${REQ_FILE}" \
    --temp_folder "${staging_dir}" \
    2>&1 | tee "${log_file}"

  rm -rf "${source_dir}"

  if grep -q "Deploy failed:" "${log_file}"; then
    echo "Deployment failed for ${name}; see ${log_file}" >&2
    return 1
  fi
}

deploy_agent "Ticket History Agent" \
  "agents.ticket_history.agent" \
  "Searches historical AcmeDesk support tickets over A2A."

deploy_agent "Knowledge Base Agent" \
  "agents.knowledge_base.agent" \
  "Searches AcmeDesk FAQ, troubleshooting, runbooks, policies, and known issues over A2A."

deploy_agent "Account Context Agent" \
  "agents.account_context.agent" \
  "Looks up customer account, contract, entitlement, SLA, contact, and health context over A2A."

deploy_agent "Incident Status Agent" \
  "agents.incident_status.agent" \
  "Correlates support cases with active and historical incidents over A2A."

deploy_agent "Escalation Policy Agent" \
  "agents.escalation_policy.agent" \
  "Applies AcmeDesk severity, SLA, escalation, and customer-communication policies over A2A."

deploy_agent "Customer Communication Agent" \
  "agents.customer_communication.agent" \
  "Generates safe customer-facing support response packages over A2A."

deploy_agent "Support Coordinator Agent" \
  "agents.coordinator.agent" \
  "Coordinates specialist A2A agents and produces Customer Support Escalation Briefs."

echo "Agent Runtime deployment commands completed."
echo "Update coordinator A2A endpoint environment variables with the deployed specialist agent cards."
