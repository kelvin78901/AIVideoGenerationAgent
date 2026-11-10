"""Shots made again on run11's seeds after a change, measured against run11 (M5 steps 15j+).

On a copy of run11's data directory, each shot gets one more take on the seed of its run11
first take, through the studio as it is now; then both takes are measured: how long the
opening stays still (``media/video.py`` frame-to-frame PSNR), where the loud part of the sound
is (the line), cuts inside the clip (scene score) and the prompt's length.

    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/retake_compare.py --home <run11's dir>
        --run run13-pacing [--shots 1-02,1-04,1-05] [--work <an earlier copy>]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "smoke"))
SMOKE = REPO / "docs/studio/reports/m5-local-smoke"
REAL = "deepseek/v4.1-flash,google/gemini-3.1-flash-lite"


def measure(data: bytes, fps: float) -> dict[str, Any]:
    from drama_series_agent.media import video as v

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        src.write_bytes(data)
        info = v._probe_file(src)
        still = v._still_head(src, info.fps or fps)
        speech = v._speech(src) if info.has_audio else None
    cuts = asyncio.run(v.scene_cuts(data))
    return {
        "s": round(info.duration_s, 2),
        "still_s": round(still, 2),
        "loud": speech,
        "cuts": cuts,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True)
    ap.add_argument("--work")
    ap.add_argument("--run", required=True, help="the report folder's name")
    ap.add_argument("--shots", default="1-02,1-04,1-05")
    ap.add_argument("--model", help="a model to name (else the studio picks as usual)")
    args = ap.parse_args()
    if os.environ.get("DRAMA_LIVE") != "1":
        raise SystemExit("the rewrite and the look are real calls: set DRAMA_LIVE=1")
    out, sheets = SMOKE / "originals" / args.run, SMOKE / args.run
    out.mkdir(parents=True, exist_ok=True)
    sheets.mkdir(parents=True, exist_ok=True)
    if args.work:
        work = Path(args.work)
    else:
        work = Path(tempfile.mkdtemp(prefix="drama-retake-")) / "home"
        shutil.copytree(args.home, work)
    os.environ.update({"DRAMA_HOME": str(work), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1",
                       "DRAMA_REAL_MODELS": REAL})  # fmt: skip

    from fastapi.testclient import TestClient
    from local_assets import V1, Smoke, VramMeter, studio_facts
    from local_storyboard import shots
    from local_video import EP_RECORD, free_comfy, sheet

    from drama_series_agent.api.app import create_app
    from drama_series_agent.core.models_db import LlmCache
    from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget
    from drama_series_agent.pipeline import runs

    facts = studio_facts("http://127.0.0.1:8000")
    record = json.loads((work / EP_RECORD).read_text("utf-8"))

    async def comfy_target() -> ComfyTarget:
        return ComfyTarget(url=facts["comfy_url"], env_hash=facts["env_hash"])

    meter = VramMeter()
    meter.start()
    with TestClient(create_app(), base_url="http://127.0.0.1",
                    headers={"X-Drama-Studio": "1"}) as client:  # fmt: skip
        state = client.app.state.studio  # type: ignore[attr-defined]
        state.setup.comfy_target = comfy_target
        state.registry._adapters.clear()
        smoke = Smoke(client, state, out, meter)
        smoke.expected_api = set(REAL.split(","))
        store = state.store
        by_label = shots(smoke)
        off = {"enabled": False, "on": [], "qa_fail_n": 2, "timeout_s": 600, "to": None}
        off["notify"] = "after"
        body = {"scope": "component", "scope_id": None, "component_id": "vid"}
        client.put(f"{V1}/config/override", json={**body, "data": {"fallback": off}})

        async def clear() -> None:
            from sqlmodel import delete

            async with state.db.session() as s:
                await s.exec(delete(LlmCache).where(LlmCache.key.like("media:%")))  # type: ignore[attr-defined]
                await s.commit()

        def path(v: dict[str, Any], role: str) -> Path:
            return store.path_for(next(f for f in v["files"] if f["role"] == role)["sha256"])

        for label in args.shots.split(","):
            pid = by_label[label]["video_product_id"]
            product = smoke.get(f"/products/{pid}")
            old = next(v for v in product["versions"] if v["id"] == record[label]["takes"][0])
            client.portal.call(clear)
            runs.random.randrange = lambda *_, s=int(old["seed"]): s  # type: ignore[attr-defined]
            extra = {"model": args.model} if args.model else {}

            def start(pid: str = pid, extra: dict[str, Any] = extra) -> list[str]:
                free_comfy(facts["comfy_url"])
                return [smoke.run(pid, count=1, **extra)["id"]]

            job = smoke.step(label, f"{label} seed {old['seed']} again", start)
            if job is None or job["state"] != "succeeded":
                continue
            new = smoke.latest(pid)
            for name, v in (("run11", old), ("new", new)):
                m = measure(path(v, "video").read_bytes(), 24.0)
                words = len(path(v, "prompt").read_text("utf-8").split())
                smoke.say(f"   {name:5} {label}: {m['s']}s, still opening {m['still_s']}s, "
                          f"loud {m['loud']}, cuts {m['cuts']}, prompt {words} words, "
                          f"window {v['payload'].get('window')}")  # fmt: skip
                shutil.copyfile(path(v, "video"), out / f"{name}-{label}.mp4")
                shutil.copyfile(path(v, "prompt"), sheets / f"prompt-{name}-{label}.txt")
                sheet(path(v, "video"), out / f"sheet-{name}-{label}.png")
        from local_video import jpeg_sheets

        jpeg_sheets(out, sheets)
    meter.stop()
    (sheets / f"report-{args.shots.replace(',', '_')}.txt").write_text(
        "\n".join(smoke.lines) + "\n", "utf-8", newline="\n"
    )
    print(f"work dir: {work}")
    return 0 if smoke.ok else 1


if __name__ == "__main__":
    sys.exit(main())
