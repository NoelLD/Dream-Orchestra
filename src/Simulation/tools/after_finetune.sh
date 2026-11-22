#!/usr/bin/env bash
# Waits for the cell fine-tune to finish, warms the checkpoint, then runs the SAME pre-registered protocol as the base
# (eval_protocol.sh: rate calibration 10/20/30 on seeds 900-901, frozen, main seeds 0-9 x 4 tasks), then the report
# and side-by-side videos. Run from Dream-Orchestra/ (host):  bash src/Simulation/tools/after_finetune.sh
# Costs: inference only (fine-tune 0.0028 $/call): calibration ~1 $, main ~2-3 $; the job itself is already paid.
set -euo pipefail
JOB="${JOB:-ftj_d37039dff2d81d6a}"
API="${API:-http://localhost:3001}"
cd "$(dirname "$0")/../../.."
DIR=src/Simulation/data/evals/cells
log() { echo "$(date '+%H:%M:%S') $*" | tee -a "$DIR/after.log"; }

while :; do
  J=$(curl -sS --max-time 60 "$API/finetune/$JOB" || echo '{}')
  read -r STATUS MODEL STEP < <(echo "$J" | python3 -c 'import json,sys
j=json.load(sys.stdin); p=j.get("progress") or {}
print(j.get("status"), j.get("fine_tuned_model"), p.get("step"))' 2>/dev/null || echo "unknown None None")
  log "job $JOB: $STATUS step $STEP model $MODEL"
  [[ "$STATUS" == "succeeded" && "$MODEL" != "None" ]] && break
  [[ "$STATUS" == "failed" || "$STATUS" == "cancelled" ]] && { log "job $STATUS: $J"; exit 1; }
  sleep 300
done

log "warming $MODEL"
docker compose run --rm --no-deps -T simulation python /app/tools/warmup.py "$MODEL" 2>&1 | grep -v ' Container ' \
  | tee -a "$DIR/after.log"
log "protocol"
bash src/Simulation/tools/eval_protocol.sh "$MODEL" ft "10 20 30" 2>&1 | tee -a "$DIR/after.log"
docker compose run --rm --no-deps -T simulation python /app/tools/eval_cells_report.py expert beta-main ft-main \
  2>&1 | grep -v ' Container ' | tee -a "$DIR/after.log"
for s in 0 1; do for t in sort_round sort_cube cnc_load cnc_unload; do
  python3 src/Simulation/tools/eval_side_by_side.py beta-main ft-main "$t" "$s" >> "$DIR/after.log" 2>&1 || true
done; done
log "after-finetune evaluation done: $DIR/report.md, $DIR/side_by_side/"
