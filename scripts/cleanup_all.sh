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
LOG_DIR="${REPO_ROOT}/.agent-runtime-temp"
mkdir -p "${LOG_DIR}"

PREFIX="AcmeDesk "
ASSUME_YES=0
DRY_RUN=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Delete every Reasoning Engine (Agent Runtime instance) in the configured
project/region whose display_name starts with the given prefix. Designed to
clean up duplicates produced by older deploy runs.

Options:
  --prefix STR   Display-name prefix to match (default: "AcmeDesk ")
  --all          Delete EVERY reasoning engine in this project/region.
                 (equivalent to --prefix "")
  -y, --yes      Skip the interactive confirmation prompt.
  --dry-run      List what would be deleted but do not delete.
  -h, --help     Show this help.

Environment:
  GOOGLE_CLOUD_PROJECT   required
  GOOGLE_CLOUD_LOCATION  default: us-central1
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) PREFIX="${2:-}"; shift 2 ;;
    --all)    PREFIX=""; shift ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

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
    $'\033[38;5;39m'
    $'\033[38;5;208m'
    $'\033[38;5;42m'
    $'\033[38;5;177m'
    $'\033[38;5;221m'
    $'\033[38;5;51m'
    $'\033[38;5;203m'
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

banner "AcmeDesk Agent Runtime — Cleanup"
info "Project: ${BOLD}${GOOGLE_CLOUD_PROJECT}${RESET}   Region: ${BOLD}${REGION}${RESET}"
if [[ -n "${PREFIX}" ]]; then
  info "Filter:  display_name starts with ${BOLD}\"${PREFIX}\"${RESET}"
else
  warn "Filter:  ${BOLD}<none>${RESET} — every Reasoning Engine in this project/region is in scope!"
fi

info "Fetching Reasoning Engine inventory..."
GCP_TOKEN="$(gcloud auth print-access-token 2>/dev/null || true)"
if [[ -z "${GCP_TOKEN}" ]]; then
  err "Could not obtain an access token via 'gcloud auth print-access-token'."
  err "Run 'gcloud auth login' (or set up ADC) and retry."
  exit 2
fi

INVENTORY_FILE="${LOG_DIR}/cleanup_inventory.tsv"

GCP_TOKEN="${GCP_TOKEN}" \
GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT}" \
REGION="${REGION}" \
PREFIX="${PREFIX}" \
python3 - > "${INVENTORY_FILE}" <<'PY'
import json, os, sys, urllib.request, urllib.error

project = os.environ["GOOGLE_CLOUD_PROJECT"]
region = os.environ["REGION"]
token = os.environ["GCP_TOKEN"]
prefix = os.environ.get("PREFIX", "")

base = f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/reasoningEngines"
url = f"{base}?pageSize=200"
rows = []
try:
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req) as r:
            data = json.load(r)
        for e in data.get("reasoningEngines", []):
            name = e.get("displayName", "")
            if prefix and not name.startswith(prefix):
                continue
            rid = e["name"].rsplit("/", 1)[-1]
            rows.append((name, rid))
        nxt = data.get("nextPageToken")
        url = f"{base}?pageSize=200&pageToken={nxt}" if nxt else None
except urllib.error.HTTPError as err:
    sys.stderr.write(f"ListReasoningEngines failed: HTTP {err.code} {err.reason}\n")
    sys.stderr.write(err.read().decode("utf-8", "replace") + "\n")
    sys.exit(1)

rows.sort()
for name, rid in rows:
    print(f"{name}\t{rid}")
PY

total=$(wc -l < "${INVENTORY_FILE}" | tr -d ' ')
if [[ "${total}" -eq 0 ]]; then
  ok "No matching Reasoning Engines found. Nothing to delete."
  exit 0
fi

info "Found ${BOLD}${total}${RESET} matching Reasoning Engine(s):"

# Tag duplicate display_names so the user can see them clearly.
awk -F'\t' \
  -v dim="${DIM}${FG_GREY}" -v rst="${RESET}" -v yel="${FG_YELLOW}${BOLD}" \
  '{
     count[$1]++; lines[NR]=$0
   }
   END {
     for (i=1; i<=NR; i++) {
       split(lines[i], f, "\t")
       dup = (count[f[1]] > 1) ? sprintf(" %s(duplicate, %d total)%s", yel, count[f[1]], rst) : ""
       printf "  - %-44s %s%s%s%s\n", f[1], dim, f[2], rst, dup
     }
   }' "${INVENTORY_FILE}"
echo

if [[ "${DRY_RUN}" -eq 1 ]]; then
  info "Dry run — no deletions performed."
  exit 0
fi

if [[ "${ASSUME_YES}" -ne 1 ]]; then
  printf "%sType %sDELETE%s%s to confirm deletion of all %d engine(s) (Ctrl-C to abort): %s" \
    "${BOLD}${FG_RED}" "${BOLD}${FG_YELLOW}" "${RESET}" "${BOLD}${FG_RED}" "${total}" "${RESET}"
  read -r confirmation
  if [[ "${confirmation}" != "DELETE" ]]; then
    err "Confirmation did not match. Aborting."
    exit 1
  fi
fi

delete_engine() {
  local display_name="$1"
  local engine_id="$2"
  local color="$3"
  local status_file="$4"
  local prefix="${color}${BOLD}[${display_name} · ${engine_id}]${RESET}"

  set +e
  GCP_TOKEN="${GCP_TOKEN}" \
  PROJECT="${GOOGLE_CLOUD_PROJECT}" \
  REGION="${REGION}" \
  ENGINE_ID="${engine_id}" \
  python3 - 2>&1 <<'PY' \
    | awk -v p="${prefix} " '{ printf "%s%s\n", p, $0; fflush() }'
import json, os, sys, time, urllib.request, urllib.error

project = os.environ["PROJECT"]
region = os.environ["REGION"]
token = os.environ["GCP_TOKEN"]
engine_id = os.environ["ENGINE_ID"]

base = f"https://{region}-aiplatform.googleapis.com/v1"
del_url = f"{base}/projects/{project}/locations/{region}/reasoningEngines/{engine_id}?force=true"

def call(method, u):
    req = urllib.request.Request(u, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    return urllib.request.urlopen(req)

print("DELETE (force=true) submitted...", flush=True)
try:
    with call("DELETE", del_url) as r:
        op = json.load(r)
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", "replace")
    print(f"HTTP {e.code} {e.reason}: {body}", flush=True)
    sys.exit(1)

op_name = op.get("name")
if op.get("done") or not op_name:
    if op.get("error"):
        print(f"failed: {op['error']}", flush=True)
        sys.exit(1)
    print("done.", flush=True)
    sys.exit(0)

op_url = f"{base}/{op_name}"
deadline = time.time() + 900  # 15 min hard cap
tick = 0
while time.time() < deadline:
    time.sleep(5)
    tick += 1
    try:
        with call("GET", op_url) as r:
            op = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"poll error: HTTP {e.code} {e.reason}", flush=True)
        sys.exit(1)
    if op.get("done"):
        if op.get("error"):
            print(f"failed: {op['error']}", flush=True)
            sys.exit(1)
        print("done.", flush=True)
        sys.exit(0)
    if tick % 3 == 0:
        print(f"still deleting... ({tick * 5}s elapsed)", flush=True)

print("timeout waiting for delete operation", flush=True)
sys.exit(1)
PY
  local rc=${PIPESTATUS[0]}
  set -e

  if [[ $rc -ne 0 ]]; then
    printf "%s %s%sFAILED%s\n" "${prefix}" "${BOLD}" "${FG_RED}" "${RESET}" >&2
    echo "fail" > "${status_file}"
    return 1
  fi
  printf "%s %s%sDELETED%s\n" "${prefix}" "${BOLD}" "${FG_GREEN}" "${RESET}"
  echo "ok" > "${status_file}"
}

banner "Launching ${total} parallel deletions"

pids=()
labels=()
status_files=()
i=0
while IFS=$'\t' read -r display_name engine_id; do
  [[ -z "${engine_id}" ]] && continue
  color="${AGENT_COLORS[$(( i % ${#AGENT_COLORS[@]} ))]}"
  status_file="${LOG_DIR}/cleanup_${engine_id}.status"
  rm -f "${status_file}"
  delete_engine "${display_name}" "${engine_id}" "${color}" "${status_file}" &
  pids+=($!)
  labels+=("${display_name} · ${engine_id}")
  status_files+=("${status_file}")
  i=$(( i + 1 ))
done < "${INVENTORY_FILE}"

info "Waiting for ${#pids[@]} background deletions to finish..."

failed=()
for idx in "${!pids[@]}"; do
  if ! wait "${pids[$idx]}"; then
    failed+=("${labels[$idx]}")
  fi
done

banner "Cleanup Summary"
for idx in "${!labels[@]}"; do
  status_file="${status_files[$idx]}"
  if [[ -f "${status_file}" ]] && [[ "$(cat "${status_file}")" == "ok" ]]; then
    printf "  %s%sOK    %s  %s\n" "${BOLD}" "${FG_GREEN}" "${RESET}" "${labels[$idx]}"
  else
    printf "  %s%sFAIL  %s  %s\n" "${BOLD}" "${FG_RED}"   "${RESET}" "${labels[$idx]}"
  fi
done
echo

if (( ${#failed[@]} > 0 )); then
  err "${#failed[@]} deletion(s) failed:"
  for label in "${failed[@]}"; do
    err "  - ${label}"
  done
  exit 1
fi

ok "All ${total} Reasoning Engine(s) deleted successfully."
