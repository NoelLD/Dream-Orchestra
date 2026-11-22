#!/usr/bin/env bash
# Last run (22.11. 10:10): yam-cells-c1000 (1000 steps, dose 500 vs 1000), pre-registered protocol (rate 20,
# vendor gripper check 0.05, first-attempt scoring). Waits until after_amendment.sh is done (one Dream session per
# key), then evaluates c1000 if it has finished training. No start after CUTOFF. Run from Dream-Orchestra/ (host).
set -uo pipefail
API="${API:-http://localhost:3001}"
CUTOFF="${CUTOFF:-14:15}"
cd "$(dirname "$0")/../../.."
DIR=src/Simulation/data/evals/cells
log() { echo "$(date '+%H:%M:%S') $*" | tee -a "$DIR/amendment.log"; }
past_cutoff() { [[ $(date +%H%M) > ${CUTOFF/:/} ]]; }
sim() { docker compose run --rm --no-deps -T simulation python "$@" 2>&1 | grep -vE ' Container |UserWarning|reply = policy|policy.get_action'; }

until grep -q "amendment queue done" "$DIR/amendment.log" 2>/dev/null; do
  past_cutoff && { log "c1000: cutoff $CUTOFF while the queue was still running - not evaluated"; exit 1; }
  sleep 120
done
while :; do
  past_cutoff && { log "c1000: cutoff $CUTOFF - not evaluated"; exit 1; }
  read -r STATUS MODEL < <(curl -sS --max-time 60 "$API/finetune" | python3 -c 'import json,sys
m=[j for j in json.load(sys.stdin) if j.get("suffix")=="yam-cells-c1000"]
print(m[-1].get("status"), m[-1].get("fine_tuned_model")) if m else print("missing None")' 2>/dev/null || echo "unknown None")
  [[ "$STATUS" == "succeeded" && "$MODEL" != "None" ]] && break
  [[ "$STATUS" == "failed" || "$STATUS" == "cancelled" || "$STATUS" == "missing" ]] && { log "c1000: $STATUS"; exit 1; }
  log "c1000: $STATUS, waiting"
  sleep 300
done
log "start ft-c1000-main ($MODEL, grip_tol 0.05): warm-up"
sim /app/tools/warmup.py "$MODEL" | tee -a "$DIR/amendment.log"
sim /app/tools/eval_cells.py --model "$MODEL" --label ft-c1000-main --rate 20 --grip-tol 0.05 --seeds 0-9 \
  --video 0-1 --max-usd 4 | tee -a "$DIR/amendment.log"
log "end ft-c1000-main"
labels="expert beta-main ft-main"
for n in ft-rep-main ft-lr3-main ft-b05-main ft-c1000-main beta-main2; do [[ -f "$DIR/$n.jsonl" ]] && labels="$labels $n"; done
sim /app/tools/eval_cells_report.py --out report_corrected.md $labels > /dev/null
log "c1000 done; report_corrected.md updated"
