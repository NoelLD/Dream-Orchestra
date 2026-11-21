#!/bin/sh
# Queue the fine-tune series R, A, B (FINETUNE_SERIES.md). COSTS 300 $ (3 x 500 steps x 0.20 $), not cancellable.
# Run by a person, on purpose:   sh src/Simulation/tools/start_finetune_series.sh --yes
# R1000 later (optional, after R is finished):  ... --resume dream-1-ft:<uid8>-yam-r500
# Stops at the first refusal; every answer is appended to src/Simulation/data/finetune_series.jsonl.
# Never re-run blindly after an unclear failure: check `curl -s localhost:3001/finetune` first (a job may exist).
set -eu
API=${SIM_API:-http://localhost:3001}
LOG=${SERIES_LOG:-src/Simulation/data/finetune_series.jsonl}

post() {  # $1 = cell label, $2 = JSON body; stops the script unless the service answers 202 with a job_id
  echo ">>> $1: POST /finetune $2"
  body=$(curl -sS -o /dev/stdout -w '\n%{http_code}' -X POST "$API/finetune" -H 'content-type: application/json' -d "$2")
  code=$(printf '%s' "$body" | tail -n 1)
  answer=$(printf '%s' "$body" | sed '$d')
  printf '{"cell":"%s","http":%s,"at":"%s","answer":%s}\n' "$1" "$code" "$(date -u +%FT%TZ)" "${answer:-null}" >> "$LOG"
  echo "<<< HTTP $code $answer"
  if [ "$code" != "202" ] || ! printf '%s' "$answer" | grep -q '"job_id":"ft'; then
    echo "STOP: $1 was not queued (HTTP $code). Nothing after it was sent." >&2
    exit 1
  fi
}

case "${1:-}" in
  --yes)
    post R '{"robot":"yam-sim","dataset":"pick-both-v2","suffix":"yam-r500","steps":500,"lr_schedule":"constant","base_share":0.5,"confirm_cost_usd":100}'
    post A '{"robot":"yam-sim","dataset":"pick-both-v2","suffix":"yam-a500-own","steps":500,"lr_schedule":"constant","base_share":0.0,"confirm_cost_usd":100}'
    post B '{"robot":"yam-sim","dataset":"pick-banana-v2","suffix":"yam-b500-banana","steps":500,"lr_schedule":"constant","base_share":0.5,"confirm_cost_usd":100}'
    ;;
  --resume)
    model=${2:?usage: --resume dream-1-ft:<uid8>-yam-r500}
    post R1000 "{\"robot\":\"yam-sim\",\"dataset\":\"pick-both-v2\",\"suffix\":\"yam-r1000\",\"steps\":500,\"lr_schedule\":\"constant\",\"resume_from\":\"$model\",\"confirm_cost_usd\":100}"
    ;;
  *)
    echo "Costs money. Read src/Simulation/FINETUNE_SERIES.md, then run with --yes (300 \$) or --resume <model> (100 \$)."
    exit 2
    ;;
esac
echo "Queued. Status (refreshes from Dream):  curl -s $API/finetune | python3 -m json.tool"
