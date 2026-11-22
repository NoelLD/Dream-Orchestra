#!/usr/bin/env bash
# Transfer test (pre-registered 22.11. 11:40, see data/evals/cells/TRANSFER_PREREG.md): does the cell fine-tune also
# help on a similar task it was never trained on? Task cnc_return = reverse of cnc_load (block from tray to stand).
# Base `beta` vs main fine-tune c500, seeds 0-19, same protocol as the main evaluation. Expert reference: 20/20.
# Waits until final_queue.sh has evaluated ft-rep2-main (or 15:30 has passed) and no Dream eval is running.
# No start after CUTOFF. Run from Dream-Orchestra/ (host):
#   nohup caffeinate -i bash src/Simulation/tools/transfer_test.sh > src/Simulation/data/evals/cells/transfer.nohup 2>&1 &
set -uo pipefail
CUTOFF="${CUTOFF:-16:25}"
cd "$(dirname "$0")/../../.."
DIR=src/Simulation/data/evals/cells
LOG="$DIR/amendment.log"
log() { echo "$(date '+%H:%M:%S') [transfer] $*" | tee -a "$LOG"; }
past() { [[ $(date +%H%M) > ${1/:/} ]]; }
sim() { docker compose run --rm --no-deps -T simulation python "$@" 2>&1 | grep -vE ' Container |UserWarning|reply = policy|policy.get_action'; }
busy() { pgrep -f "eval_cells.py --model" > /dev/null || pgrep -f "warmup.py" > /dev/null; }
FT=dream-1-ft:317db52a-yam-cells-c500

log "waiting: ft-rep2-main evaluated or 15:30, and no Dream eval running"
until { grep -q "end ft-rep2-main" "$LOG" || past 15:30; } && ! busy; do
  past "$CUTOFF" && { log "cutoff $CUTOFF reached: transfer test not run"; exit 0; }
  sleep 60
done
sleep 90; until ! busy; do sleep 60; done  # the queue may be writing reports or starting its next step

run() {  # model label
  past "$CUTOFF" && { log "cutoff $CUTOFF: skipped $2"; return; }
  log "start $2 ($1): warm-up"
  [[ "$1" == beta ]] || sim /app/tools/warmup.py "$1" | tee -a "$LOG"
  sim /app/tools/eval_cells.py --model "$1" --label "$2" --tasks cnc_return --rate 20 --grip-tol 0.05 \
    --seeds 0-19 --video 0-1 --max-usd 2 | tee -a "$LOG"
  log "end $2"
}
run beta xfer-beta
run "$FT" xfer-ft-main
python3 src/Simulation/tools/results_page.py > /dev/null && log "results page regenerated (deploy by hand)"
log "transfer test done"
