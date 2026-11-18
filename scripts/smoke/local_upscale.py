"""Local smoke test (M6 step 6): 2K 精修 of a real take on this machine's ComfyUI (SeedVR2 7B),
through the studio's own ``POST /versions/{id}/upscale``. Nothing is spent: the script opens a
**copy** of an earlier local run's data directory (round 19 by default) with
``DRAMA_MOCK=1 DRAMA_REAL_LOCAL=1`` (ComfyUI and the local QA tools real, every API Mock).

    uv run --no-sync python scripts/smoke/local_upscale.py [--home <data dir>] [--shot 1-04]
        [--studio http://127.0.0.1:8000]

- The take is the shot's adopted one, else its newest local take.
- Checked: made locally on SeedVR2 (a fallback is reported), the delivery size (1080×1920), the
  take's frame rate and length, its sound stream byte for byte, then QA and whether it was
  adopted (only when the take was the adopted one).
- A middle frame of the take (scaled to 1080×1920 with Lanczos) and of the upscale go side by
  side, whole and as a 1:1 crop of the face area, to ``docs/studio/reports/m6-upscale-local/``
  (JPEG); the upscaled clip itself to ``reports/m5-local-smoke/originals/m6-upscale/`` (not in
  git). The report is ``reports/m6-upscale-local/README.txt``.

ComfyUI must be running (the address is the open studio's last scan); do not run it next to
the full pytest. One 5 s take takes about 3.5 minutes on the 5090.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_assets import REAL_HOME, V1, studio_facts
from local_qa import ROUND19, copy_home

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "studio" / "reports" / "m6-upscale-local"
ORIGINALS = ROOT / "docs" / "studio" / "reports" / "m5-local-smoke" / "originals" / "m6-upscale"
DONE = ("succeeded", "failed", "canceled")


def ffmpeg(*args: str) -> bytes:
    from drama_series_agent.media.audio import ffmpeg_exe

    cmd = [ffmpeg_exe(), "-hide_banner", "-v", "error", *args]
    return subprocess.run(cmd, check=True, capture_output=True).stdout


def sound(path: Path) -> bytes:
    return ffmpeg("-i", str(path), "-map", "0:a:0", "-c", "copy", "-f", "data", "-")


def frame(path: Path, at: float, out: Path, scale: str | None = None) -> None:
    vf = ["-vf", f"scale={scale}:flags=lanczos"] if scale else []
    ffmpeg("-ss", f"{at:.3f}", "-i", str(path), "-frames:v", "1", *vf, "-y", str(out))


def side_by_side(a: Path, b: Path, out: Path, crop: str | None = None) -> None:
    pre = f"crop={crop}," if crop else ""
    graph = f"[0:v]{pre}setsar=1[a];[1:v]{pre}setsar=1[b];[a][b]hstack=inputs=2"
    ffmpeg("-i", str(a), "-i", str(b), "-filter_complex", graph, "-q:v", "3", "-y", str(out))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--home", default=str(ROUND19), help="the data directory of a local run")
    ap.add_argument("--shot", default="1-04")
    ap.add_argument("--studio", default="http://127.0.0.1:8000", help="the studio you have open")
    args = ap.parse_args()

    facts = studio_facts(args.studio.rstrip("/"))
    home = copy_home(Path(args.home))
    os.environ.update({"DRAMA_HOME": str(home), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1"})

    from fastapi.testclient import TestClient

    from drama_series_agent.api.app import create_app
    from drama_series_agent.media.video import probe
    from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget
    from drama_series_agent.modelhub.adapters.local_python import RuntimePaths
    from drama_series_agent.wflib.comfy import HttpComfy

    async def runtime_paths() -> RuntimePaths:
        return RuntimePaths(envs=REAL_HOME / "envs", models=facts["models"])

    async def comfy_target() -> ComfyTarget:
        return ComfyTarget(url=facts["comfy_url"], env_hash=facts["env_hash"])

    async def comfy_url() -> str:
        return str(facts["comfy_url"])

    lines: list[str] = []

    def say(text: str = "") -> None:
        print(text, flush=True)
        lines.append(text)

    ok = True
    headers = {"X-Drama-Studio": "1"}
    with TestClient(create_app(), base_url="http://127.0.0.1", headers=headers) as client:
        state = client.app.state.studio  # type: ignore[attr-defined]
        state.setup.runtime_paths = runtime_paths
        state.setup.comfy_target = comfy_target
        state.workflows.comfy = lambda: HttpComfy(comfy_url, state.http_transport)
        state.registry._adapters.clear()
        store = state.store

        def get(path: str, **params: Any) -> Any:
            resp = client.get(f"{V1}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

        series = get("/series")[0]
        episode = get(f"/series/{series['id']}/episodes")[0]
        shot = next(s for s in get(f"/episodes/{episode['id']}/shots") if s["label"] == args.shot)
        product = get(f"/products/{shot['video_product_id']}")
        takes = [v for v in product["versions"] if any(f["role"] == "video" for f in v["files"])]
        adopted = product["adopted_version_id"]
        take = next((v for v in takes if v["id"] == adopted), None) or next(
            v for v in reversed(takes) if v["where"] == "local"
        )
        video = next(f for f in take["files"] if f["role"] == "video")
        src = store.path_for(video["sha256"])
        say(f"M6 2K 精修 local smoke · {datetime.now():%Y-%m-%d %H:%M} · {args.home}")
        say(f"{args.shot} T{take['n']} ({take['model_key']}, {video['w']}×{video['h']}, "
            f"{video['duration_s']} s){' · adopted' if take['id'] == adopted else ''}")  # fmt: skip
        est = (product.get("estimate") or {}).get("finishing", {}).get("up")
        if est:
            say(f"estimate: {est['model_key']} · ${est['cost_usd']} · ~{est['seconds']:.0f} s")

        t0 = time.monotonic()
        resp = client.post(f"{V1}/versions/{take['id']}/upscale", json={})
        resp.raise_for_status()
        job = resp.json()
        while job["state"] not in DONE:
            time.sleep(2)
            job = get(f"/jobs/{job['id']}")
        took = time.monotonic() - t0
        if job["state"] != "succeeded":
            say(f"FAILED: {job['state']} {job.get('error')}")
            return 1
        say(f"upscale job {job['state']} in {took:.0f} s")
        # QA queues on the new version; wait for it.
        deadline = time.monotonic() + 600
        while True:
            after = get(f"/products/{product['id']}")
            v = after["versions"][-1]
            if v["qa"] is not None or time.monotonic() > deadline:
                break
            time.sleep(2)

        out = next(f for f in v["files"] if f["role"] == "video")
        dst = store.path_for(out["sha256"])
        a, b = (client.portal.call(probe, p.read_bytes()) for p in (src, dst))  # type: ignore[union-attr]
        local = v["model_key"] == "comfy/seedvr2" and v["where"] == "local"
        same_sound = a.has_audio and b.has_audio and sound(src) == sound(dst)
        checks = {
            "on SeedVR2 locally": local,
            "1080×1920": (b.w, b.h) == (1080, 1920),
            "frame rate kept": a.fps == b.fps,
            "length kept (±0.05 s)": abs(a.duration_s - b.duration_s) <= 0.05,
            "sound byte for byte": same_sound,
        }
        say(f"→ T{v['n']} {v['model_key']} ({v['where']}), origin {v['origin']}, parent T"
            f"{next(x['n'] for x in takes if x['id'] == v['parent_version_id'])}")  # fmt: skip
        say(f"  take   {a.w}×{a.h} {a.fps} fps {a.duration_s} s audio={a.has_audio}")
        say(f"  2K     {b.w}×{b.h} {b.fps} fps {b.duration_s} s audio={b.has_audio}")
        for name, passed in checks.items():
            say(f"  {'ok ' if passed else 'BAD'} {name}")
            ok = ok and passed
        qa = v.get("qa") or {}
        rows = [
            f"{c['metric']} {'—' if c['ok'] is None else 'ok' if c['ok'] else 'FAIL'}"
            + (f" {c['value']}" if c.get("value") is not None else "")
            for c in qa.get("checks") or []
        ]
        say(f"  QA: {v['qa_pass']} · {', '.join(rows)}")
        was = take["id"] == adopted
        say(f"  adopted now: {after['adopted_version_id'] == v['id']} (take was adopted: {was})")

        OUT.mkdir(parents=True, exist_ok=True)
        ORIGINALS.mkdir(parents=True, exist_ok=True)
        name = f"{args.shot}-T{take['n']}"
        shutil.copyfile(dst, ORIGINALS / f"{name}-2k.mp4")
        shutil.copyfile(src, ORIGINALS / f"{name}-take.mp4")
        with tempfile.TemporaryDirectory() as tmp:
            fa, fb = Path(tmp) / "a.png", Path(tmp) / "b.png"
            mid = a.duration_s / 2
            frame(src, mid, fa, scale=f"{b.w}:{b.h}")
            frame(dst, mid, fb)
            side_by_side(fa, fb, OUT / f"{name}-whole.jpg")
            # The face area of a medium shot: the upper middle, at 1:1.
            crop = f"540:540:{(b.w - 540) // 2}:{b.h // 5}"
            side_by_side(fa, fb, OUT / f"{name}-crop.jpg", crop=crop)
        say(f"  pictures: {OUT.relative_to(ROOT)}/{name}-whole.jpg, -crop.jpg (left: the take "
            f"scaled with Lanczos, right: SeedVR2)")  # fmt: skip
        say(f"  took {took:.0f} s for {a.duration_s} s of take")

    with open(OUT / "README.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    shutil.rmtree(home.parent, ignore_errors=True)
    print("ALL OK" if ok else "SOMETHING FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
