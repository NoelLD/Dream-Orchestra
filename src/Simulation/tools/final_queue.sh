#!/usr/bin/env bash
# Final measurement queue (22.11. 10:30, order after Codex review reviews/codex_final_runs_review.md).
# Replaces after_amendment.sh steps 3-5 and after_c1000.sh. Strictly sequential (one Dream session per API key).
# Waits for the running ft-lr3-main to end first. Martin extended the end to 17:15 -> CUTOFF 16:25 (last start).
#   1. beta-main2     fresh base measurement (noise floor of the base)
#   2. ft-b05-main    pre-registered variant (base_share 0.5)
#   3. fruit-forget   forgetting check outside the cells: pick-banana, seeds 0-19, beta vs ft-main vs ft-b05,
#                     training prompt, fresh base (POST /evals bypasses .dream.lock -> polled to the end);
#                     error seeds must be recounted as failures in the analysis (evals.py drops them)
#   4. ft-rep-g15     EXPLORATORY: replicate (9/10 sort_cube gripper aborts) with gripper clip 0.15
#   5. ft-c1000-main  dose 500 vs 1000, if trained
#   6. ft-rep2-main   third training of the main recipe (training noise), if trained
#   7. ft-v2-main     cells-v2: 320 demos instead of 160, else like c500, if trained
# Jobs not trained when reached are retried once at the end. No new step starts after CUTOFF.
# No new step starts after CUTOFF. Run from Dream-Orchestra/ (host).
set -uo pipefail
API="${API:-http://localhost:3001}"
CUTOFF="${CUTOFF:-16:25}"
cd "$(dirname "$0")/../../.."
DIR=src/Simulation/data/evals/cells
log() { echo "$(date '+%H:%M:%S') [final] $*" | tee -a "$DIR/amendment.log"; }
past_cutoff() { [[ $(date +%H%M) > ${CUTOFF/:/} ]]; }
sim() { docker compose run --rm --no-deps -T simulation python "$@" 2>&1 | grep -vE ' Container |UserWarning|reply = policy|policy.get_action'; }
FT=dream-1-ft:317db52a-yam-cells-c500

reports() {
  local labels="expert beta-main ft-main"
  for n in ft-rep-main ft-lr3-main ft-b05-main ft-c1000-main ft-rep2-main ft-v2-main beta-main2; do [[ -f "$DIR/$n.jsonl" ]] && labels="$labels $n"; done
  sim /app/tools/eval_cells_report.py --out report_corrected.md $labels > /dev/null
  if [[ -f "$DIR/ft-main-g15.jsonl" ]]; then
    local g="expert beta-main"; [[ -f "$DIR/beta-main2.jsonl" ]] && g="$g beta-main2"
    sim /app/tools/eval_cells_report.py --out report_g15.md $g ft-main ft-main-g15 > /dev/null
  fi
  if [[ -f "$DIR/ft-rep-g15.jsonl" ]]; then
    local g="expert beta-main"; [[ -f "$DIR/beta-main2.jsonl" ]] && g="$g beta-main2"
    sim /app/tools/eval_cells_report.py --out report_rep_g15.md $g ft-rep-main ft-rep-g15 > /dev/null
  fi
  log "reports updated"
}

step() {  # model label grip_tol
  past_cutoff && { log "cutoff $CUTOFF: skipped $2"; return; }
  log "start $2 ($1, grip_tol $3): warm-up"
  [[ "$1" == beta ]] || sim /app/tools/warmup.py "$1" | tee -a "$DIR/amendment.log"
  sim /app/tools/eval_cells.py --model "$1" --label "$2" --rate 20 --grip-tol "$3" --seeds 0-9 --video 0-1 \
    --max-usd 4 | tee -a "$DIR/amendment.log"
  log "end $2"
  reports
}

job_model() {  # suffix -> prints the checkpoint if the job succeeded, else nothing
  curl -sS --max-time 60 "$API/finetune" | python3 -c 'import json,sys
m=[j for j in json.load(sys.stdin) if j.get("suffix")==sys.argv[1]]
print(m[-1]["fine_tuned_model"]) if m and m[-1].get("status")=="succeeded" and m[-1].get("fine_tuned_model") else None' "$1" 2>/dev/null
}
LATER=()
job_step() {  # suffix label
  local m; m=$(job_model "$1")
  if [[ -n "$m" ]]; then step "$m" "$2" 0.05; else log "$1 not trained yet: retry at the end"; LATER+=("$1 $2"); fi
}

fruit() {
  past_cutoff && { log "cutoff $CUTOFF: skipped fruit-forget"; return; }
  log "start fruit-forget (pick-banana, seeds 0-19, beta / ft-main / ft-b05): warm-up"
  sim /app/tools/warmup.py "$FT" "$FT-b05" | tee -a "$DIR/amendment.log"
  local body id status
  body=$(python3 -c 'import json
p="pick up the banana and put it back down"; ft="'"$FT"'"
v=[("beta","dreamlabs/dream-1-beta"),("ft-main",ft),("ft-b05",ft+"-b05")]
print(json.dumps({"skill":"pick-banana","mode":"dream","trials":20,"seed_start":0,"timeout_s":30,
 "variants":[{"label":l,"checkpoint":c,"prompt":p,"max_attempts":1} for l,c in v]}))')
  id=$(curl -sS --max-time 60 -X POST "$API/evals" -H 'content-type: application/json' -d "$body" \
    | python3 -c 'import json,sys;print(json.load(sys.stdin).get("eval_id",""))')
  [[ -n "$id" ]] || { log "fruit-forget: POST /evals failed"; return; }
  log "fruit-forget: eval $id"
  while :; do
    sleep 60
    status=$(curl -sS --max-time 60 "$API/evals/$id" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("status"))' 2>/dev/null)
    [[ "$status" == queued || "$status" == running ]] || break
  done
  curl -sS --max-time 60 "$API/evals/$id" > "$DIR/fruit-forget.json"
  log "end fruit-forget ($status) -> fruit-forget.json"
}

until ! pgrep -f "eval_cells.py.*--label ft-lr3-main" > /dev/null; do sleep 60; done
log "ft-lr3-main ended"
reports

step beta beta-main2 0.05
step "$FT-b05" ft-b05-main 0.05
fruit
step "$FT-rep" ft-rep-g15 0.15
job_step yam-cells-c1000 ft-c1000-main
job_step yam-cells-c500-rep2 ft-rep2-main
job_step yam-cells-v2-c500 ft-v2-main
for item in "${LATER[@]+"${LATER[@]}"}"; do
  read -r suf lab <<< "$item"
  until [[ -n "$(job_model "$suf")" ]] || past_cutoff; do sleep 300; done
  [[ -n "$(job_model "$suf")" ]] && step "$(job_model "$suf")" "$lab" 0.05 || log "$suf not trained by cutoff: not evaluated"
done
log "final queue done"
