#!/usr/bin/env bash
# Pre-registered evaluation protocol (22.11. 04:35, after Codex eval review). Same for base and fine-tune:
#   1. rate calibration on separate seeds 900-901 (all 4 tasks) at each candidate rate;
#      pick the rate with most successes, ties -> more collision-free successes -> 20 (runner default); then FROZEN
#   2. main measurement: seeds 0-9 x 4 tasks at the frozen rate, videos for seeds 0-1
# Strictly sequential: one Dream session per API key (parallel runs replaced each other's sessions in the pilot).
# Run from Dream-Orchestra/:
#   bash src/Simulation/tools/eval_protocol.sh beta beta "20 30"
#   bash src/Simulation/tools/eval_protocol.sh dream-1-ft:<id> ft "10 20 30"
set -euo pipefail
MODEL="$1"; NAME="$2"; RATES="${3:-20 30}"
cd "$(dirname "$0")/../../.."
DIR=src/Simulation/data/evals/cells
ev() { docker compose run --rm --no-deps -T simulation python /app/tools/eval_cells.py "$@" 2>&1 | grep -vE ' Container |UserWarning|reply = policy'; }

echo "== $NAME calibration on seeds 900-901, rates: $RATES"
for r in $RATES; do
  ev --model "$MODEL" --label "calib-$NAME-r$r" --rate "$r" --seeds 900-901 --max-usd 1
done
BEST=$(python3 - "$DIR" "$NAME" $RATES <<'EOF'
import json, sys
d, name, rates = sys.argv[1], sys.argv[2], sys.argv[3:]
def score(r):
    rows = [json.loads(x) for x in open(f"{d}/calib-{name}-r{r}.jsonl") if x.strip()]
    act = lambda x: x["outcome"] == "action_error" or "No rows executed" in (x.get("error") or "")
    first = {}
    for x in rows:  # first attempt per scene; an action error is a failure (corrected 22.11., Grok review)
        if (x["task"], x["seed"]) not in first and (x["outcome"] != "error" or act(x)):
            first[(x["task"], x["seed"])] = x | ({"success": False, "clean_success": False} if act(x) else {})
    rows = list(first.values())
    return (sum(x["success"] for x in rows), sum(x["clean_success"] for x in rows), r == "20")
for r in rates:
    print(f"rate {r}: successes, clean, default = {score(r)}", file=sys.stderr)
print(max(rates, key=score))
EOF
)
echo "== $NAME frozen rate: $BEST" | tee "$DIR/$NAME.rate"
ev --model "$MODEL" --label "$NAME-main" --rate "$BEST" --seeds 0-9 --video 0-1 --max-usd 4
echo "== $NAME done"
