"""Start the pre-registered evaluations of the fine-tune series (FINETUNE_SERIES.md). Costs inference credits.

    python3 src/Simulation/tools/eval_series.py banana          # 5 variants x 20 seeds (~1-2 h, ~3 $)
    python3 src/Simulation/tools/eval_series.py apple           # 4 variants x 10 seeds
    python3 src/Simulation/tools/eval_series.py steps           # R vs R1000 vs base, banana, 10 seeds
    add --dry-run to print the request without sending it;
    --skip ft-A,ft-B leaves out variants whose model was not `ready` after warm-up (tools/warmup.py), stated now.
Checkpoints are resolved from the service's job records by suffix; a missing/unfinished model stops the script.
Every variant gets the TRAINING prompt (record_dataset.py), so base and fine-tunes see the same words.
Runs on the host (stdlib only) against http://localhost:3001.
"""

import json
import sys
import urllib.request

API = "http://localhost:3001"
PROMPTS = {"pick-banana": "pick up the banana and put it back down",
           "pick-apple": "pick up the apple and put it back down"}
BASE = "dreamlabs/dream-1-beta"
PLANS = {
    "banana": ("pick-banana", 20, [("beta-1x", BASE), ("beta-1x-rep", BASE), ("ft-R", "yam-r500"),
                                   ("ft-A", "yam-a500-own"), ("ft-B", "yam-b500-banana")]),
    "apple": ("pick-apple", 10, [("beta-1x", BASE), ("ft-R", "yam-r500"), ("ft-A", "yam-a500-own"),
                                 ("ft-B", "yam-b500-banana")]),
    "steps": ("pick-banana", 10, [("beta-1x", BASE), ("ft-R", "yam-r500"), ("ft-R1000", "yam-r1000")]),
}


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in PLANS:
        print(__doc__)
        return 2
    skill, trials, variants = PLANS[sys.argv[1]]
    skip = set(sys.argv[sys.argv.index("--skip") + 1].split(",")) if "--skip" in sys.argv else set()
    jobs = {j.get("suffix"): j for j in call("GET", "/finetune")}
    # Pre-registered: the reference is the base the fine-tunes start from (job `base_model`), if Dream states it.
    bases = {j.get("base_model") for j in jobs.values() if j.get("base_model")}
    if len(bases) > 1:
        print(f"STOP: the fine-tunes start from different bases {bases}; decide the reference explicitly")
        return 1
    base = bases.pop() if bases else BASE
    if base != BASE:
        print(f"note: reference base switched to the fine-tunes' base_model {base}")
    resolved = []
    for label, ref in variants:
        if label in skip:
            print(f"skipped (not ready after warm-up): {label}")
            continue
        if ref.startswith("dreamlabs/"):
            checkpoint = base
        else:
            job = jobs.get(ref)
            checkpoint = job and job.get("fine_tuned_model")
            if not checkpoint:
                print(f"STOP: {label} ({ref}) has no finished model yet: {job and job.get('status')}")
                return 1
        resolved.append({"label": label, "checkpoint": checkpoint, "prompt": PROMPTS[skill], "max_attempts": 1})
    body = {"skill": skill, "mode": "dream", "trials": trials, "seed_start": 0, "timeout_s": 30, "variants": resolved}
    print(json.dumps(body, indent=2))
    if "--dry-run" in sys.argv:
        return 0
    answer = call("POST", "/evals", body)
    print(json.dumps(answer)[:300])
    print(f"Progress: curl -s {API}/evals/{answer.get('eval_id')} | python3 -m json.tool")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
