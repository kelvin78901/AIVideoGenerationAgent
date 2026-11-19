"""Local smoke test (M6 step 7b): 口型修复 of a real take with LatentSync 1.6 on this machine,
through the studio's own ``POST /versions/{id}/lipsync``. Nothing is spent: the script opens a
**copy** of an earlier local run's data directory (round 19 by default) with
``DRAMA_MOCK=1 DRAMA_REAL_LOCAL=1`` (local workers and QA tools real, every API Mock).

    uv run --no-sync python scripts/smoke/local_lipsync.py [--home <data dir>] [--shot 1-04]
        [--take 9] [--studio http://127.0.0.1:8000]

- The take: ``--take N``, else the shot's adopted one. The shot's on-screen lines must be dubbed
  in that data directory (round 19: 1-04 and 1-08).
- The take is checked again first (「重新质检」: its lip sync before), then repaired; QA checks
  the repair (its lip sync after) and adopts it when the take was the adopted one and it is no
  worse.
- Checked: made locally on LatentSync, the take's size, frame rate, length (±0.1 s) and
  decoded frame count, a sound track; the peak GPU memory while it ran (nvidia-smi every
  second) and the time.
- Three frames through the spoken part (25 %, 50 %, 75 %), the take and the repair side by side,
  whole and as 1:1 crops of the face area, to ``docs/studio/reports/m6-lipsync-local/`` (JPEG);
  the clips themselves to ``reports/m5-local-smoke/originals/m6-lipsync/`` (not in git). The
  report is ``reports/m6-lipsync-local/README.txt``.

Setup items rt_latentsync and w_latentsync must be installed. Do not run it next to the full
pytest or a ComfyUI job (LatentSync takes about 18 GB of VRAM).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_assets import REAL_HOME, V1, studio_facts
from local_qa import ROUND19, copy_home
from local_upscale import frame, side_by_side

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "studio" / "reports" / "m6-lipsync-local"
ORIGINALS = ROOT / "docs" / "studio" / "reports" / "m5-local-smoke" / "originals" / "m6-lipsync"
DONE = ("succeeded", "failed", "canceled")


class GpuPeak:
    """The most GPU memory in use (MiB) while it runs, by nvidia-smi once a second."""

    def __init__(self) -> None:
        self.peak = 0
        self.start = self._used()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True)

    @staticmethod
    def _used() -> int:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout  # fmt: skip
            return int(out.split()[0])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            return 0

    def _watch(self) -> None:
        while not self._stop.wait(1.0):
            self.peak = max(self.peak, self._used())

    def __enter__(self) -> GpuPeak:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()


def frames(path: Path) -> int:
    """Decoded video frames (a lost frame at the end hides in the container's duration)."""
    from drama_series_agent.media.audio import ffmpeg_exe

    cmd = [ffmpeg_exe(), "-hide_banner", "-i", str(path), "-map", "0:v", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True, check=True).stderr
    return int(err.rsplit("frame=", 1)[1].split()[0])


def lip_value(v: dict[str, Any]) -> str:
    c = next((c for c in (v.get("qa") or {}).get("checks") or [] if c["metric"] == "lipsync"), None)
    if c is None:
        return "not checked"
    verdict = "—" if c["ok"] is None else "ok" if c["ok"] else "FAIL"
    detail = c.get("detail") or {}
    return f"{verdict} {c.get('value')} (conf {detail.get('conf')}, offset {detail.get('offset')})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--home", default=str(ROUND19), help="the data directory of a local run")
    ap.add_argument("--shot", default="1-04")
    ap.add_argument("--take", type=int, default=None, help="the take's number (default: adopted)")
    ap.add_argument("--studio", default="http://127.0.0.1:8000", help="the studio you have open")
    args = ap.parse_args()

    facts = studio_facts(args.studio.rstrip("/"))
    home = copy_home(Path(args.home))
    os.environ.update({"DRAMA_HOME": str(home), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1"})

    from fastapi.testclient import TestClient

    from drama_series_agent.api.app import create_app
    from drama_series_agent.media.video import probe
    from drama_series_agent.modelhub.adapters.local_python import RuntimePaths

    async def runtime_paths() -> RuntimePaths:
        return RuntimePaths(envs=REAL_HOME / "envs", models=facts["models"])

    lines: list[str] = []

    def say(text: str = "") -> None:
        print(text, flush=True)
        lines.append(text)

    ok = True
    headers = {"X-Drama-Studio": "1"}
    with TestClient(create_app(), base_url="http://127.0.0.1", headers=headers) as client:
        state = client.app.state.studio  # type: ignore[attr-defined]
        state.setup.runtime_paths = runtime_paths
        state.registry._adapters.clear()
        store = state.store

        def get(path: str, **params: Any) -> Any:
            resp = client.get(f"{V1}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

        def wait_job(job: dict[str, Any]) -> dict[str, Any]:
            while job["state"] not in DONE:
                time.sleep(2)
                job = get(f"/jobs/{job['id']}")
            return job

        def checked(product_id: str, version_id: str, after: float) -> dict[str, Any]:
            """The version once QA has written on it (after ``after``)."""
            deadline = time.monotonic() + 900
            while True:
                v = next(
                    x for x in get(f"/products/{product_id}")["versions"] if x["id"] == version_id
                )
                ran = (v.get("qa") or {}).get("ran_at")
                if ran and datetime.fromisoformat(ran.replace("Z", "+00:00")).timestamp() > after:
                    return v
                if time.monotonic() > deadline:
                    return v
                time.sleep(2)

        series = get("/series")[0]
        episode = get(f"/series/{series['id']}/episodes")[0]
        shot = next(s for s in get(f"/episodes/{episode['id']}/shots") if s["label"] == args.shot)
        product = get(f"/products/{shot['video_product_id']}")
        adopted = product["adopted_version_id"]
        takes = [v for v in product["versions"] if any(f["role"] == "video" for f in v["files"])]
        take = (
            next(v for v in takes if v["n"] == args.take)
            if args.take is not None
            else next(v for v in takes if v["id"] == adopted)
        )
        video = next(f for f in take["files"] if f["role"] == "video")
        src = store.path_for(video["sha256"])
        say(f"M6 口型修复 local smoke · {datetime.now():%Y-%m-%d %H:%M} · {args.home}")
        say(f"{args.shot} T{take['n']} ({take['model_key']}, {video['w']}×{video['h']}, "
            f"{video['duration_s']} s){' · adopted' if take['id'] == adopted else ''}")  # fmt: skip
        est = (product.get("estimate") or {}).get("finishing", {}).get("lip")
        if est:
            say(f"estimate: {est['model_key']} · ${est['cost_usd']} · ~{est['seconds']:.0f} s")

        # Lip sync before: the take checked again with this machine's tools.
        t = time.time()
        resp = client.post(f"{V1}/versions/{take['id']}/qa")
        resp.raise_for_status()
        wait_job(resp.json())
        before = checked(product["id"], take["id"], t)
        say(f"lip sync before: {lip_value(before)}")

        t = time.time()
        t0 = time.monotonic()
        resp = client.post(f"{V1}/versions/{take['id']}/lipsync")
        if resp.status_code != 200:
            say(f"REFUSED: {resp.status_code} {resp.text}")
            return 1
        with GpuPeak() as gpu:
            job = wait_job(resp.json())
        took = time.monotonic() - t0
        if job["state"] != "succeeded":
            say(f"FAILED: {job['state']} {job.get('error')}")
            OUT.mkdir(parents=True, exist_ok=True)
            with open(OUT / "README.txt", "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines) + "\n")
            return 1
        say(f"lipsync job {job['state']} in {took:.0f} s · GPU memory peak {gpu.peak} MiB "
            f"(before {gpu.start} MiB)")  # fmt: skip
        after = get(f"/products/{product['id']}")
        v = after["versions"][-1]
        v = checked(product["id"], v["id"], t)
        after = get(f"/products/{product['id']}")

        out = next(f for f in v["files"] if f["role"] == "video")
        dst = store.path_for(out["sha256"])
        a, b = (client.portal.call(probe, p.read_bytes()) for p in (src, dst))  # type: ignore[union-attr]
        checks = {
            "on LatentSync locally": v["model_key"] == "local/latentsync" and v["where"] == "local",
            "size kept": (a.w, a.h) == (b.w, b.h),
            "frame rate kept": a.fps == b.fps,
            "length kept (±0.1 s)": abs(a.duration_s - b.duration_s) <= 0.1,
            f"frames kept ({frames(src)})": frames(src) == frames(dst),
            "has sound": b.has_audio,
        }
        say(f"→ T{v['n']} {v['model_key']} ({v['where']}), origin {v['origin']}, "
            f"lip {v['payload'].get('lip')}")  # fmt: skip
        say(f"  take   {a.w}×{a.h} {a.fps} fps {a.duration_s} s audio={a.has_audio}")
        say(f"  repair {b.w}×{b.h} {b.fps} fps {b.duration_s} s audio={b.has_audio}")
        for name, passed in checks.items():
            say(f"  {'ok ' if passed else 'BAD'} {name}")
            ok = ok and passed
        say(f"lip sync after: {lip_value(v)}")
        rows = [
            f"{c['metric']} {'—' if c['ok'] is None else 'ok' if c['ok'] else 'FAIL'}"
            + (f" {c['value']}" if c.get("value") is not None else "")
            for c in (v.get("qa") or {}).get("checks") or []
        ]
        say(f"  QA: {v['qa_pass']} · {', '.join(rows)}")
        was = take["id"] == adopted
        say(f"  adopted now: {after['adopted_version_id'] == v['id']} (take was adopted: {was})")

        OUT.mkdir(parents=True, exist_ok=True)
        ORIGINALS.mkdir(parents=True, exist_ok=True)
        name = f"{args.shot}-T{take['n']}"
        shutil.copyfile(dst, ORIGINALS / f"{name}-lipsync.mp4")
        shutil.copyfile(src, ORIGINALS / f"{name}-take.mp4")
        with tempfile.TemporaryDirectory() as tmp:
            for pct in (25, 50, 75):
                fa, fb = Path(tmp) / f"a{pct}.png", Path(tmp) / f"b{pct}.png"
                at = a.duration_s * pct / 100
                frame(src, at, fa)
                frame(dst, at, fb)
                side_by_side(fa, fb, OUT / f"{name}-{pct}-whole.jpg")
                size = min(b.w, b.h) // 2
                crop = f"{size}:{size}:{(b.w - size) // 2}:{b.h // 6}"
                side_by_side(fa, fb, OUT / f"{name}-{pct}-crop.jpg", crop=crop)
        say(f"  pictures: {OUT.relative_to(ROOT)}/{name}-{{25,50,75}}-whole.jpg, -crop.jpg "
            f"(left: the take, right: LatentSync; the crop is 1:1)")  # fmt: skip
        say(f"  took {took:.0f} s for {a.duration_s} s of take")

    with open(OUT / "README.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    shutil.rmtree(home.parent, ignore_errors=True)
    print("ALL OK" if ok else "SOMETHING FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
