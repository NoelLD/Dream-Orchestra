#!/usr/bin/env bash
# Gated chain: record cell demos on Modal -> checks -> upload -> fine-tune. Every gate aborts BEFORE any payment.
# Run from Dream-Orchestra/ on the host (needs modal CLI, docker compose, the simulation service on :3001):
#   bash src/Simulation/tools/chain_cells.sh --dry-run   # local test set, no Modal, no upload, prints the request
#   bash src/Simulation/tools/chain_cells.sh             # REAL: Modal (~0.30 $), upload, fine-tune 500 steps = 100 $
# Log: src/Simulation/data/datasets/<NAME>.chain.log
# Settings (reviewed 22.11. 04:15, Codex + Grok): 160 episodes = 40 per task; cosine (tutorial: best for
# specialization; no resume needed before the deadline); base_share 0.0 (cell data only: largest effect in the
# cells, may lose general skill - we only measure in the cells); 500 steps (minimum, ~4 h).
set -euo pipefail

NAME="${NAME:-cells-v1}"
COUNT="${COUNT:-160}"
FIRST_SEED="${FIRST_SEED:-4000}"
MIN_EPISODES="${MIN_EPISODES:-140}"
MIN_PER_TASK="${MIN_PER_TASK:-35}"
DEADLINE="${DEADLINE:-05:45}"   # no paid start after this time today (or tomorrow if started before midnight)
STEPS=500                       # fixed: the confirmed price is 100 $; change the script, not an env var
SUFFIX="${SUFFIX:-yam-cells-c500}"
LR_SCHEDULE="${LR_SCHEDULE:-cosine}"
BASE_SHARE="${BASE_SHARE:-0.0}"
API="${API:-http://localhost:3001}"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1
[[ $DRY == 1 ]] && NAME="cells-test"
[[ "$NAME$SUFFIX" =~ ^[a-z0-9-]+$ ]] || { echo "bad NAME/SUFFIX"; exit 1; }
[[ "$LR_SCHEDULE" =~ ^(cosine|constant)$ && "$BASE_SHARE" =~ ^(0\.0|0\.5)$ ]] || { echo "bad LR_SCHEDULE/BASE_SHARE"; exit 1; }

cd "$(dirname "$0")/../../.."   # Dream-Orchestra/
DATA="src/Simulation/data/datasets"
LOG="$DATA/$NAME.chain.log"
mkdir -p "$DATA"
PAID=0
log() { echo "$(date '+%H:%M:%S') $*" | tee -a "$LOG"; }
die() {
  if [[ $PAID == 1 ]]; then log "ABORT AFTER the fine-tune request was sent - check: curl -s $API/finetune"; else
    log "ABORT (no fine-tune started): $*"; fi
  exit 1
}
sim() { docker compose run --rm --no-deps -T simulation python "$@" 2>&1 | grep -v ' Container ' ; return "${PIPESTATUS[0]}"; }
api() { curl -sS --fail-with-body --connect-timeout 5 --max-time 60 "$@"; }
count_tasks() {  # "<n> <prompt>" lines for every session with meta
  for d in "$DATA/$NAME"/ep-*; do
    [[ -f "$d/meta/info.json" ]] && sed -n 's/.*"task": "\(.*\)"}/\1/p' "$d/meta/tasks.jsonl"
  done | sort | uniq -c
}
check_counts() {  # $1 = label; all four prompts present, totals and minimum per task
  local counts total tasks mint
  counts=$(count_tasks)
  log "$1:"; echo "$counts" | tee -a "$LOG"
  total=$(echo "$counts" | awk '{s+=$1} END {print s+0}')
  tasks=$(echo "$counts" | grep -c . || true)
  mint=$(echo "$counts" | awk 'NR==1{m=$1} $1<m{m=$1} END {print m+0}')
  [[ $DRY == 1 ]] && { log "dry run: count gates skipped ($total sessions)"; return 0; }
  (( tasks == 4 )) || die "$1: only $tasks of 4 tasks"
  (( total >= MIN_EPISODES )) || die "$1: only $total episodes (< $MIN_EPISODES)"
  (( mint >= MIN_PER_TASK )) || die "$1: a task has only $mint episodes (< $MIN_PER_TASK)"
  log "$1 OK: $total episodes, min $mint per task"
}

# 0. one chain per dataset (atomic), dated deadline
mkdir "$DATA/$NAME.chain.lock" 2>/dev/null || { echo "another chain holds $DATA/$NAME.chain.lock"; exit 1; }
trap 'rmdir "$DATA/$NAME.chain.lock" 2>/dev/null || true' EXIT
TODAY=$(date +%Y-%m-%d)
DEADLINE_TS=$(date -j -f "%Y-%m-%d %H:%M" "$TODAY $DEADLINE" +%s)
(( DEADLINE_TS > $(date +%s) )) || DEADLINE_TS=$(( DEADLINE_TS + 86400 ))   # started before midnight
(( DEADLINE_TS - $(date +%s) < 12 * 3600 )) || { echo "deadline more than 12 h away: check DEADLINE"; exit 1; }
log "chain start name=$NAME count=$COUNT seeds=$FIRST_SEED.. steps=$STEPS $LR_SCHEDULE base_share=$BASE_SHARE" \
    "deadline=$(date -r "$DEADLINE_TS" '+%d.%m. %H:%M') dry=$DRY"
api "$API/health" >/dev/null || die "simulation service not reachable at $API"
[[ $DRY == 1 || ! -e "$DATA/$NAME.finetune_started" ]] || die "a fine-tune was already requested for $NAME"

# 1. generate
if [[ $DRY == 0 ]]; then
  [[ ! -e "$DATA/$NAME" ]] || die "$DATA/$NAME exists: use a new NAME (no unchecked old sessions)"
  modal run src/Simulation/tools/modal_gen.py --script cells --name "$NAME" --count "$COUNT" \
    --first-seed "$FIRST_SEED" 2>&1 | grep -E "seed|done|error|sessions exist" | tee -a "$LOG" \
    || log "modal_gen exited non-zero (partial results are judged by the gates below)"
fi
mkdir -p "$DATA/$NAME.sim_results"   # stray sim_results beside the sessions break the validator
mv "$DATA/$NAME"/*.sim_results.json "$DATA/$NAME.sim_results/" 2>/dev/null || true
check_counts "recorded"

# 2. strict open-loop replay (no settle, own part only, start state must match), failures moved aside
REJECT=()
[[ $DRY == 0 ]] && REJECT=(--reject "/data/datasets/$NAME.rejected")
REPLAY=$(sim /app/tools/replay_check_cells.py "datasets/$NAME" --min-rate 0.9 ${REJECT[@]+"${REJECT[@]}"}) \
  || { echo "$REPLAY" | tail -8 >> "$LOG"; die "replay check below 90 %"; }
echo "$REPLAY" > "$DATA/$NAME.replay.jsonl"
echo "$REPLAY" | tail -2 | tee -a "$LOG"
echo "$REPLAY" | tail -1 | grep -q "PASS" || die "replay check did not report PASS"
check_counts "after replay"

# 3. format validation (offline, Dream SDK)
sim /app/tools/validate.py "datasets/$NAME" | tail -2 | tee -a "$LOG" || die "validate_dataset failed"

# 4. manifest: what exactly is uploaded, from which code
( git rev-parse HEAD; git status --porcelain -- src/Simulation/tools src/Simulation/app
  cd "$DATA" && find "$NAME" -type f | sort | xargs shasum -a 256 ) > "$DATA/$NAME.manifest.txt"
log "manifest: $DATA/$NAME.manifest.txt ($(wc -l < "$DATA/$NAME.manifest.txt") lines)"

BODY=$(python3 -c 'import json,sys; print(json.dumps({"robot": "yam-sim", "dataset": sys.argv[1], "suffix": sys.argv[2],
  "steps": 500, "lr_schedule": sys.argv[3], "base_share": float(sys.argv[4]), "confirm_cost_usd": 100}))' \
  "$NAME" "$SUFFIX" "$LR_SCHEDULE" "$BASE_SHARE")
if [[ $DRY == 1 ]]; then
  log "dry run complete. The real run would upload and then POST $API/finetune with: $BODY"
  exit 0
fi

# 5. upload via the service; bind to THIS upload's Dream dataset id; poll until processed (wall clock 45 min)
BEFORE=$(api "$API/datasets/$NAME" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("dream_dataset_id"))' || echo None)
RESP=$(api -X POST "$API/datasets/$NAME/upload") || die "upload request failed: $RESP"
log "upload accepted: $RESP"
END=$(( $(date +%s) + 45 * 60 ))
STATUS=""; DSID="None"
while (( $(date +%s) < END )); do
  REC=$(api "$API/datasets/$NAME") || { log "status poll failed, retrying"; sleep 30; continue; }
  read -r STATUS DSID < <(echo "$REC" | python3 -c 'import json,sys; r=json.load(sys.stdin); print(r.get("status"), r.get("dream_dataset_id"))')
  log "dataset status: $STATUS (dream id $DSID)"
  [[ "$STATUS" == "failed" ]] && die "upload/processing failed: $REC"
  [[ "$STATUS" == "processed" && "$DSID" != "None" && "$DSID" != "$BEFORE" ]] && break
  sleep 30
done
[[ "$STATUS" == "processed" && "$DSID" != "$BEFORE" ]] || die "dataset not processed after 45 min (status $STATUS)"

# 6. the paid step: once, no retries, not after the deadline
(( $(date +%s) <= DEADLINE_TS )) || die "past start deadline $DEADLINE: the model would finish too late to measure"
( set -o noclobber; echo "$(date) $BODY" > "$DATA/$NAME.finetune_started" ) 2>/dev/null \
  || die "a fine-tune was already requested for $NAME"
log "starting fine-tune: $BODY"
PAID=1
RESP=$(curl -sS --connect-timeout 5 --max-time 120 -w '\nHTTP %{http_code}' -X POST "$API/finetune" \
  -H 'content-type: application/json' -d "$BODY") || true
log "fine-tune response: $RESP"
echo "$RESP" | grep -q '"job_id"' || die "fine-tune response has no job_id (do NOT retry blindly; check the job list)"
log "chain done. Status: curl -s $API/finetune | python3 -m json.tool"
