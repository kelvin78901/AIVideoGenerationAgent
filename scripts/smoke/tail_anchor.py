"""Tail guide plus an anchor on the last frame (M5 step 15h, Kelvin 2026-11-09).

Run11 found the cut into a continuing shot jumps: the tail clip guided at frame 0 holds its
first frame (~35 dB against the shot before) and drifts after it (~20 dB by frame 21), so the
take, cut after the tail's 22 frames, starts from a pose the shot before never reached. Here
one more official ``MiniMaxH3AddGuide`` pins the shot before's LAST frame at frame 21, the
tail's last frame, so frame 22 (where the take starts) follows the real end of that shot.

1-08 is made once on run11's seed and inputs, on a copy of run11's data directory, through the
studio with this process patching the graph (``ComfyUIAdapter._one``); nothing in the product
changes. The cut is measured as run11's was (PSNR of the shot before's last frame against the
take's first, and of the guided frames against the tail they should repeat).

    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/tail_anchor.py --home <run11's data dir>
        [--label 1-08] [--work <an earlier copy>]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "smoke"))

OUT = REPO / "docs/studio/reports/m5-local-smoke/originals/run12-tail-anchor"
SHEETS = REPO / "docs/studio/reports/m5-local-smoke/run12-tail-anchor"
REAL = "deepseek/v4.1-flash,google/gemini-3.1-flash-lite"
TAIL_FRAMES = 22
PATCH: dict[str, Any] = {"last": None}


def install_patch() -> None:
    from drama_series_agent.modelhub.adapters import comfyui as cm

    orig = cm.ComfyUIAdapter._one

    async def _one(self, client, socket, url, wf, graph, progress):  # type: ignore[no-untyped-def]
        g = graph
        tail = next(
            (n for n, x in g.items() if x.get("_meta", {}).get("title") == "Tail guide"), None
        )
        if PATCH["last"] and tail is not None:
            data = await asyncio.to_thread(Path(PATCH["last"]).read_bytes)
            name = await self._upload(
                client, f"last-{hashlib.sha256(data).hexdigest()[:16]}.png", data, "image/png"
            )
            for node in g.values():  # what read the tail guide's conditioning reads the anchor's
                for k, v in node["inputs"].items():
                    if v == [tail, 0]:
                        node["inputs"][k] = ["951", 0]
            g["950"] = {"class_type": "LoadImage", "inputs": {"image": name},
                        "_meta": {"title": "Tail last frame"}}  # fmt: skip
            t = g[tail]["inputs"]
            g["951"] = {
                "class_type": "MiniMaxH3AddGuide",
                "inputs": {"positive": [tail, 0], "latent": t["latent"],
                           "frame_idx": TAIL_FRAMES - 1, "vae": t["vae"], "image": ["950", 0]},
                "_meta": {"title": "Tail end anchor"},
            }  # fmt: skip
            (OUT / "graph.json").write_text(json.dumps(g, ensure_ascii=False, indent=1), "utf-8")
        return await orig(self, client, socket, url, wf, graph, progress)

    cm.ComfyUIAdapter._one = _one  # type: ignore[method-assign]


def ff(*args: str) -> str:
    from drama_series_agent.media.audio import ffmpeg_exe

    done = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostdin", *args],
                          capture_output=True, text=True, check=True)  # fmt: skip
    return done.stderr


def frames(src: Path, dest: Path, *, last: int | None = None) -> list[Path]:
    """The clip's frames as PNGs (only the last ``last`` when given)."""
    dest.mkdir(parents=True, exist_ok=True)
    for p in dest.glob("*.png"):
        p.unlink()
    ff("-loglevel", "error", "-y", "-i", str(src), str(dest / "%04d.png"))
    out = sorted(dest.glob("*.png"))
    return out[-last:] if last else out


def psnr(a: Path, b: Path) -> float:
    text = ff("-i", str(a), "-i", str(b), "-filter_complex", "[0][1]psnr", "-f", "null", "-")
    found = [x for x in text.splitlines() if "average:" in x]
    value = found[-1].split("average:", 1)[1].split()[0] if found else "0"
    return float("inf") if value == "inf" else float(value)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True, help="run11's data directory")
    ap.add_argument("--work", help="a copy made by an earlier run (reused)")
    ap.add_argument("--label", default="1-08")
    args = ap.parse_args()
    if os.environ.get("DRAMA_LIVE") != "1":
        raise SystemExit("the prompt rewrite and the look are real calls: set DRAMA_LIVE=1")
    OUT.mkdir(parents=True, exist_ok=True)
    SHEETS.mkdir(parents=True, exist_ok=True)
    if args.work:
        work = Path(args.work)
    else:
        work = Path(tempfile.mkdtemp(prefix="drama-anchor-")) / "home"
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

    install_patch()
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
        smoke = Smoke(client, state, OUT, meter)
        smoke.expected_api = set(REAL.split(","))
        store = state.store
        by_label = shots(smoke)
        label = args.label
        before = str(by_label[label]["tail_from"])
        smoke.say(f"{label} with a last-frame anchor at frame {TAIL_FRAMES - 1} · work dir {work}")

        def product(x: str) -> dict[str, Any]:
            got: dict[str, Any] = smoke.get(f"/products/{by_label[x]['video_product_id']}")
            return got

        def path(v: dict[str, Any], role: str) -> Path:
            return store.path_for(next(f for f in v["files"] if f["role"] == role)["sha256"])

        prev = product(before)
        prev_v = next(v for v in prev["versions"] if v["id"] == prev["adopted_version_id"])
        old = next(v for v in product(label)["versions"] if v["id"] == record[label]["takes"][0])
        PATCH["last"] = str(path(prev_v, "last_frame"))
        off = {"enabled": False, "on": [], "qa_fail_n": 2, "timeout_s": 600, "to": None}
        off["notify"] = "after"
        body = {"scope": "component", "scope_id": None, "component_id": "vid"}
        put = client.put(f"{V1}/config/override", json={**body, "data": {"fallback": off}})
        put.raise_for_status()

        async def clear() -> None:
            from sqlmodel import delete

            async with state.db.session() as s:
                await s.exec(delete(LlmCache).where(LlmCache.key.like("media:%")))  # type: ignore[attr-defined]
                await s.commit()

        client.portal.call(clear)
        runs.random.randrange = lambda *_: int(old["seed"])  # type: ignore[attr-defined]

        def start() -> list[str]:
            free_comfy(facts["comfy_url"])
            return [smoke.run(by_label[label]["video_product_id"], count=1, model="comfy/h3")["id"]]

        job = smoke.step("anchor", f"{label} seed {old['seed']}, tail + last-frame anchor", start)
        if job is None or job["state"] != "succeeded":
            meter.stop()
            return 1
        new = smoke.latest(by_label[label]["video_product_id"])
        tmp = Path(tempfile.mkdtemp(prefix="anchor-frames-"))
        tail = frames(path(prev_v, "video"), tmp / "tail", last=TAIL_FRAMES)
        for name, v in (("run11", old), ("anchored", new)):
            raw = frames(path(v, "raw"), tmp / f"{name}-raw")
            take = frames(path(v, "video"), tmp / f"{name}-take")
            guided = [psnr(tail[i], raw[i]) for i in (0, 5, 10, 15, 21)]
            cut = psnr(tail[-1], take[0])
            inside = psnr(take[0], take[1]), psnr(take[1], take[2])
            smoke.say(f"   {name}: guided frames 0/5/10/15/21 vs the tail "
                      f"{' / '.join(f'{x:.1f}' for x in guided)} dB; cut {cut:.1f} dB "
                      f"(take's first two pairs {inside[0]:.1f}, {inside[1]:.1f})")  # fmt: skip
            shutil.copyfile(path(v, "video"), OUT / f"{name}-{label}.mp4")
            sheet(path(v, "video"), OUT / f"sheet-{name}-{label}.png")
            shutil.copyfile(take[0], tmp / f"{name}-first.png")
        shutil.copyfile(tail[-1], tmp / "before-last.png")
        ff("-loglevel", "error", "-y", "-i", str(tmp / "before-last.png"),
           "-i", str(tmp / "run11-first.png"), "-i", str(tmp / "anchored-first.png"),
           "-filter_complex", "[0]scale=384:672[a];[1]scale=384:672[b];[2]scale=384:672[c];"
           "[a][b][c]hstack=3", str(tmp / "cut.png"))  # fmt: skip
        ff("-loglevel", "error", "-y", "-i", str(tmp / "cut.png"), "-pix_fmt", "yuvj420p",
           "-q:v", "4", str(SHEETS / f"cut-{label}.jpg"))  # fmt: skip
        for png in OUT.glob("sheet-*.png"):
            ff("-loglevel", "error", "-y", "-i", str(png), "-q:v", "4",
               str(SHEETS / f"{png.stem}.jpg"))  # fmt: skip
    meter.stop()
    (SHEETS / f"report-{label}.txt").write_text("\n".join(smoke.lines) + "\n", "utf-8",
                                                 newline="\n")  # fmt: skip
    print(f"work dir: {work}")
    return 0 if smoke.ok else 1


if __name__ == "__main__":
    sys.exit(main())
