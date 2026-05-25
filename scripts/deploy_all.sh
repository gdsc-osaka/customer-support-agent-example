#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

load_env_defaults() {
  local env_file="$1"
  local line key
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "${line}" || "${line}" == \#* || "${line}" != *=* ]] && continue
    key="${line%%=*}"
    key="${key%"${key##*[![:space:]]}"}"
    if [[ -z "${!key+x}" ]]; then
      export "${line}"
    fi
  done < "${env_file}"
}

if [[ -f "${REPO_ROOT}/.env" ]]; then
  load_env_defaults "${REPO_ROOT}/.env"
fi

if [[ -z "${GOOGLE_CLOUD_PROJECT:-}" ]]; then
  echo "GOOGLE_CLOUD_PROJECT is required" >&2
  exit 2
fi

REGION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
UV_BIN="${UV_BIN:-uv}"
LOG_DIR="${REPO_ROOT}/.agent-runtime-temp"
DEPLOY_WORK_DIR="${LOG_DIR}/deploy-work"
REQ_FILE="${LOG_DIR}/requirements.txt"
TRACE_TO_CLOUD="${TRACE_TO_CLOUD:-${ACMEDESK_TRACE_TO_CLOUD:-false}}"
A2A_ENV_NAMES=(
  TICKET_HISTORY_A2A_URL
  KNOWLEDGE_BASE_A2A_URL
  ACCOUNT_CONTEXT_A2A_URL
  INCIDENT_STATUS_A2A_URL
  ESCALATION_POLICY_A2A_URL
  CUSTOMER_COMMUNICATION_A2A_URL
)

# --- ANSI styling ---------------------------------------------------------
if [[ -t 1 ]] && [[ "${NO_COLOR:-}" == "" ]]; then
  RESET=$'\033[0m'
  BOLD=$'\033[1m'
  DIM=$'\033[2m'
  FG_RED=$'\033[38;5;203m'
  FG_GREEN=$'\033[38;5;42m'
  FG_YELLOW=$'\033[38;5;221m'
  FG_BLUE=$'\033[38;5;39m'
  FG_GREY=$'\033[38;5;245m'
  AGENT_COLORS=(
    $'\033[38;5;39m'   # blue
    $'\033[38;5;208m'  # orange
    $'\033[38;5;42m'   # green
    $'\033[38;5;177m'  # magenta
    $'\033[38;5;221m'  # yellow
    $'\033[38;5;51m'   # cyan
    $'\033[38;5;203m'  # red/pink
  )
else
  RESET=""; BOLD=""; DIM=""
  FG_RED=""; FG_GREEN=""; FG_YELLOW=""; FG_BLUE=""; FG_GREY=""
  AGENT_COLORS=("" "" "" "" "" "" "")
fi

banner() {
  local title="$1"
  local line
  line="$(printf '%.0s─' {1..72})"
  printf "\n%s%s┌%s┐%s\n"     "${BOLD}" "${FG_BLUE}" "${line}" "${RESET}"
  printf "%s%s│%s %-70s %s│%s\n" "${BOLD}" "${FG_BLUE}" "${RESET}" "${title}" "${BOLD}${FG_BLUE}" "${RESET}"
  printf "%s%s└%s┘%s\n\n"     "${BOLD}" "${FG_BLUE}" "${line}" "${RESET}"
}

info()  { printf "%s[info]%s %s\n"  "${FG_BLUE}${BOLD}"   "${RESET}" "$*"; }
ok()    { printf "%s[ ok ]%s %s\n"  "${FG_GREEN}${BOLD}"  "${RESET}" "$*"; }
warn()  { printf "%s[warn]%s %s\n"  "${FG_YELLOW}${BOLD}" "${RESET}" "$*"; }
err()   { printf "%s[fail]%s %s\n"  "${FG_RED}${BOLD}"    "${RESET}" "$*" >&2; }

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

validate_coordinator_a2a_env() {
  local missing=()
  local env_name
  for env_name in "${A2A_ENV_NAMES[@]}"; do
    if ! grep -q -E "^${env_name}=" "${DEPLOY_ENV_FILE}"; then
      missing+=("${env_name}")
    fi
  done

  if (( ${#missing[@]} == 0 )); then
    return 0
  fi

  err "Coordinator deployment needs Agent Runtime A2A card URLs for every specialist."
  err "Missing: ${missing[*]}"
  return 1
}

extract_engine_id_from_log() {
  sed -nE \
    's#.*projects/[^/]+/locations/[^/]+/reasoningEngines/([0-9]+).*#\1#p' "$1" \
    | tail -n 1
}

runtime_a2a_card_url() {
  local resource_id="$1"
  printf "https://%s-aiplatform.googleapis.com/v1beta1/projects/%s/locations/%s/reasoningEngines/%s/a2a/v1/card" \
    "${REGION}" "${GOOGLE_CLOUD_PROJECT}" "${REGION}" "${resource_id}"
}

append_specialist_a2a_card_urls() {
  local entry name _module _description env_name agent_slug engine_id_file engine_id card_url

  info "Building specialist Agent Runtime A2A card URLs..."
  for entry in "${SPECIALIST_AGENTS[@]}"; do
    IFS='|' read -r name _module _description env_name <<< "${entry}"
    agent_slug="$(slugify "${name}")"
    engine_id_file="${LOG_DIR}/${agent_slug}.engine_id"
    if [[ ! -s "${engine_id_file}" ]]; then
      err "Missing Agent Runtime resource ID for ${name}; expected ${engine_id_file}"
      return 1
    fi
    engine_id="$(cat "${engine_id_file}")"
    card_url="$(runtime_a2a_card_url "${engine_id}")"
    printf "%s=%s\n" "${env_name}" "${card_url}" >> "${DEPLOY_ENV_FILE}"
    printf "  %s=%s\n" "${env_name}" "${card_url}"
  done
}

mkdir -p "${LOG_DIR}" "${DEPLOY_WORK_DIR}"
rm -rf "${DEPLOY_WORK_DIR}"/source_* "${DEPLOY_WORK_DIR}"/acmedesk_agent_runtime_*

EXISTING_ENGINES_FILE="${LOG_DIR}/existing_engines.tsv"

banner "AcmeDesk Agent Runtime — Parallel Deploy"
info "Project: ${BOLD}${GOOGLE_CLOUD_PROJECT}${RESET}   Region: ${BOLD}${REGION}${RESET}"
info "Logs:    ${LOG_DIR}"

info "Fetching existing Agent Runtime resources (to update in place rather than duplicate)..."
GCP_TOKEN="$(gcloud auth print-access-token 2>/dev/null || true)"
if [[ -z "${GCP_TOKEN}" ]]; then
  err "Could not obtain an access token via 'gcloud auth print-access-token'."
  err "Run 'gcloud auth login' (or set up ADC) so the script can look up existing Agent Runtime resource IDs;"
  err "otherwise each run would create duplicate agents instead of updating them."
  exit 2
fi

GCP_TOKEN="${GCP_TOKEN}" \
GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT}" \
REGION="${REGION}" \
python3 - > "${EXISTING_ENGINES_FILE}" <<'PY'
import json, os, sys, urllib.request, urllib.error

project = os.environ["GOOGLE_CLOUD_PROJECT"]
region = os.environ["REGION"]
token = os.environ["GCP_TOKEN"]

base = f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/reasoningEngines"
url = f"{base}?pageSize=200"
results = {}
try:
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req) as r:
            data = json.load(r)
        for e in data.get("reasoningEngines", []):
            rid = e["name"].rsplit("/", 1)[-1]
            results[e.get("displayName", "")] = rid
        nxt = data.get("nextPageToken")
        url = f"{base}?pageSize=200&pageToken={nxt}" if nxt else None
except urllib.error.HTTPError as err:
    sys.stderr.write(f"ListReasoningEngines failed: HTTP {err.code} {err.reason}\n")
    sys.stderr.write(err.read().decode("utf-8", "replace") + "\n")
    sys.exit(1)

for name, rid in results.items():
    print(f"{name}\t{rid}")
PY

existing_count=$(wc -l < "${EXISTING_ENGINES_FILE}" | tr -d ' ')
info "Found ${BOLD}${existing_count}${RESET} existing Agent Runtime resource(s) in this project/region."

lookup_engine_id() {
  awk -F'\t' -v n="$1" '$1 == n { print $2; exit }' "${EXISTING_ENGINES_FILE}"
}

info "Exporting requirements..."
"${UV_BIN}" export \
  --format requirements.txt \
  --no-dev \
  --no-hashes \
  --no-emit-project \
  --output-file "${REQ_FILE}"

# Build a deploy-only env file: drop AI-Studio API key and force Vertex mode so
# the runtime uses its service account ADC (Vertex SessionService rejects API keys).
# Agent Runtime owns GOOGLE_CLOUD_* deployment env vars; setting them explicitly
# in spec.deployment_spec.env is rejected.
DEPLOY_ENV_FILE="${LOG_DIR}/deploy.env"
if [[ -f "${REPO_ROOT}/.env" ]]; then
  grep -v -E '^[[:space:]]*(GOOGLE_API_KEY|GOOGLE_GENAI_USE_VERTEXAI|GOOGLE_CLOUD_PROJECT|GOOGLE_CLOUD_LOCATION|GOOGLE_CLOUD_REGION|TRACE_TO_CLOUD|ACMEDESK_TRACE_TO_CLOUD|[A-Z_]+_A2A_URL)[[:space:]]*=' \
    "${REPO_ROOT}/.env" > "${DEPLOY_ENV_FILE}" || true
else
  : > "${DEPLOY_ENV_FILE}"
fi
echo "GOOGLE_GENAI_USE_VERTEXAI=true" >> "${DEPLOY_ENV_FILE}"
echo "ACMEDESK_A2A_USE_ADC_AUTH=true" >> "${DEPLOY_ENV_FILE}"
if is_truthy "${TRACE_TO_CLOUD}"; then
  echo "ACMEDESK_TRACE_TO_CLOUD=true" >> "${DEPLOY_ENV_FILE}"
fi

slugify() {
  printf "%s" "$1" \
    | tr "[:upper:]" "[:lower:]" \
    | sed -E "s/[^a-z0-9_]+/_/g; s/^_+//; s/_+$//"
}

prepare_deploy_source() {
  local source_dir="$1"
  local agent_module="$2"
  local deploy_kind="$3"
  local description="$4"
  local description_literal
  local trace_literal="False"
  description_literal="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "${description}")"
  if is_truthy "${TRACE_TO_CLOUD}"; then
    trace_literal="True"
  fi

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

  cp "${REQ_FILE}" "${source_dir}/requirements.txt"

  if [[ "${deploy_kind}" == "a2a" ]]; then
    cat > "${source_dir}/agent.py" <<PY
import os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agents._runtime_a2a import build_runtime_a2a_agent
from ${agent_module} import root_agent as adk_root_agent

root_agent = build_runtime_a2a_agent(adk_root_agent, description=${description_literal})
PY
  else
    cat > "${source_dir}/agent.py" <<PY
import os, sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ${agent_module} import root_agent
PY
    cat > "${source_dir}/agent_runtime_app.py" <<PY
import os
import vertexai
from google.adk.apps import App
from vertexai.agent_engines import AdkApp

from agent import root_agent

vertexai.init(
    project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
    location=os.environ.get("GOOGLE_CLOUD_LOCATION"),
)

adk_app = AdkApp(
    app=App(name=root_agent.name or "acmedesk_agent", root_agent=root_agent),
    enable_tracing=${trace_literal},
)
PY
  fi
}

deploy_runtime_source_agent() {
  local source_dir="$1"
  local display_name="$2"
  local description="$3"
  local existing_id="$4"
  local deploy_kind="$5"

  set +e
  GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT}" \
  GOOGLE_CLOUD_LOCATION="${REGION}" \
  SOURCE_DIR="${source_dir}" \
  DISPLAY_NAME="${display_name}" \
  DESCRIPTION="${description}" \
  EXISTING_ID="${existing_id}" \
  DEPLOY_ENV_FILE="${DEPLOY_ENV_FILE}" \
  DEPLOY_KIND="${deploy_kind}" \
  "${UV_BIN}" run python - <<'PY'
from __future__ import annotations

import importlib
import os
import sys

import vertexai
from google.genai import types as genai_types


def load_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key] = value
    return env


project = os.environ["GOOGLE_CLOUD_PROJECT"]
location = os.environ["GOOGLE_CLOUD_LOCATION"]
source_dir = os.environ["SOURCE_DIR"]
display_name = os.environ["DISPLAY_NAME"]
description = os.environ["DESCRIPTION"]
existing_id = os.environ.get("EXISTING_ID", "")
env_vars = load_env(os.environ["DEPLOY_ENV_FILE"])
deploy_kind = os.environ["DEPLOY_KIND"]

os.chdir(source_dir)
sys.path.insert(0, source_dir)

vertexai.init(project=project, location=location)
client = vertexai.Client(
    project=project,
    location=location,
    http_options=genai_types.HttpOptions(api_version="v1beta1"),
)

if deploy_kind == "a2a":
    root_agent = importlib.import_module("agent").root_agent
    entrypoint_module = "agent"
    entrypoint_object = "root_agent"
    source_packages = [
        "agent.py",
        "agents",
        "data",
        "pyproject.toml",
        "requirements.txt",
        "src",
    ]
    class_methods = []
    for mode, method_names in root_agent.register_operations().items():
        for method_name in method_names:
            class_methods.append(
                {
                    "name": method_name,
                    "description": None,
                    "parameters": {
                        "properties": {},
                        "type": "object",
                        "required": ["request", "context"],
                    },
                    "api_mode": mode,
                    "a2a_agent_card": root_agent.agent_card.model_dump_json(
                        exclude_none=True,
                        by_alias=True,
                    ),
                }
            )
    agent_framework = None
else:
    from google.adk.cli.cli_deploy import _AGENT_ENGINE_CLASS_METHODS

    importlib.import_module("agent_runtime_app").adk_app
    entrypoint_module = "agent_runtime_app"
    entrypoint_object = "adk_app"
    source_packages = [
        "agent.py",
        "agent_runtime_app.py",
        "agents",
        "data",
        "pyproject.toml",
        "requirements.txt",
        "src",
    ]
    class_methods = _AGENT_ENGINE_CLASS_METHODS
    agent_framework = "google-adk"

config = {
    "display_name": display_name,
    "description": description,
    "source_packages": source_packages,
    "entrypoint_module": entrypoint_module,
    "entrypoint_object": entrypoint_object,
    "requirements_file": "requirements.txt",
    "env_vars": env_vars,
    "class_methods": class_methods,
}
if agent_framework:
    config["agent_framework"] = agent_framework

for path in config["source_packages"]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Configured source package does not exist: {path}")

if existing_id:
    resource_name = (
        f"projects/{project}/locations/{location}/reasoningEngines/{existing_id}"
    )
    agent_engine = client.agent_engines.update(name=resource_name, config=config)
else:
    agent_engine = client.agent_engines.create(config=config)

name = agent_engine.api_resource.name
print(f"Deployed Agent Runtime resource: {name}")
PY
  local rc=$?
  set -e
  return "${rc}"
}

deploy_agent() {
  local name="$1"
  local agent_module="$2"
  local description="$3"
  local color="$4"
  local deploy_kind="${5:-adk}"

  local agent_slug
  agent_slug="$(slugify "${name}")"
  local source_dir="${DEPLOY_WORK_DIR}/source_${agent_slug}"
  local log_file="${LOG_DIR}/${agent_slug}.deploy.log"
  local status_file="${LOG_DIR}/${agent_slug}.status"
  local engine_id_file="${LOG_DIR}/${agent_slug}.engine_id"
  local prefix="${color}${BOLD}[${name}]${RESET}"

  local display_name="AcmeDesk ${name}"
  local existing_id
  existing_id="$(lookup_engine_id "${display_name}")"
  local action_label
  if [[ -n "${existing_id}" ]]; then
    action_label="updating ${FG_YELLOW}${existing_id}${RESET}"
  else
    action_label="${FG_GREEN}creating new${RESET}"
  fi

  prepare_deploy_source "${source_dir}" "${agent_module}" "${deploy_kind}" "${description}"

  printf "%s %s→ %s%s\n" \
    "${prefix}" "${DIM}${FG_GREY}" "${action_label}${DIM}${FG_GREY}" "${RESET}"

  local rc
  set +e
  deploy_runtime_source_agent \
    "${source_dir}" \
    "${display_name}" \
    "${description}" \
    "${existing_id}" \
    "${deploy_kind}" \
    2>&1 \
    | tee "${log_file}" \
    | awk -v p="${prefix} " '{ printf "%s%s\n", p, $0; fflush(); }'
  rc=${PIPESTATUS[0]}
  set -e

  rm -rf "${source_dir}"

  if [[ $rc -ne 0 ]] || grep -q "Deploy failed:" "${log_file}"; then
    printf "%s %s%sFAILED%s  log: %s\n" \
      "${prefix}" "${BOLD}" "${FG_RED}" "${RESET}" "${log_file}" >&2
    echo "fail" > "${status_file}"
    return 1
  fi

  local deployed_engine_id
  deployed_engine_id="$(extract_engine_id_from_log "${log_file}")"
  if [[ -z "${deployed_engine_id}" && -n "${existing_id}" ]]; then
    deployed_engine_id="${existing_id}"
  fi
  if [[ -n "${deployed_engine_id}" ]]; then
    echo "${deployed_engine_id}" > "${engine_id_file}"
  fi

  printf "%s %s%sSUCCESS%s\n" \
    "${prefix}" "${BOLD}" "${FG_GREEN}" "${RESET}"
  echo "ok" > "${status_file}"
}

# Specialist agents to deploy, one per line: NAME|MODULE|DESCRIPTION|A2A_URL_ENV_NAME
SPECIALIST_AGENTS=(
  "Ticket History Agent|agents.ticket_history.agent|Searches historical AcmeDesk support tickets over A2A.|TICKET_HISTORY_A2A_URL"
  "Knowledge Base Agent|agents.knowledge_base.agent|Searches AcmeDesk FAQ, troubleshooting, runbooks, policies, and known issues over A2A.|KNOWLEDGE_BASE_A2A_URL"
  "Account Context Agent|agents.account_context.agent|Looks up customer account, contract, entitlement, SLA, contact, and health context over A2A.|ACCOUNT_CONTEXT_A2A_URL"
  "Incident Status Agent|agents.incident_status.agent|Correlates support cases with active and historical incidents over A2A.|INCIDENT_STATUS_A2A_URL"
  "Escalation Policy Agent|agents.escalation_policy.agent|Applies AcmeDesk severity, SLA, escalation, and customer-communication policies over A2A.|ESCALATION_POLICY_A2A_URL"
  "Customer Communication Agent|agents.customer_communication.agent|Generates safe customer-facing support response packages over A2A.|CUSTOMER_COMMUNICATION_A2A_URL"
)
COORDINATOR_AGENT=(
  "Support Coordinator Agent|agents.coordinator.agent|Coordinates specialist A2A agents and produces Customer Support Escalation Briefs."
)
AGENTS=("${SPECIALIST_AGENTS[@]}" "${COORDINATOR_AGENT[@]}")

banner "Launching ${#SPECIALIST_AGENTS[@]} specialist deployments"

pids=()
names=()
i=0
for entry in "${SPECIALIST_AGENTS[@]}"; do
  IFS='|' read -r name module description _env_name <<< "${entry}"
  color="${AGENT_COLORS[$(( i % ${#AGENT_COLORS[@]} ))]}"
  # Clear any stale status from a previous run.
  rm -f "${LOG_DIR}/$(slugify "${name}").status"
  deploy_agent "${name}" "${module}" "${description}" "${color}" "a2a" &
  pids+=($!)
  names+=("${name}")
  i=$(( i + 1 ))
done

info "Waiting for ${#pids[@]} background deployments to finish..."

failed=()
for idx in "${!pids[@]}"; do
  if ! wait "${pids[$idx]}"; then
    failed+=("${names[$idx]}")
  fi
done

banner "Specialist Deployment Summary"
for entry in "${SPECIALIST_AGENTS[@]}"; do
  IFS='|' read -r name _ _ _ <<< "${entry}"
  status_file="${LOG_DIR}/$(slugify "${name}").status"
  if [[ -f "${status_file}" ]] && [[ "$(cat "${status_file}")" == "ok" ]]; then
    printf "  %s%sOK  %s  %s\n" "${BOLD}" "${FG_GREEN}" "${RESET}" "${name}"
  else
    printf "  %s%sFAIL%s  %s\n" "${BOLD}" "${FG_RED}"   "${RESET}" "${name}"
  fi
done
echo

if (( ${#failed[@]} > 0 )); then
  err "${#failed[@]} deployment(s) failed: ${failed[*]}"
  err "Inspect per-agent logs under ${LOG_DIR}/<slug>.deploy.log"
  exit 1
fi

append_specialist_a2a_card_urls

if ! validate_coordinator_a2a_env; then
  exit 2
fi

banner "Launching coordinator deployment"
IFS='|' read -r name module description <<< "${COORDINATOR_AGENT[0]}"
rm -f "${LOG_DIR}/$(slugify "${name}").status"
if ! deploy_agent "${name}" "${module}" "${description}" "${AGENT_COLORS[6]}"; then
  err "Coordinator deployment failed; inspect ${LOG_DIR}/$(slugify "${name}").deploy.log"
  exit 1
fi

ok "All ${#AGENTS[@]} agents deployed successfully."
