#!/usr/bin/env bash
# Measurements after the scoring correction (22.11. 10:05, Codex review reviews/codex_amendment_review.md).
# Strictly sequential (one Dream session per key). Each step skips scenes already scored (resume).
#   1. ft-rep-main  finish the replicate, pre-registered protocol (rate 20, vendor gripper check 0.05)
#   2. ft-lr3-main  pre-registered variant, same protocol
#   3. ft-main-g15  EXPLORATORY: main fine-tune, all 40 scenes anew, gripper clipped up to 0.15 outside 0..1
#   4. beta-main2   fresh base measurement (base never triggered the gripper check): base noise floor
#   5. ft-b05-main  pre-registered variant, only if it can start before CUTOFF
# Reports after every step: report_corrected.md (first-attempt scoring), report_g15.md (exploratory).
# No new step starts after CUTOFF. Run from Dream-Orchestra/ (host).
set -uo pipefail
CUTOFF="${CUTOFF:-14:15}"
cd "$(dirname "$0")/../../.."
DIR=src/Simulation/data/evals/cells
log() { echo "$(date '+%H:%M:%S') $*" | tee -a "$DIR/amendment.log"; }
past_cutoff() { [[ $(date +%H%M) > ${CUTOFF/:/} ]]; }
sim() { docker compose run --rm --no-deps -T simulation python "$@" 2>&1 | grep -vE ' Container |UserWarning|reply = policy|policy.get_action'; }
FT=dream-1-ft:317db52a-yam-cells-c500

reports() {
  local labels="expert beta-main ft-main"
  for n in ft-rep-main ft-lr3-main ft-b05-main beta-main2; do [[ -f "$DIR/$n.jsonl" ]] && labels="$labels $n"; done
  sim /app/tools/eval_cells_report.py --out report_corrected.md $labels > /dev/null
  if [[ -f "$DIR/ft-main-g15.jsonl" ]]; then
    local g="expert beta-main"; [[ -f "$DIR/beta-main2.jsonl" ]] && g="$g beta-main2"
    sim /app/tools/eval_cells_report.py --out report_g15.md $g ft-main ft-main-g15 > /dev/null
  fi
  log "reports updated"
}

step() {  # model label grip_tol
  past_cutoff && { log "cutoff $CUTOFF: skipped $2"; return; }
  log "start $2 ($1, grip_tol $3): warm-up"
  [[ "$1" == beta ]] || sim /app/tools/warmup.py "$1" | tee -a "$DIR/amendment.log"  # base is always warm
  sim /app/tools/eval_cells.py --model "$1" --label "$2" --rate 20 --grip-tol "$3" --seeds 0-9 --video 0-1 \
    --max-usd 4 | tee -a "$DIR/amendment.log"
  log "end $2"
  reports
}

step "$FT-rep" ft-rep-main 0.05
step "$FT-lr3" ft-lr3-main 0.05
step "$FT" ft-main-g15 0.15
step beta beta-main2 0.05
step "$FT-b05" ft-b05-main 0.05
log "amendment queue done"
