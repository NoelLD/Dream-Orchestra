#!/usr/bin/env bash
# Second batch of fine-tunes (started 22.11. ~05:20, deadline moved to 17:45), evaluated AFTER after_variants.sh
# (one Dream session per key). Jobs are found by suffix, so this can start before the curls are sent:
#   yam-cells-c1000    1000 steps, cosine, base_share 0.0  -> dose (500 vs 1000)
#   yam-cells-c500-b05  500 steps, cosine, base_share 0.5  -> mixing in Dream's own data
# Pre-registered like the variants: no own calibration, the main fine-tune's frozen rate; seeds 0-9 x 4 tasks,
# videos 0-1. No new evaluation starts after CUTOFF. Run from Dream-Orchestra/ (host).
set -euo pipefail
API="${API:-http://localhost:3001}"
CUTOFF="${CUTOFF:-15:00}"
cd "$(dirname "$0")/../../.."
DIR=src/Simulation/data/evals/cells
log() { echo "$(date '+%H:%M:%S') $*" | tee -a "$DIR/variants2.log"; }
past_cutoff() { [[ $(date +%H%M) > ${CUTOFF/:/} ]]; }

until grep -qE "variants done|cutoff" "$DIR/variants.log" 2>/dev/null; do
  past_cutoff && { log "cutoff $CUTOFF before the first variants finished: not evaluated"; exit 1; }
  sleep 120
done
RATE=$(sed -n 's/.*frozen rate: \([0-9.]*\).*/\1/p' "$DIR/ft.rate")
[[ -n "$RATE" ]] || { log "no frozen rate in $DIR/ft.rate"; exit 1; }
log "main fine-tune frozen rate: $RATE"

lookup() {  # suffix -> "status model" (newest job with that suffix)
  curl -sS --max-time 60 "$API/finetune" | python3 -c 'import json,sys
d=json.load(sys.stdin); jobs=d if isinstance(d,list) else d.get("jobs",[d])
m=[j for j in jobs if j.get("suffix")==sys.argv[1]]
print((m[-1].get("status"), m[-1].get("fine_tuned_model")) if m else ("missing", None))' "$1" \
  | tr -d "()',"  2>/dev/null || echo "unknown None"
}

pending="yam-cells-c500-b05:ft-b05 yam-cells-c1000:ft-c1000"
# after_variants.sh stops at 12:30 (old deadline); catch up on whatever it skipped
for item in yam-cells-c500-rep:ft-rep yam-cells-c500-lr3:ft-lr3; do
  [[ -f "$DIR/${item##*:}-main.jsonl" ]] || { pending="$pending $item"; log "catching up ${item##*:} (skipped by after_variants.sh)"; }
done
while [[ -n "$pending" ]]; do
  past_cutoff && { log "cutoff $CUTOFF: not evaluated: $pending"; break; }
  for item in $pending; do
    suffix=${item%%:*}; name=${item##*:}
    read -r STATUS MODEL < <(lookup "$suffix")
    if [[ "$STATUS" == "succeeded" && "$MODEL" != "None" ]]; then
      log "$name ($suffix) ready: $MODEL - warming, then main seeds at rate $RATE"
      docker compose run --rm --no-deps -T simulation python /app/tools/warmup.py "$MODEL" 2>&1 \
        | grep -v ' Container ' | tee -a "$DIR/variants2.log"
      docker compose run --rm --no-deps -T simulation python /app/tools/eval_cells.py --model "$MODEL" \
        --label "$name-main" --rate "$RATE" --seeds 0-9 --video 0-1 --max-usd 4 2>&1 \
        | grep -vE ' Container |UserWarning|reply = policy' | tee -a "$DIR/variants2.log"
      pending=${pending/$item/}; pending=$(echo $pending)
      continue 2
    elif [[ "$STATUS" == "failed" || "$STATUS" == "cancelled" ]]; then
      log "$name ($suffix) $STATUS"; pending=${pending/$item/}; pending=$(echo $pending); continue 2
    fi
    log "$name: $STATUS"
  done
  sleep 300
done
LABELS="expert beta-main ft-main"
for n in ft-rep ft-lr3 ft-b05 ft-c1000; do [[ -f "$DIR/$n-main.jsonl" ]] && LABELS="$LABELS $n-main"; done
docker compose run --rm --no-deps -T simulation python /app/tools/eval_cells_report.py $LABELS 2>&1 \
  | grep -v ' Container ' > "$DIR/report_all2.md"
log "variants2 done: $DIR/report_all2.md"
