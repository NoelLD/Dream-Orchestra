"""Fan out scripted YAM demo generation on Modal: one container per episode, one LeRobot session per episode.

    modal run src/Simulation/tools/modal_gen.py --name pick-v1 --count 2    # wave 1: two episodes
    modal run src/Simulation/tools/modal_gen.py --name pick-v1 --count 50   # wave 2: resumes, skips existing
Run from a host with the modal CLI and the Dream example cloned to Dream-Orchestra/vendor/dreamlabs.
Result: src/Simulation/data/datasets/<name>/ep-<seed>/ (each a one-episode LeRobot v2.1 session; Dream accepts a folder of sessions).
Validate afterwards:  docker compose run --rm simulation python /app/tools/validate.py datasets/<name>
No Dream API calls. Costs Modal CPU time only; a cost/provenance line per run goes to data/datasets/<name>.runs.jsonl.
"""

import io
import json
import tarfile
import time
from pathlib import Path

import modal

# Host paths only: inside the container this file is /root/modal_gen.py, so parents[1] would be "/" and
# SERVICE.parents[1] raised IndexError at import (every container crash-looped on startup).
# The container never reads these (the image is already built); any path deep enough for parents[1] works.
SERVICE = Path(__file__).resolve().parents[1] if modal.is_local() else Path("/unused/src/Simulation")
EXAMPLE = SERVICE.parents[1] / "vendor/dreamlabs/dream_library/examples/yam_mujoco"
DATASETS = SERVICE / "data/datasets"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libegl1", "libgl1", "libgles2", "libgl1-mesa-dri", "libosmesa6", "ffmpeg")
    .pip_install_from_requirements(str(SERVICE / "requirements.txt"))
    .env({"MUJOCO_GL": "egl", "DREAM_LOG": "off", "DREAM_YAM_EXAMPLE": "/opt/yam_mujoco", "SIM_DATA_DIR": "/tmp/simdata"})
    .add_local_dir(str(EXAMPLE), "/opt/yam_mujoco", ignore=["**/mock_results", "**/__pycache__"])
    .add_local_dir(str(SERVICE / "app"), "/work/app", ignore=["**/__pycache__"])
    .add_local_dir(str(SERVICE / "tools"), "/work/tools", ignore=["**/__pycache__"])
)
app = modal.App("dream-orchestra-demo-gen", image=image)


@app.function(cpu=2, memory=4096, timeout=900, retries=1)
def record_episode(seed: int, skill: str = "both", small: bool = False) -> dict:
    """Record one randomized episode and return the session as a tar. skill: banana | apple | both (alternating)."""
    import subprocess

    start = time.time()
    out = Path(f"/tmp/ep-{seed:04d}")
    proc = subprocess.run(
        ["python", "tools/record_dataset.py", "--out", str(out), "--episodes", "1", "--seed", str(seed),
         "--randomize", "--skill-offset", str({"banana": 0, "apple": 1}.get(skill, seed % 2)), "--no-validate"]
        + (["--small"] if small else []),
        cwd="/work", capture_output=True, text=True,
    )
    log = (proc.stdout + proc.stderr)[-2000:]
    if proc.returncode != 0 or not (out / "meta/info.json").exists():
        return {"seed": seed, "ok": False, "log": log, "seconds": time.time() - start}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        tar.add(out, arcname=out.name)
        results = out.parent / f"{out.name}.sim_results.json"
        if results.exists():
            tar.add(results, arcname=results.name)
    return {"seed": seed, "ok": True, "tar": buffer.getvalue(), "log": log[-300:], "seconds": time.time() - start}


@app.local_entrypoint()
def main(name: str = "pick-v1", count: int = 2, first_seed: int = 1000, skill: str = "both", small: bool = False):
    """Training seeds start at 1000; evaluation uses seeds below 1000, so test scenes are never training scenes."""
    target = DATASETS / name
    target.mkdir(parents=True, exist_ok=True)
    seeds = [s for s in range(first_seed, first_seed + count) if not (target / f"ep-{s:04d}/meta/info.json").exists()]
    print(f"{count - len(seeds)} sessions exist, launching {len(seeds)}")
    runs = target.parent / f"{name}.runs.jsonl"
    ok = 0
    for result in record_episode.map(seeds, kwargs={"skill": skill, "small": small}, return_exceptions=True):
        if isinstance(result, Exception):
            print("worker error:", result)
            continue
        record = {k: v for k, v in result.items() if k != "tar"}
        if result["ok"]:
            with tarfile.open(fileobj=io.BytesIO(result["tar"])) as tar:
                tar.extractall(target, filter="data")
            # The validator refuses stray .json beside sessions: keep sim results in a sibling folder.
            results_dir = target.parent / f"{name}.sim_results"
            results_dir.mkdir(exist_ok=True)
            for stray in target.glob("*.sim_results.json"):
                stray.rename(results_dir / stray.name)
            ok += 1
        print(f"seed {result['seed']}: {'ok' if result['ok'] else 'FAILED'} in {result['seconds']:.0f}s")
        if not result["ok"]:
            print(result["log"])
        with runs.open("a") as fh:
            fh.write(json.dumps(record | {"finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
    print(f"done: {ok}/{len(seeds)} new sessions in {target}")
