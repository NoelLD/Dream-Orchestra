#!/usr/bin/env bash
# Extra fine-tunes (started 22.11. ~04:50), evaluated AFTER the main one (one Dream session per key):
#   ftj_45fce78514effa5b  yam-cells-c500-rep  replicate of the main job (training noise)
#   ftj_f2e771ed46fbaa3d  yam-cells-c500-lr3  learning_rate 3e-5 (500 steps x batch 32 < 1 epoch of 25k frames)
# Pre-registered: no own calibration, the main fine-tune's frozen rate (same data/architecture); same seeds 0-9 x 4
# tasks, videos 0-1. No new evaluation starts after CUTOFF. Run from Dream-Orchestra/ (host).
set -euo pipefail
API="${API:-http://localhost:3001}"
CUTOFF="${CUTOFF:-12:30}"
cd "$(dirname "$0")/../../.."
DIR=src/Simulation/data/evals/cells
log() { echo "$(date '+%H:%M:%S') $*" | tee -a "$DIR/variants.log"; }
past_cutoff() { [[ $(date +%H%M) > ${CUTOFF/:/} ]]; }

until grep -q "after-finetune evaluation done" "$DIR/after.log" 2>/dev/null; do
  past_cutoff && { log "cutoff $CUTOFF before the main evaluation finished: variants not evaluated"; exit 1; }
  sleep 120
done
RATE=$(sed -n 's/.*frozen rate: \([0-9.]*\).*/\1/p' "$DIR/ft.rate")
log "main fine-tune frozen rate: $RATE"

pending="ftj_45fce78514effa5b:ft-rep ftj_f2e771ed46fbaa3d:ft-lr3"
while [[ -n "$pending" ]]; do
  past_cutoff && { log "cutoff $CUTOFF: not evaluated: $pending"; break; }
  next=""
  for item in $pending; do
    job=${item%%:*}; name=${item##*:}
    read -r STATUS MODEL < <(curl -sS --max-time 60 "$API/finetune/$job" | python3 -c 'import json,sys
j=json.load(sys.stdin); print(j.get("status"), j.get("fine_tuned_model"))' 2>/dev/null || echo "unknown None")
    if [[ "$STATUS" == "succeeded" && "$MODEL" != "None" ]]; then
      log "$name ($job) ready: $MODEL - warming, then main seeds at rate $RATE"
      docker compose run --rm --no-deps -T simulation python /app/tools/warmup.py "$MODEL" 2>&1 \
        | grep -v ' Container ' | tee -a "$DIR/variants.log"
      docker compose run --rm --no-deps -T simulation python /app/tools/eval_cells.py --model "$MODEL" \
        --label "$name-main" --rate "$RATE" --seeds 0-9 --video 0-1 --max-usd 4 2>&1 \
        | grep -vE ' Container |UserWarning|reply = policy' | tee -a "$DIR/variants.log"
      pending=${pending/$item/}; pending=$(echo $pending)
      continue 2
    elif [[ "$STATUS" == "failed" ]]; then
      log "$name ($job) failed"; pending=${pending/$item/}; pending=$(echo $pending); continue 2
    fi
    log "$name: $STATUS"
  done
  sleep 300
done
LABELS="expert beta-main ft-main"
for n in ft-rep ft-lr3; do [[ -f "$DIR/$n-main.jsonl" ]] && LABELS="$LABELS $n-main"; done
docker compose run --rm --no-deps -T simulation python /app/tools/eval_cells_report.py $LABELS 2>&1 \
  | grep -v ' Container ' > "$DIR/report_all.md"
log "variants done: $DIR/report_all.md"
