#!/usr/bin/env python3
"""Team overview page of the cell fine-tune results (host, no Docker, no network).

Reads data/evals/cells/<label>.jsonl with the same first-attempt scoring as eval_cells_report.py
(first non-infrastructure attempt per scene; an action error counts as a failure), and writes one
self-contained HTML file with embedded fonts. Re-run after every queue step:
    python3 src/Simulation/tools/results_page.py [out.html]
"""
from __future__ import annotations

import base64
import html
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

SIM = Path(__file__).resolve().parents[1]
CELLS = SIM / "data/evals/cells"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else SIM.parents[2] / "results_overview.html"
FONTS = Path.home() / "claude-projects/products/marty-skills/skills/public/martin-uix/assets/fonts"
TASKS = ["sort_round", "sort_cube", "cnc_load", "cnc_unload"]
TASK_NAMES = {"sort_round": "Sort round part", "sort_cube": "Sort cube", "cnc_load": "Load CNC",
              "cnc_unload": "Unload CNC"}
BASE = "beta-main"
# label -> (name, what it tests, pre-registered?)
MODELS = {
    "expert": ("Scripted expert", "reference that produced the training demos", True),
    "beta-main": ("Dream-1 beta (base)", "no fine-tune", True),
    "beta-main2": ("Base, second run", "noise floor of the base", True),
    "ft-main": ("Fine-tune c500", "160 cell demos, 500 steps", True),
    "ft-rep-main": ("Fine-tune c500, replicate", "identical training, training noise", True),
    "ft-rep2-main": ("Fine-tune c500, 3rd training", "training noise", True),
    "ft-lr3-main": ("Fine-tune, lr 3e-5", "learning rate 3x", True),
    "ft-b05-main": ("Fine-tune, 50 % base data", "mix in Dream's own data", True),
    "ft-c1000-main": ("Fine-tune c1000", "dose: 1000 steps", True),
    "ft-v2-main": ("Fine-tune, 320 demos", "more data (cells-v2)", True),
    "ft-rep-g15": ("Replicate, gripper clip 0.15", "exploratory: cost of gripper aborts", False),
}
QUEUE = [("ft-lr3-main", "~10:40"), ("beta-main2", "~11:25"), ("ft-b05-main", "~12:10"),
         ("fruit-forget", "~13:10"), ("ft-rep-g15", "~13:55"), ("ft-c1000-main", "~14:40"),
         ("ft-rep2-main", "~15:25"), ("ft-v2-main", "~16:10")]


def is_action_error(r: dict) -> bool:
    e = r.get("error") or ""
    return r["outcome"] == "action_error" or (r["outcome"] == "error" and "No rows executed" in e)


def load(label: str) -> dict | None:
    p = CELLS / f"{label}.jsonl"
    if not p.exists():
        return None
    scored: dict = {}
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        key = (r["task"], r["seed"])
        if key in scored or (r["outcome"] == "error" and not is_action_error(r)):
            continue
        if is_action_error(r):
            r = r | {"success": False, "clean_success": False, "outcome": "action_error"}
        scored[key] = r
    return scored


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def bucket(r: dict) -> str:
    o = r["outcome"]
    if r["success"]:
        return "success"
    if o == "action_error":
        return "action_error"
    if "dropped" in o:
        return "dropped"
    if "not_released" in o:
        return "not_released"
    return "no_grasp"


def spending() -> dict:
    """Training jobs live from the local API (steps x 0.20 $), eval tariff estimates summed from every jsonl line."""
    jobs = []
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:3001/finetune", timeout=30) as f:
            for j in json.load(f):
                if str(j.get("suffix", "")).startswith("yam-cells"):
                    jobs.append({"name": j["suffix"], "status": j.get("status"), "usd": round(j.get("steps", 0) * 0.20, 2)})
    except Exception:
        pass
    chain = SIM / "data/datasets/cells-v2.chain.log"
    if not any(j["name"].startswith("yam-cells-v2") for j in jobs):
        jobs.append({"name": "yam-cells-v2-c500", "status": "not submitted yet (chain still checking data)", "usd": 0.0,
                     "pending": 100.0 if chain.exists() else 0.0})
    evals = {}
    for f in sorted(CELLS.glob("*.jsonl")):
        tot = sum((json.loads(x).get("cost_usd") or 0) for x in f.read_text().splitlines() if x.strip())
        if tot:
            evals[f.stem] = round(tot, 3)
    return {"jobs": jobs, "evals": evals, "credit": 1000.0, "dev": claude_dev_cost()}


# Claude Code session logs of this project (local only). API list prices per 1M tokens (claude-api skill, 2026-11):
# input, output, cache read; cache writes 1.25x input (5 min) or 2x input (1 h).
CLAUDE_LOGS = Path.home() / ".claude/projects/-Users-marty-claude-projects-hackathons-2026-robotix-dreamlabs-hack"
CLAUDE_PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20), "claude-sonnet-5-5": (2.0, 10.0, 0.10), "claude-haiku-5-5": (0.10, 0.50, 0.01)}
DEV_PHASES = [("2026-11-21T14:27", "Idea, research, team name"),  # UTC boundaries (= 15:27 / 03:47 CET)
              ("2026-11-22T01:47", "Simulation, cells, scripted expert, API"),
              ("9999", "Fine-tune data, training gates, evaluation, pages, integration")]


def claude_dev_cost() -> dict:
    """List-price equivalent of the Claude Code work, deduplicated per API response, split into phases."""
    seen, phases, calls, tokens = set(), {name: 0.0 for _, name in DEV_PHASES}, 0, {"out": 0, "cache_read": 0}
    for f in CLAUDE_LOGS.glob("**/*.jsonl"):
        for line in f.open(errors="ignore"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            m = d.get("message") or {}
            u, mid = m.get("usage"), m.get("id")
            if not u or not mid or (mid, d.get("requestId")) in seen or m.get("model") not in CLAUDE_PRICES:
                continue
            seen.add((mid, d.get("requestId")))
            i, o, cr = CLAUDE_PRICES[m["model"]]
            cc = u.get("cache_creation") or {}
            w1h = cc.get("ephemeral_1h_input_tokens", 0)
            w5 = cc.get("ephemeral_5m_input_tokens", 0) if cc else u.get("cache_creation_input_tokens", 0)
            usd = (u.get("input_tokens", 0) * i + u.get("output_tokens", 0) * o + u.get("cache_read_input_tokens", 0) * cr
                   + w5 * i * 1.25 + w1h * i * 2) / 1e6
            ts = d.get("timestamp", "")
            phases[next(name for end, name in DEV_PHASES if ts < end)] += usd
            calls += 1
            tokens["out"] += u.get("output_tokens", 0)
            tokens["cache_read"] += u.get("cache_read_input_tokens", 0)
    return {"calls": calls, "phases": {k: round(v, 2) for k, v in phases.items()}, "usd": round(sum(phases.values()), 2),
            "out_m": round(tokens["out"] / 1e6, 2), "cache_read_m": round(tokens["cache_read"] / 1e6, 1)}


SBS = CELLS / "side_by_side"
FRAMES = [  # (video, seconds, crop to left panel?, caption)
    ("sort_round-1", 0.3, True, "Conveyor cell: round parts go into the green box (right arm), cubes into the blue box (left arm)."),
    ("cnc_unload-1", 0.3, True, "CNC cell: load a blank onto the machine tray (left arm), take the finished part to the green tray (right arm)."),
    ("cnc_unload-1", 9, False, "9 s: both versions have picked up the finished part."),
    ("cnc_unload-1", 14, False, "14 s: the fine-tune is already over the green tray; the base is still at the machine."),
    ("cnc_unload-1", 22.9, False, "End: the base dropped the part beside the tray (fail). The fine-tune set it down in the tray, no contact (success)."),
]


def media() -> dict:
    """Stills cut from the side-by-side videos with ffmpeg, plus the video itself, all as data URIs."""
    import subprocess, tempfile
    out = {"frames": [], "video": ""}
    for name, t, crop, cap in FRAMES:
        src = SBS / f"{name}.mp4"
        if not src.exists():
            continue
        with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
            vf = ["-vf", "crop=640:298:0:62"] if crop else ["-vf", "crop=1280:298:0:62"]
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(src), *vf, "-frames:v", "1",
                            "-q:v", "4", f.name], check=True)
            out["frames"].append({"src": "data:image/jpeg;base64," + base64.b64encode(Path(f.name).read_bytes()).decode(),
                                  "cap": cap, "wide": not crop})
    v = SBS / "cnc_unload-1.mp4"
    if v.exists():
        out["video"] = "data:video/mp4;base64," + base64.b64encode(v.read_bytes()).decode()
    return out


APP = CELLS / "app_shots"


def app_shot(name: str) -> str:
    f = APP / f"{name}.jpg"
    return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode() if f.exists() else ""


def font(name: str) -> str:
    return base64.b64encode((FONTS / name).read_bytes()).decode()


def main() -> int:
    data = {}
    for label in MODELS:
        s = load(label)
        if s and len(s) >= 40:
            data[label] = s
    running = [lab for lab in MODELS if lab not in data and (CELLS / f"{lab}.jsonl").exists()]
    base = data[BASE]
    models = []
    for label, s in data.items():
        name, what, prereg = MODELS[label]
        k = sum(r["success"] for r in s.values())
        lo, hi = wilson(k, 40)
        m = {"label": label, "name": name, "what": what, "prereg": prereg, "k": k, "lo": lo, "hi": hi,
             "contact": sum(r["contact_steps"] > 0 for r in s.values()),
             "buckets": {b: sum(bucket(r) == b for r in s.values())
                         for b in ["success", "dropped", "not_released", "no_grasp", "action_error"]},
             "tasks": {t: sum(s[(t, i)]["success"] for i in range(10)) for t in TASKS},
             "scenes": [[bucket(s[(t, i)]), s[(t, i)]["contact_steps"] > 0, s[(t, i)]["outcome"]]
                        for t in TASKS for i in range(10)]}
        times = sorted(r["done_s"] for r in s.values() if r["success"] and r.get("done_s") is not None)
        m |= {"times": [round(x, 1) for x in times],
              "t_median": round(times[len(times) // 2] if len(times) % 2 else (times[len(times) // 2 - 1] + times[len(times) // 2]) / 2, 1) if times else None,
              "within20": sum(x <= 20 for x in times), "within30": sum(x <= 30 for x in times)}
        if label not in ("expert", BASE):
            both = [(base[key]["done_s"], s[key]["done_s"]) for key in base
                    if base[key]["success"] and s[key]["success"] and base[key].get("done_s") and s[key].get("done_s")]
            m["both"] = len(both)
            m["both_faster"] = sum(b < a for a, b in both)
        if label not in ("expert", BASE):
            win = sum(not base[key]["success"] and s[key]["success"] for key in base)
            loss = sum(base[key]["success"] and not s[key]["success"] for key in base)
            m |= {"win": win, "loss": loss, "p": mcnemar(win, loss)}
        models.append(m)

    log = (CELLS / "amendment.log").read_text().splitlines()
    final = [x for x in log if "[final]" in x][-6:]
    fruit = CELLS / "fruit-forget.json"
    now = datetime.now().strftime("%H:%M")
    spend = spending()
    summary = {"generated_at": datetime.now().isoformat(timespec="seconds"), "base": BASE, "tasks": TASKS,
               "task_names": TASK_NAMES, "models": models, "spend": spend,
               "queue": [{"label": lab, "name": MODELS[lab][0] if lab in MODELS else "Forgetting check (banana)",
                          "eta": eta, "done": lab in data or (lab == "fruit-forget" and fruit.exists())}
                         for lab, eta in QUEUE],
               "public_url": "https://cell-finetune-results.martinkaiser-bln.workers.dev"}  # same Worker, reframed as Orchestrator page
    (CELLS / "results.json").write_text(json.dumps(summary, indent=1))
    payload = json.dumps({"spend": spend, "models": models, "tasks": TASKS, "taskNames": TASK_NAMES}).replace("</", "<\\/")

    rows = []
    for lab, eta in QUEUE:
        done = lab in data or (lab == "fruit-forget" and fruit.exists())
        state = "done" if done else ("running" if lab in running or (lab == "fruit-forget" and any(
            "start fruit-forget" in x for x in final)) else "queued")
        nm = MODELS[lab][0] if lab in MODELS else "Forgetting check (banana, outside the cells)"
        rows.append(f'<li class="q-{state}"><span class="q-state">{state}</span>'
                    f'<span class="q-name">{html.escape(nm)}</span><span class="q-eta num">{eta if state != "done" else ""}</span></li>')

    md = media()
    cells_fig = "".join(f'<figure><img src="{f["src"]}" alt="{html.escape(f["cap"])}" loading="lazy"><figcaption>{html.escape(f["cap"])}</figcaption></figure>'
                        for f in md["frames"] if not f["wide"])
    seq_fig = "".join(f'<figure class="wide"><img src="{f["src"]}" alt="{html.escape(f["cap"])}" loading="lazy"><figcaption>{html.escape(f["cap"])}</figcaption></figure>'
                      for f in md["frames"] if f["wide"])
    poster = next((f["src"] for f in reversed(md["frames"]) if f["wide"]), "")
    video = (f'<video controls playsinline preload="metadata" poster="{poster}" src="{md["video"]}"></video>' if md["video"] else "")
    page = TEMPLATE.replace("{{SHOT_EDITOR}}", app_shot("editor")).replace("{{SHOT_CELLS}}", app_shot("cells")).replace("{{SHOT_DEVICES}}", app_shot("devices"))
    page = page.replace("{{CELLS_FIG}}", cells_fig).replace("{{SEQ_FIG}}", seq_fig).replace("{{VIDEO}}", video)
    for key, val in {
        "{{NOW}}": now, "{{DATA}}": payload, "{{QUEUE}}": "\n".join(rows),
        "{{LOG}}": html.escape("\n".join(re.sub(r"^(\S+) \[final\] ", r"\1  ", x) for x in final) or "queue waiting for lr3"),
        "{{F_PS4}}": font("public-sans-400.woff2"), "{{F_PS6}}": font("public-sans-600.woff2"),
        "{{F_MONO}}": font("plex-mono-400.woff2"),
    }.items():
        page = page.replace(key, val)
    OUT.write_text(page)
    print(OUT)
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dream Orchestrator</title>
<style>
@font-face{font-family:"Public Sans";src:url(data:font/woff2;base64,{{F_PS4}}) format("woff2");font-weight:400;font-display:swap}
@font-face{font-family:"Public Sans";src:url(data:font/woff2;base64,{{F_PS6}}) format("woff2");font-weight:600;font-display:swap}
@font-face{font-family:"Plex Mono";src:url(data:font/woff2;base64,{{F_MONO}}) format("woff2");font-weight:400;font-display:swap}
:root{
  --plane:#f2f1ed;--surface:#fcfcfb;--sunk:#e7e5df;--ink:#16181b;--ink-2:#4e5157;--ink-3:#6c6f75;
  --success:#2a78d6;--dropped:#eb6834;--not-released:#6250d6;--action:#eda100;--empty:#dcdad3;
  --accent:#1c5cab;--tint:#e3ecf8;--warn-tint:#f6ecd6;color-scheme:light
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --plane:#121314;--surface:#1a1a19;--sunk:#262624;--ink:#f0efec;--ink-2:#c3c2b7;--ink-3:#9c9b93;
  --success:#3987e5;--dropped:#d95926;--not-released:#9085e9;--action:#c98500;--empty:#383835;
  --accent:#86b6ef;--tint:#1d2a3b;--warn-tint:#33291a;color-scheme:dark}}
:root[data-theme="dark"]{
  --plane:#121314;--surface:#1a1a19;--sunk:#262624;--ink:#f0efec;--ink-2:#c3c2b7;--ink-3:#9c9b93;
  --success:#3987e5;--dropped:#d95926;--not-released:#9085e9;--action:#c98500;--empty:#383835;
  --accent:#86b6ef;--tint:#1d2a3b;--warn-tint:#33291a;color-scheme:dark}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--plane);color:var(--ink);font:400 16.5px/1.55 "Public Sans",sans-serif;
  font-variant-numeric:tabular-nums}
::selection{background:var(--tint);color:var(--ink)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:3px}
a{color:var(--accent);text-underline-offset:3px}
.num,code,pre{font-family:"Plex Mono",monospace;font-size:.9em}
main{max-width:1080px;margin:0 auto;padding:48px 16px 80px}
h1{font-weight:600;font-size:2.4rem;line-height:1.1;letter-spacing:-.02em;margin:0 0 12px;text-wrap:balance}
h2{font-weight:600;font-size:1.35rem;margin:64px 0 8px;text-wrap:balance}
p{margin:0 0 12px;max-width:70ch}
.sub{color:var(--ink-2);margin-bottom:28px}
.lead{font-size:1.2rem;line-height:1.5;max-width:62ch}
.lead strong{font-weight:600}
.note{background:var(--tint);padding:14px 18px;border-radius:4px;max-width:78ch;margin:20px 0}
.note.warn{background:var(--warn-tint)}
.note b{font-weight:600}
.muted{color:var(--ink-3)}
/* summary table */
.tbl-wrap{overflow-x:auto;margin:16px -16px 0;padding:0 16px}
table{border-collapse:collapse;width:100%;min-width:720px}
th{font-weight:600;text-align:left;font-size:.85rem;color:var(--ink-2);padding:8px 12px 8px 0;vertical-align:bottom}
td{padding:12px 12px 12px 0;vertical-align:middle;border-top:1px solid var(--sunk)}
td.r,th.r{text-align:right}
.mname{font-weight:600}
.mwhat{color:var(--ink-3);font-size:.88rem}
.tag{font-size:.78rem;background:var(--warn-tint);padding:1px 6px;border-radius:3px;margin-left:6px;white-space:nowrap}
.ci{position:relative;height:18px;width:220px;background:var(--sunk);border-radius:3px}
.ci .band{position:absolute;top:6px;height:6px;background:color-mix(in srgb,var(--success) 35%,transparent);border-radius:3px}
.ci .pt{position:absolute;top:2px;width:4px;height:14px;margin-left:-2px;background:var(--success);border-radius:2px}
.ci .basept{position:absolute;top:0;width:2px;height:18px;margin-left:-1px;background:var(--ink-3);opacity:.6}
.pv{white-space:nowrap}
.sig{font-weight:600}
/* scene grid */
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:14px 0 18px;font-size:.88rem;color:var(--ink-2)}
.legend span{display:inline-flex;align-items:center;gap:7px}
.sw{width:14px;height:14px;border-radius:3px;display:inline-block}
.controls{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 0}
.controls button{font:inherit;font-size:.9rem;padding:10px 14px;min-height:44px;border-radius:4px;border:0;
  background:var(--sunk);color:var(--ink);cursor:pointer}
.controls button[aria-pressed="true"]{background:var(--ink);color:var(--plane)}
.grid{display:grid;grid-template-columns:minmax(150px,210px) 1fr;gap:6px 14px;align-items:center;margin-top:12px}
.ghead{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;font-size:.8rem;color:var(--ink-2)}
.gname{font-size:.9rem;line-height:1.25}
.gname small{display:block;color:var(--ink-3);font-size:.78rem}
.cells{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.task{display:grid;grid-template-columns:repeat(10,1fr);gap:2px}
.c{aspect-ratio:1;border-radius:3px;background:var(--empty);position:relative;cursor:default}
.c.success{background:var(--success)}
.c.dropped{background:var(--dropped)}
.c.not_released{background:var(--not-released)}
.c.action_error{background:repeating-linear-gradient(45deg,var(--action) 0 3px,color-mix(in srgb,var(--action) 45%,var(--surface)) 3px 6px)}
.c.contact::after{content:"";position:absolute;right:2px;top:2px;width:4px;height:4px;border-radius:50%;background:var(--ink)}
.c.dim{opacity:.18}
.c.gain{box-shadow:0 0 0 2px var(--surface),0 0 0 4px var(--success)}
.c.lost{box-shadow:0 0 0 2px var(--surface),0 0 0 4px var(--dropped)}
.tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--plane);font-size:.82rem;padding:6px 9px;border-radius:4px;
  transform:translate(-50%,-120%);white-space:nowrap;opacity:0;transition:opacity .12s}
/* outcome bars */
.bars{display:grid;grid-template-columns:minmax(150px,210px) 1fr 48px;gap:8px 14px;align-items:center;margin-top:12px}
.bar{display:flex;height:22px;gap:2px}
.bar i{display:block;height:100%}
.bar i:first-child{border-radius:4px 0 0 4px}.bar i:last-child{border-radius:0 4px 4px 0}
/* task table */
.task-tbl td,.task-tbl th{text-align:right}
.task-tbl td:first-child,.task-tbl th:first-child{text-align:left}
.dots{display:inline-flex;gap:2px;margin-left:8px;vertical-align:middle}
.dots i{width:6px;height:12px;border-radius:2px;background:var(--empty)}
.dots i.on{background:var(--success)}
/* claims */
.claims{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:12px}
.claims h3{font-size:1rem;font-weight:600;margin:0 0 8px}
.claims ul{margin:0;padding-left:20px}.claims li{margin-bottom:8px;max-width:60ch}
/* orchestrator */
.flow{max-width:80ch;padding-left:22px;margin:12px 0 24px}
.flow li{margin-bottom:10px;padding-left:4px}
.flow li::marker{font-weight:600;color:var(--accent)}
.flow b{font-weight:600}
figure.shot img{border-radius:6px;box-shadow:0 2px 10px rgba(0,0,0,.12)}
h2.part{font-size:1.75rem;margin-top:88px;padding-top:28px;border-top:2px solid var(--sunk)}
/* time chart */
.chart{position:relative;max-width:820px;margin-top:16px}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.chart .grid line{stroke:var(--sunk)}
.chart .axis text{fill:var(--ink-3);font-size:11px;font-family:"Public Sans",sans-serif}
.chart .lbl{font-size:12px;font-family:"Public Sans",sans-serif;fill:var(--ink-2)}
.chart .ft{stroke:var(--success);stroke-width:1.6;fill:none;opacity:.6}
.chart .ft.hot{opacity:1;stroke-width:2.6}
.chart .base{stroke:var(--ink-2);stroke-width:2.6;fill:none}
.chart .expert{stroke:var(--ink-3);stroke-width:1.6;fill:none;stroke-dasharray:5 4}
.chart .cross{stroke:var(--ink-3);stroke-width:1;opacity:0}
.chart svg:hover .cross{opacity:1}
.ctip{position:absolute;top:0;pointer-events:none;background:var(--ink);color:var(--plane);font-size:.8rem;padding:6px 9px;border-radius:4px;white-space:nowrap;opacity:0}
.ctip div{display:flex;justify-content:space-between;gap:14px}
/* figures */
.figs{display:grid;gap:16px;margin:16px 0}
.figs.two{grid-template-columns:1fr 1fr}
figure{margin:0}
figure img,video{display:block;width:100%;height:auto;border-radius:4px;background:var(--sunk)}
video{max-width:1080px;margin:12px 0 4px}
figcaption{font-size:.88rem;color:var(--ink-2);margin-top:6px;max-width:70ch}
.fig-h{font-size:1.05rem;font-weight:600;margin:36px 0 6px}
.figs.seq{grid-template-columns:1fr;gap:14px;margin-top:4px}
.seq-head{display:grid;grid-template-columns:1fr 1fr;font-size:.8rem;color:var(--ink-3);margin-top:20px}
@media (max-width:760px){.figs.two,.figs.seq{grid-template-columns:1fr}.seq-head{max-width:none}}
/* steps */
.steps{max-width:78ch;padding-left:22px;margin:12px 0}
.steps li{margin-bottom:12px;padding-left:4px}
.steps li::marker{font-weight:600;color:var(--ink-3)}
.steps b{font-weight:600}
/* spend */
.spendbar{display:flex;gap:2px;height:28px;margin:18px 0 0;max-width:780px}
.spendbar i{display:block;height:100%}
.spendbar i:first-child{border-radius:4px 0 0 4px}.spendbar i:last-child{border-radius:0 4px 4px 0}
.s-done{background:var(--success)}.s-run{background:color-mix(in srgb,var(--success) 50%,var(--surface))}
.s-pend{background:repeating-linear-gradient(45deg,var(--action) 0 3px,color-mix(in srgb,var(--action) 45%,var(--surface)) 3px 6px)}
.s-eval{background:var(--dropped)}.s-free{background:var(--empty)}
#spendtbl{min-width:480px;max-width:780px}
/* queue */
.queue{list-style:none;padding:0;margin:12px 0;max-width:620px}
.queue li{display:grid;grid-template-columns:84px 1fr 70px;gap:12px;padding:9px 0;border-top:1px solid var(--sunk);align-items:center}
.q-state{font-size:.8rem;padding:2px 8px;border-radius:3px;background:var(--sunk);justify-self:start}
.q-done .q-state{background:var(--tint);color:var(--accent)}
.q-running .q-state{background:var(--warn-tint)}
.q-done .q-name{color:var(--ink-3)}
.q-eta{text-align:right;color:var(--ink-3)}
pre{background:var(--sunk);padding:12px 14px;border-radius:4px;overflow-x:auto;font-size:.8rem;line-height:1.5;max-width:780px}
footer{margin-top:64px;color:var(--ink-3);font-size:.85rem}
.theme{position:absolute;top:16px;right:16px}
@media (max-width:760px){.theme{position:static;display:flex;justify-content:flex-end;padding:12px 16px 0}main{padding-top:12px}}
.theme button{font:inherit;font-size:.85rem;padding:8px 12px;min-height:40px;border:0;border-radius:4px;background:var(--sunk);color:var(--ink);cursor:pointer}
@media (max-width:760px){
  h1{font-size:1.8rem}
  .grid,.bars{grid-template-columns:1fr}
  .bars{grid-template-columns:1fr 40px}.bars .gname{grid-column:1/-1;margin-top:8px}
  .cells{grid-template-columns:repeat(2,1fr)}
  .ghead{display:none}
  .task::before{content:attr(data-t);grid-column:1/-1;font-size:.72rem;color:var(--ink-3)}
  .claims{grid-template-columns:1fr}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
@media print{.controls,.theme{display:none}body{background:#fff}h2{break-after:avoid}}
</style>
</head>
<body>
<div class="theme"><button type="button" id="themeBtn">Dark / light</button></div>
<main>
<h1>Dream Orchestrator</h1>
<p class="lead"><b>Dream Orchestra turns Dream-1 skills into machine workflows and measures whether they actually
work.</b> You draw the process as a workflow, connect machines and sensors, run it in a simulated cell, and only when
a robot needs to learn a new cell do you fine-tune it, with the result measured before anyone trusts it.</p>
<p class="sub">REMix × Dream Labs hackathon, team Dream Orchestra. Everything below runs in MuJoCo simulation. As of {{NOW}}.</p>

<h2 id="idea">How it fits together</h2>
<ol class="flow">
<li><b>Skills.</b> A skill is a Dream-1 prompt for one robot type, such as "put the metal block on the machine tray".
Skills are reused across workflows.</li>
<li><b>Workflow.</b> A visual editor chains skills with waits on sensors, conditions, loops and actuator steps, and
an error path. A run highlights the active block, logs every API call with duration and credits, and can be stopped any time.</li>
<li><b>Cell and devices.</b> Sensors and actuators (light barrier, door, conveyor, stack light) are devices with an
adapter: virtual today, MQTT and OPC UA prepared. Two simulated cells, a sorting conveyor and a CNC machine, give the
workflow a real process to drive.</li>
<li><b>Measured fine-tune.</b> When the base model is not good enough in a cell, the platform records checked
demonstrations, fine-tunes Dream-1 for that robot type, and measures it on the same test scenes before release.</li>
</ol>
<figure class="shot"><img src="{{SHOT_EDITOR}}" alt="Workflow editor: Start, Greifen (Dream-1 prompt), wait for sensor, condition with loop, error path to a stack light, end" loading="lazy">
<figcaption>Workflow editor: pick-and-place with a sensor wait, a loop over remaining parts and an error path.</figcaption></figure>
<div class="figs two">
<figure class="shot"><img src="{{SHOT_CELLS}}" alt="Cell control room: live view of the CNC cell, tasks, controls and sensor states" loading="lazy">
<figcaption>Cell control room: live simulation, machine controls, sensor states and the pass/fail check of each task.</figcaption></figure>
<figure class="shot"><img src="{{SHOT_DEVICES}}" alt="Devices: sensors and actuators with type, protocol and value" loading="lazy">
<figcaption>Devices: sensors and actuators with type, protocol and current value.</figcaption></figure>
</div>

<h2 class="part" id="finetune">Part 4 in detail: does a fine-tune make the robot better in a new cell?</h2>
<p class="sub">Dream-1 on the <code>yam-sim</code> arms in our two cells. 40 identical test scenes per model: 4 tasks ×
10 seeds, never seen in training.</p>

<p class="lead" id="lead"></p>
<div class="note"><b>How we score.</b> Success = part rests in the target zone, gripper open, stable 0.4 s. First attempt
per scene counts. If Dream returns an invalid action (gripper value outside 0..1), that scene is a failure, not a retry.
Comparison is <b>paired</b>: the same scene for base and fine-tune, exact McNemar test.</div>

<h2 id="look">What the robot sees and does</h2>
<div class="figs two">{{CELLS_FIG}}</div>
<h3 class="fig-h">Same scene, before and after the fine-tune</h3>
<p class="muted">Unload CNC, test seed 1, one of the scenes the fine-tune gained. Left: Dream-1 base. Right: after the
cell fine-tune. Both get the same instruction and the same starting scene. Play the video, or read the three stills below. In the video, the label above each side is the simulator's verdict.</p>
{{VIDEO}}
<div class="seq-head"><span>Base (before)</span><span>Fine-tune (after)</span></div>
<div class="figs seq">{{SEQ_FIG}}</div>

<h2>Success on 40 scenes</h2>
<p class="muted">Bar = 95 % Wilson interval, tick = measured rate, grey line = base. Wins : losses = scenes the fine-tune
solved and the base did not, and the reverse.</p>
<div class="tbl-wrap"><table id="summary"><thead><tr>
<th>Model</th><th class="r">Success</th><th>Rate, 0–100 %</th><th class="r">Wins : losses vs base</th>
<th class="r">McNemar p</th><th class="r">Runs with contact</th></tr></thead><tbody></tbody></table></div>

<h2 id="time">Time to success</h2>
<p class="muted">Share of the 40 scenes solved by time <i>t</i> (simulated seconds from the model's first answer, limit 45 s).
This counts speed and success together on the same scenes. Hover for values.</p>
<div class="chart" id="tchart"></div>
<div class="legend" id="tlegend"></div>
<div class="tbl-wrap"><table id="ttable"><thead><tr><th>Model</th><th class="r">Successes</th>
<th class="r">Median time of successes</th><th class="r">Solved within 20 s</th><th class="r">Within 30 s</th>
<th class="r">Faster than first base run, where both succeed</th></tr></thead><tbody></tbody></table></div>
<div class="note"><b>How to read it.</b> The base is slower when it succeeds (median 29.6 s vs about 19–25 s for the
fine-tunes), and by 30 s the fine-tunes have solved three times as many scenes. A direct per-scene time comparison is
thin: base and fine-tune both succeed on only a few of the same scenes (last column), so the medians compare
different scenes. The curve is the fair view.</div>

<h2>Every scene, side by side</h2>
<p class="muted">One square per scene, same position in every row, so you can read straight down a column.
Hover or tap a square for the outcome.</p>
<div class="legend" id="legend"></div>
<div class="controls" role="group" aria-label="Highlight">
  <button type="button" data-mode="all" aria-pressed="true">Show all outcomes</button>
  <button type="button" data-mode="flips" aria-pressed="false">Highlight changes vs base</button>
</div>
<div class="grid" id="grid"></div>

<h2 id="fail">Why runs fail</h2>
<p class="muted">The base mostly never grasps the part. The fine-tune grasps far more often. Its new failure is an
invalid gripper command (1.05–1.09 instead of 0..1), which the vendor check rejects. It hits <code>sort_cube</code>
hardest (hatched squares above), so the fine-tune's <code>sort_cube</code> score understates what it can do.</p>
<div class="bars" id="bars"></div>

<h2>Per task</h2>
<div class="tbl-wrap"><table class="task-tbl" id="tasks"><thead></thead><tbody></tbody></table></div>

<h2 id="claims">What we can and cannot say</h2>
<div class="claims">
<div><h3>Supported</h3><ul>
<li>On 40 identical simulated scenes, first-attempt success rises from 15 % to 35–43 % after the cell fine-tune.
Two independent trainings point the same way (p = 0.057 and 0.013). Quote both, not just the better one.</li>
<li>The base is stable in total but not per scene: two runs of the identical base model solve 6 and 7 of 40, yet
11 scenes flip between the runs (6 : 5). Only totals are reliable; single scenes are partly luck.</li>
<li>Fine-tunes are faster as well: within 30 s they solve 12–20 of 40 scenes, the base 2–4 (time-to-success curve).</li>
<li>The gain shows up in the total, not reliably in any one task: <code>cnc_load</code> goes 3 → 7 and 10 of 10 in the
two identical trainings, but only 1 of 10 with lr 3e-5, which instead solves <code>cnc_unload</code> 10 of 10.</li>
<li>Our system measures success, contacts, aborts and cost per robot type on identical scenes, and decides whether a
fine-tune pays off. Dream itself reports no task success.</li>
</ul></div>
<div><h3>Not supported</h3><ul>
<li>Safety. Runs with arm–cell contact go <em>up</em> (8 → 15–17 of 40). We only check arm–cell contact > 0.5 mm.</li>
<li>Transfer to a real robot. Everything here is MuJoCo simulation.</li>
<li>That lr 3e-5 (20/40) is better than the main recipe: its gap to the two identical trainings (14 and 17) is not
larger than their own gap (3), so by our pre-registered rule it is not shown.</li>
<li>Variant A beats variant B, unless the gap is larger than the gap between the two identical trainings (3 of 40).</li>
<li>Time and cost comparisons, and drop height / smoothness (observed in video, exploratory).</li>
</ul></div>
</div>

<h2 id="method">How it was done</h2>
<ol class="steps">
<li><b>Two cells in simulation.</b> MuJoCo scene with the two YAM arms: a conveyor cell (sort round parts into a green
box, cubes into a blue box) and a CNC cell (load a blank onto the machine tray, unload the finished part). Four tasks,
each with a fixed instruction text.</li>
<li><b>A scripted expert.</b> A collision-aware motion planner solves the tasks (39 of 40 test scenes). It produces the
demonstrations, so the robot learns this arm in this cell.</li>
<li><b>Training data.</b> 160 expert episodes (40 per task, scene seeds 4000–4159) recorded on Modal in Dream's
LeRobot format: 10 frames per second, 14 joint values (7 per arm), 320×180 camera images.</li>
<li><b>Quality gates before any money is spent.</b> One script records, replays every episode (160 of 160 must reproduce
the result), validates the format, uploads to Dream and waits until processed. Only if every check passes does it start
the paid fine-tune.</li>
<li><b>Fine-tune.</b> Dream-1 beta, 500 steps, cosine schedule, learning rate 1e-5, cell data only. Variants each change
one thing: an identical replicate (noise), learning rate 3e-5, 50 % Dream base data mixed in, 1000 steps, 320 demos.</li>
<li><b>Same test scenes for every model.</b> Seeds 0–9 per task, never used in training. Each scene is rebuilt
identically from its seed, and the model gets the training instruction. The action playback rate (20 per second) was
chosen once on separate seeds 900–901 and then frozen.</li>
<li><b>Scoring by the simulator, not by eye.</b> Success = part in the target zone, gripper open, stable for 0.4 s.
Contact = arm penetrates the cell by more than 0.5 mm, checked every 50 ms. First attempt counts; an invalid model
command is a failure. Only infrastructure errors (e.g. a dropped session) are retried.</li>
<li><b>Statistics.</b> Paired comparison on identical scenes (exact McNemar test), 95 % Wilson intervals. Strictly
one Dream session at a time so runs cannot interfere.</li>
<li><b>Rules fixed in advance.</b> Protocol, success definition and what we may claim were written down before the
results and reviewed by two independent AI reviewers (Codex, Grok). One correction after review: an earlier count
retried invalid actions, which flattered the fine-tune. It is replaced by the first-attempt count shown here.</li>
</ol>

<h2 id="spend">Spending</h2>
<p class="muted">Fine-tunes: 0.20 $ per training step, not cancellable. Evaluation: Dream's tariff for every model call,
including failed attempts and rate calibration. Not included: warm-ups, the forgetting check, and data recording on
Modal (cents).</p>
<div class="spendbar" id="spendbar" role="img"></div>
<div class="legend" id="spendlegend"></div>
<div class="tbl-wrap"><table id="spendtbl"><thead><tr><th>Item</th><th>Status</th><th class="r">US$</th></tr></thead><tbody></tbody></table></div>

<h3 class="fig-h">Development with Claude Code (Opus 5.5)</h3>
<p class="muted">The scripted expert costs nothing per demonstration, but writing it, the cells, the simulation API and
the evaluation took many Claude Opus 5.5 sessions: more than all Dream-1 evaluation calls together, less than the fine-tunes. Shown at API list
prices ($4 / $20 per million input / output tokens, $0.20 cache reads), from the local session logs; what was actually
billed depends on the plan. Codex and Grok reviews are not included.</p>
<div class="tbl-wrap"><table id="devtbl"><thead><tr><th>Phase</th><th class="r">US$ (list price)</th></tr></thead><tbody></tbody></table></div>

<div class="note"><b>One-time versus per run.</b> A fine-tune is paid once ($100–200) and then belongs to the robot
type; each later run costs only Dream's call tariff (here about 3–5 cents per scene). Development is a one-time cost
too. The scripted expert is also reusable and costs nothing per run (39 of 40), but it has to be programmed for every
new cell and task; Dream-1 needs only demonstrations, which the expert produced here.
<br><br><b>How flexible is the fine-tune?</b> Measured: on scene layouts it never saw (test seeds 0–9, training 4000+)
it solves 14–20 of 40 instead of 6–7. Not measured yet: transfer to a new but similar task (another part or target);
all four test tasks were in training. Whether it forgets skills outside the cells is the forgetting check below.</div>

<h2>Still running</h2>
<p class="muted">Strictly one Dream session at a time. Last start 16:25, done by about 16:30. Times are estimates.</p>
<ul class="queue">
{{QUEUE}}
</ul>
<pre>{{LOG}}</pre>
<div class="note warn"><b>Forgetting check.</b> The fine-tune saw only cell data. The banana task outside the cells tests
whether it lost general skills. Pre-registered rule: "harms" only at ≥ 6 lost : 0 won paired seeds, otherwise
"forgetting not shown", which is not the same as "no forgetting".</div>

<footer>Generated by <code>src/Simulation/tools/results_page.py</code> from <code>data/evals/cells/*.jsonl</code>.
Video: <code>data/evals/cells/side_by_side/cnc_unload-1.mp4</code> (base drops the part, fine-tune places it without contact).</footer>
</main>
<div class="tip" id="tip" role="tooltip"></div>
<script id="data" type="application/json">{{DATA}}</script>
<script>
(function(){
const D=JSON.parse(document.getElementById("data").textContent);
const M=D.models, base=M.find(m=>m.label==="beta-main");
const OUT={success:"Success",dropped:"Dropped",not_released:"Placed, not released",no_grasp:"No grasp",action_error:"Invalid action (gripper > 1)"};
const ORDER=["success","dropped","not_released","no_grasp","action_error"];
const el=(t,c,txt)=>{const e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e};
const pct=k=>Math.round(k/40*100);
const isBase=m=>m.label.startsWith("beta");
const fts=M.filter(m=>m.win!=null&&m.prereg&&!isBase(m));
// lead
const lead=document.getElementById("lead");
const main=M.find(m=>m.label==="ft-main"), rep=M.find(m=>m.label==="ft-rep-main");
lead.append("Base Dream-1 solves ",el("strong",null,base.k+" of 40")," scenes. After fine-tuning on 160 scripted cell demos it solves ");
lead.append(el("strong",null,fts.map(m=>m.k).join(", ")+" of 40")," across "+fts.length+" trainings. Two of them are identical trainings (replicates), which tells us how much is noise.");
// summary
const tb=document.querySelector("#summary tbody");
M.forEach(m=>{
  const tr=el("tr");const td0=el("td");td0.append(el("div","mname",m.name));
  if(!m.prereg)td0.querySelector(".mname").append(el("span","tag","exploratory"));
  td0.append(el("div","mwhat",m.what));tr.append(td0);
  tr.append(el("td","r num",m.k+"/40"));
  const ci=el("div","ci");const b=el("i","band");b.style.left=(m.lo*100)+"%";b.style.width=((m.hi-m.lo)*100)+"%";
  const p=el("i","pt");p.style.left=(m.k/40*100)+"%";const bp=el("i","basept");bp.style.left=(base.k/40*100)+"%";
  ci.append(b,bp,p);ci.title=pct(m.k)+" % (95 % CI "+Math.round(m.lo*100)+"–"+Math.round(m.hi*100)+" %)";
  const tdc=el("td");tdc.append(ci);tr.append(tdc);
  tr.append(el("td","r num",m.win!=null?m.win+" : "+m.loss:"–"));
  const tp=el("td","r num pv",m.p!=null?m.p.toFixed(3):"–");if(m.p!=null&&m.p<0.05)tp.classList.add("sig");tr.append(tp);
  tr.append(el("td","r num",m.contact+"/40"));tb.append(tr);
});
// legend
const lg=document.getElementById("legend");
ORDER.forEach(o=>{const s=el("span");const w=el("i","sw c "+o);w.style.width="14px";s.append(w,OUT[o]);lg.append(s)});
const cs=el("span");const cw=el("i","sw c contact");cs.append(cw,"Dot = arm touched the cell");lg.append(cs);
// grid
const g=document.getElementById("grid");const tip=document.getElementById("tip");
g.append(el("div"));const gh=el("div","ghead");D.tasks.forEach(t=>gh.append(el("div",null,D.taskNames[t])));g.append(gh);
const cellEls=[];
M.forEach(m=>{
  const n=el("div","gname",m.name);n.append(el("small",null,m.k+"/40"));g.append(n);
  const wrap=el("div","cells");
  D.tasks.forEach((t,ti)=>{const tk=el("div","task");tk.dataset.t=D.taskNames[t];
    for(let i=0;i<10;i++){const s=m.scenes[ti*10+i];const c=el("i","c "+s[0]+(s[1]?" contact":""));
      c.tabIndex=0;const label=m.name+" · "+D.taskNames[t]+" seed "+i+": "+OUT[s[0]]+(s[1]?", contact":"");
      c.setAttribute("aria-label",label);c.dataset.tip=label;
      c.dataset.k=ti*10+i;c.dataset.m=m.label;cellEls.push(c);tk.append(c)}
    wrap.append(tk)});
  g.append(wrap);
});
const show=e=>{const c=e.target.closest(".c[data-tip]");if(!c){tip.style.opacity=0;return}
  const r=c.getBoundingClientRect();tip.textContent=c.dataset.tip;tip.style.left=Math.min(Math.max(r.left+r.width/2,120),innerWidth-120)+"px";
  tip.style.top=r.top+"px";tip.style.opacity=1};
g.addEventListener("mouseover",show);g.addEventListener("focusin",show);g.addEventListener("click",show);
g.addEventListener("mouseleave",()=>tip.style.opacity=0);addEventListener("scroll",()=>tip.style.opacity=0,{passive:true});
document.querySelectorAll(".controls button").forEach(b=>b.addEventListener("click",()=>{
  document.querySelectorAll(".controls button").forEach(x=>x.setAttribute("aria-pressed",x===b));
  const flips=b.dataset.mode==="flips";
  cellEls.forEach(c=>{c.classList.remove("dim","gain","lost");if(!flips||c.dataset.m==="beta-main"||c.dataset.m==="expert")return;
    const m=M.find(x=>x.label===c.dataset.m);const k=+c.dataset.k;const was=base.scenes[k][0]==="success",now=m.scenes[k][0]==="success";
    if(was===now)c.classList.add("dim");else c.classList.add(now?"gain":"lost")});
}));
// bars
const bars=document.getElementById("bars");
M.filter(m=>m.label!=="expert").forEach(m=>{
  bars.append(el("div","gname",m.name));const bar=el("div","bar");
  ORDER.forEach(o=>{const v=m.buckets[o];if(!v)return;const i=el("i","c "+o);i.style.flex=v;i.style.aspectRatio="auto";i.style.borderRadius="0";
    i.dataset.tip=m.name+": "+OUT[o]+" "+v+"/40";i.title=OUT[o]+": "+v;bar.append(i)});
  bars.append(bar);bars.append(el("div","num muted",m.buckets.success+"/40"));
});
// tasks table
const tt=document.getElementById("tasks");const hr=el("tr");hr.append(el("th",null,"Model"));
D.tasks.forEach(t=>hr.append(el("th",null,D.taskNames[t])));tt.tHead.append(hr);
M.forEach(m=>{const tr=el("tr");tr.append(el("td","mname",m.name));
  D.tasks.forEach(t=>{const td=el("td","num");td.append(m.tasks[t]+"/10");const d=el("span","dots");
    for(let i=0;i<10;i++)d.append(el("i",i<m.tasks[t]?"on":""));td.append(d);tr.append(td)});
  tt.tBodies[0].append(tr)});
// spending
const S=D.spend;const usd=v=>v.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
const done=S.jobs.filter(j=>j.status==="succeeded").reduce((a,j)=>a+j.usd,0);
const run=S.jobs.filter(j=>j.status!=="succeeded"&&j.usd>0).reduce((a,j)=>a+j.usd,0);
const pend=S.jobs.reduce((a,j)=>a+(j.pending||0),0);
const ev=Object.values(S.evals).reduce((a,v)=>a+v,0);
const free=Math.max(0,S.credit-done-run-pend-ev);
const parts=[["s-done","Fine-tunes finished",done],["s-run","Fine-tunes training",run],["s-pend","Next fine-tune if data checks pass",pend],
  ["s-eval","Evaluation calls",ev],["s-free","Credit left",free]];
const sb=document.getElementById("spendbar"),sl=document.getElementById("spendlegend");
sb.setAttribute("aria-label","Of "+usd(S.credit)+" US$ credit: "+parts.map(p=>p[1]+" "+usd(p[2])).join(", "));
parts.forEach(([c,l,v])=>{if(v<=0)return;const i=el("i",c);i.style.flex=Math.max(v,4);i.title=l+": "+usd(v)+" $";sb.append(i);
  const s=el("span");s.append(el("i","sw "+c),l+" "+usd(v)+" $");sl.append(s)});
const st=document.querySelector("#spendtbl tbody");
const row=(a,b,c,strong)=>{const tr=el("tr");tr.append(el("td",strong?"mname":"",a),el("td","muted",b),el("td","r num",c));st.append(tr)};
S.jobs.forEach(j=>row("Fine-tune "+j.name,j.status,j.usd?usd(j.usd):(j.pending?"("+usd(j.pending)+")":"–")));
row("Evaluation, all runs and calibration",Object.keys(S.evals).length+" result files",usd(ev));
row("Total committed","of "+usd(S.credit)+" $ credit",usd(done+run+ev),true);
// time to success
(function(){
  const box=document.getElementById("tchart");if(!box)return;
  const W=820,H=320,L=44,R=150,T=12,B=34,TMAX=45,N=40;
  const x=t=>L+(t/TMAX)*(W-L-R), y=k=>T+(1-k/N)*(H-T-B);
  const ns="http://www.w3.org/2000/svg";const mk=(t,a)=>{const e=document.createElementNS(ns,t);for(const k in a)e.setAttribute(k,a[k]);return e};
  const svg=mk("svg",{viewBox:`0 0 ${W} ${H}`,role:"img","aria-label":"Scenes solved by time, per model; table below"});
  const g=mk("g",{class:"grid"});const ax=mk("g",{class:"axis"});
  for(let k=0;k<=N;k+=10){g.append(mk("line",{x1:L,x2:W-R,y1:y(k),y2:y(k)}));const t=mk("text",{x:L-8,y:y(k)+4,"text-anchor":"end"});t.textContent=k;ax.append(t)}
  for(let s=0;s<=TMAX;s+=5){const t=mk("text",{x:x(s),y:H-B+18,"text-anchor":"middle"});t.textContent=s+(s===TMAX?" s":"");ax.append(t)}
  const yl=mk("text",{x:L-36,y:T+4});yl.textContent="";ax.append(yl);
  svg.append(g,ax);
  const step=m=>{let d=`M${x(0)},${y(0)}`,k=0;for(const t of m.times){d+=`H${x(t)}V${y(++k)}`}return d+`H${x(TMAX)}`};
  const order=[...M].sort((a,b)=>(a.label==="expert")-(b.label==="expert")||isBase(a)-isBase(b));
  const paths={};
  order.forEach(m=>{const cls=m.label==="expert"?"expert":isBase(m)?"base":"ft";const p=mk("path",{d:step(m),class:cls});p.dataset.label=m.label;paths[m.label]=p;svg.append(p)});
  // direct labels: expert, base, best fine-tune
  const fts2=M.filter(m=>m.label!=="expert"&&!isBase(m));const bases=M.filter(isBase);
  const lab=(m,text)=>{const t=mk("text",{x:W-R+8,y:y(m.times.length)+4,class:"lbl"});t.textContent=text;svg.append(t)};
  const ex=M.find(m=>m.label==="expert");if(ex)lab(ex,"Expert "+ex.times.length);
  {const lo=Math.min(...bases.map(m=>m.times.length)),hi=Math.max(...bases.map(m=>m.times.length));lab(base,lo===hi?"Base "+lo:`Base ${lo}–${hi}`)}
  if(fts2.length){const lo=Math.min(...fts2.map(m=>m.times.length)),hi=Math.max(...fts2.map(m=>m.times.length));
    const t=mk("text",{x:W-R+8,y:y((lo+hi)/2)+4,class:"lbl"});t.textContent=`Fine-tunes ${lo}–${hi}`;svg.append(t)}
  const cross=mk("line",{class:"cross",y1:T,y2:H-B,x1:-10,x2:-10});svg.append(cross);
  box.append(svg);
  const tip=document.createElement("div");tip.className="ctip";box.append(tip);
  const at=(m,t)=>m.times.filter(v=>v<=t).length;
  svg.addEventListener("pointermove",e=>{const r=svg.getBoundingClientRect();const px=(e.clientX-r.left)*W/r.width;
    const t=Math.max(0,Math.min(TMAX,(px-L)/(W-L-R)*TMAX));cross.setAttribute("x1",x(t));cross.setAttribute("x2",x(t));
    tip.replaceChildren();const h=el("div");h.append(el("b",null,"by "+t.toFixed(0)+" s"));tip.append(h);
    [...M].sort((a,b)=>at(b,t)-at(a,t)).forEach(m=>{const d=el("div");d.append(el("span",null,m.name),el("span",null,at(m,t)+"/40"));tip.append(d)});
    tip.style.opacity=1;const left=(x(t)/W)*r.width;tip.style.left=Math.min(left+12,r.width-tip.offsetWidth)+"px"});
  svg.addEventListener("pointerleave",()=>{tip.style.opacity=0;cross.setAttribute("x1",-10);cross.setAttribute("x2",-10)});
  const tl=document.getElementById("tlegend");
  [["expert","Expert (reference)"],["base","Base Dream-1 (each line one run)"],["ft","Fine-tunes (each line one training)"]].forEach(([c,l])=>{
    const s=el("span");const sv=mk("svg",{width:26,height:10});sv.append(mk("line",{x1:1,x2:25,y1:5,y2:5,class:c}));
    const w=el("span","chart");w.style.display="inline-block";w.append(sv);s.append(w,l);tl.append(s)});
  const tb=document.querySelector("#ttable tbody");
  M.forEach(m=>{const tr=el("tr");tr.addEventListener("pointerenter",()=>paths[m.label]?.classList.add("hot"));
    tr.addEventListener("pointerleave",()=>paths[m.label]?.classList.remove("hot"));
    tr.append(el("td","mname",m.name),el("td","r num",m.times.length+"/40"),el("td","r num",m.t_median!=null?m.t_median.toFixed(1)+" s":"–"),
      el("td","r num",m.within20+"/40"),el("td","r num",m.within30+"/40"),el("td","r num",m.both!=null?m.both_faster+" of "+m.both:"–"));tb.append(tr)});
})();
// development cost
(function(){const d=S.dev;if(!d)return;const tb=document.querySelector("#devtbl tbody");
  Object.entries(d.phases).forEach(([k,v])=>{const tr=el("tr");tr.append(el("td",null,k),el("td","r num",usd(v)));tb.append(tr)});
  const tr=el("tr");tr.append(el("td","mname",`Total, ${d.calls.toLocaleString("en-US")} model calls (${d.out_m} M output, ${d.cache_read_m} M cache-read tokens)`),el("td","r num mname",usd(d.usd)));tb.append(tr);
  const t2=el("tr");t2.append(el("td","muted","For comparison: Dream-1 evaluation calls"),el("td","r num muted",usd(ev)));tb.append(t2)})();
// theme
const root=document.documentElement;
try{const t=localStorage.getItem("cellres-theme");if(t)root.dataset.theme=t}catch(e){}
document.getElementById("themeBtn").addEventListener("click",()=>{
  const dark=root.dataset.theme?root.dataset.theme==="dark":matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme=dark?"light":"dark";try{localStorage.setItem("cellres-theme",root.dataset.theme)}catch(e){}});
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    sys.exit(main())
