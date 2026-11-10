"""Continuous shots: how the tail goes in and whether references go with it (M5 step 15m).

On a copy of run11's data directory 1-09 (close-up: 林晚 picks up the red umbrella at the door;
continues 1-08, no line) is made once per variant on the seed of run11's first 1-09 take:

  old       ``comfy/h3`` (i2v), the tail cut from 1-08's trimmed clip, crf 10 + AAC (before 15m)
  lossless  the same, the tail cut from 1-08's clip as H3 made it, lossless (the product now)
  audio18   lossless, the tail's sound only for its first 18 frames (the community's
            audio_context_length)
  r2v       ``comfy/h3-r2v`` with the locked pictures of 林晚 and the umbrella, not the hall's
            (run10: the scene's picture makes it cut there), lossless tail

The old tail and the scene's picture left out are patches in this process; the rest is the
product. Each take is measured: the guided frames against the tail they should repeat (PSNR
at 0 / 10 / 21), the cut (1-08's last frame against the take's first), the sound either side of
the cut (loudness and the share above 3 kHz: a muffled seam loses the top), and contact sheets.

    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/cont_compare.py --home <run11's dir>
        [--only old,lossless,audio18,r2v] [--work <an earlier copy>] [--label 1-09]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "smoke"))
OUT = REPO / "docs/studio/reports/m5-local-smoke/originals/run15-continuity"
SHEETS = REPO / "docs/studio/reports/m5-local-smoke/run15-continuity"
REAL = "deepseek/v4.1-flash,google/gemini-3.1-flash-lite"
VARIANTS = {
    "old": ("comfy/h3", {"old_tail": True}),
    "lossless": ("comfy/h3", {}),
    "audio18": ("comfy/h3", {"audio": 18}),
    "r2v": ("comfy/h3-r2v", {"no_scene": True}),
}
TAIL = 22


def ff(*args: str) -> subprocess.CompletedProcess[bytes]:
    from drama_series_agent.media.audio import ffmpeg_exe

    return subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostdin", *args],
                          capture_output=True, check=True)  # fmt: skip


def frames(src: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    for p in dest.glob("*.png"):
        p.unlink()
    ff("-loglevel", "error", "-y", "-i", str(src), str(dest / "%04d.png"))
    return sorted(dest.glob("*.png"))


def psnr(a: Path, b: Path) -> float:
    text = ff("-i", str(a), "-i", str(b), "-filter_complex", "[0][1]psnr", "-f", "null", "-")
    found = [x for x in text.stderr.decode().splitlines() if "average:" in x]
    value = found[-1].split("average:", 1)[1].split()[0] if found else "0"
    return 99.0 if value == "inf" else float(value)


def sound(src: Path, start: float, seconds: float) -> tuple[float, float]:
    """Loudness (dBFS) and the share of it above 3 kHz, ``seconds`` from ``start`` (negative:
    from the end)."""

    def rms(extra: list[str]) -> float:
        where = ["-sseof", f"{start}"] if start < 0 else ["-ss", f"{start}"]
        pcm = ff("-loglevel", "error", *where, "-i", str(src), "-t", f"{seconds}", "-map", "0:a:0",
                 *extra, "-ac", "1", "-ar", "16000", "-f", "s16le", "-").stdout  # fmt: skip
        s = memoryview(pcm).cast("h")
        return (sum(x * x for x in s) / max(1, len(s))) ** 0.5

    whole, top = rms([]), rms(["-af", "highpass=f=3000,highpass=f=3000"])
    db = 20 * math.log10(whole / 32768) if whole else -99.0
    return round(db, 1), round(top / whole, 3) if whole else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True)
    ap.add_argument("--work")
    ap.add_argument("--label", default="1-09")
    ap.add_argument("--only", default=",".join(VARIANTS))
    args = ap.parse_args()
    if os.environ.get("DRAMA_LIVE") != "1":
        raise SystemExit("the rewrite and the look are real calls: set DRAMA_LIVE=1")
    OUT.mkdir(parents=True, exist_ok=True)
    SHEETS.mkdir(parents=True, exist_ok=True)
    if args.work:
        work = Path(args.work)
    else:
        work = Path(tempfile.mkdtemp(prefix="drama-cont15-")) / "home"
        shutil.copytree(args.home, work)
    os.environ.update({"DRAMA_HOME": str(work), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1",
                       "DRAMA_REAL_MODELS": REAL})  # fmt: skip

    from fastapi.testclient import TestClient
    from local_assets import V1, Smoke, VramMeter, studio_facts
    from local_storyboard import shots
    from local_video import EP_RECORD, free_comfy, jpeg_sheets, sheet

    from drama_series_agent.api.app import create_app
    from drama_series_agent.core.models_db import LlmCache
    from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget
    from drama_series_agent.pipeline import runs
    from drama_series_agent.pipeline.components import vid

    patch: dict[str, Any] = {}
    file_, tail_clip, pick_refs = vid._file, vid.tail_clip, vid.pick_refs

    def _file(version: Any, role: str) -> Any:
        return None if role == "raw" and patch.get("old_tail") else file_(version, role)

    async def _tail_clip(data: bytes, frames: int, fps: float, **kw: Any) -> bytes:
        kw["audio_frames"] = patch.get("audio", kw.get("audio_frames", TAIL))
        return await tail_clip(data, frames, fps, lossless=not patch.get("old_tail"), **kw)

    def _pick_refs(inputs: Any, draft: Any, limit: Any) -> Any:
        if patch.get("no_scene"):
            refs = [r for r in inputs.context.get("refs") or [] if r["kind"] != "scene"]
            inputs = dataclasses.replace(inputs, context={**inputs.context, "refs": refs})
        return pick_refs(inputs, draft, limit)

    vid._file = _file  # type: ignore[assignment]
    vid.tail_clip = _tail_clip  # type: ignore[assignment]
    vid.pick_refs = _pick_refs  # type: ignore[assignment]

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
        label = args.label
        by_label = shots(smoke)
        shot = by_label[label]
        before = str(shot["tail_from"])  # the shots API names it by label
        if before not in by_label:
            before = next(k for k, v in by_label.items() if v["id"] == before)
        off = {"enabled": False, "on": [], "qa_fail_n": 2, "timeout_s": 600, "to": None}
        off["notify"] = "after"
        body = {"scope": "component", "scope_id": None, "component_id": "vid"}
        client.put(f"{V1}/config/override", json={**body, "data": {"fallback": off}})

        async def clear() -> None:
            from sqlmodel import delete

            async with state.db.session() as s:
                await s.exec(delete(LlmCache).where(LlmCache.key.like("media:%")))  # type: ignore[attr-defined]
                await s.commit()

        def product(x: str) -> dict[str, Any]:
            got: dict[str, Any] = smoke.get(f"/products/{by_label[x]['video_product_id']}")
            return got

        def path(v: dict[str, Any], role: str) -> Path:
            return store.path_for(next(f for f in v["files"] if f["role"] == role)["sha256"])

        prev_p = product(before)
        prev = next(v for v in prev_p["versions"] if v["id"] == prev_p["adopted_version_id"])
        seeds = {x: [v["seed"] for v in product(x)["versions"]] for x in ("1-06", "1-08", "1-09")}
        smoke.say(f"{label} after {before} (adopted {prev['id']}); seeds so far {seeds}")
        pid = shot["video_product_id"]
        old = next(v for v in product(label)["versions"] if v["id"] == record[label]["takes"][0])
        seed = int(old["seed"])
        res_file = work / f"cont15-results-{label}.json"
        results: dict[str, str] = (
            json.loads(res_file.read_text("utf-8")) if res_file.exists() else {}
        )
        for name, (model, knobs) in VARIANTS.items():
            if name not in args.only.split(","):
                continue
            client.portal.call(clear)
            runs.random.randrange = lambda *_: seed  # type: ignore[attr-defined]
            patch.clear()
            patch.update(knobs)

            def start(model: str = model) -> list[str]:
                free_comfy(facts["comfy_url"])
                return [smoke.run(pid, count=1, model=model)["id"]]

            job = smoke.step(name, f"{label} · {name} · {model} · seed {seed}", start)
            if job is None or job["state"] != "succeeded":
                continue
            results[name] = smoke.latest(pid)["id"]
            res_file.write_text(json.dumps(results), "utf-8")
        patch.clear()

        versions = {v["id"]: v for v in product(label)["versions"]}
        tmp = Path(tempfile.mkdtemp(prefix="cont15-frames-"))
        tail = frames(path(prev, "raw"), tmp / "prev")[-TAIL:]
        prev_end = sound(path(prev, "video"), -0.5, 0.5)
        smoke.say(f"   {before} last 0.5 s: {prev_end[0]} dBFS, above 3 kHz {prev_end[1]}")
        firsts = [tail[-1]]
        for name, vid_id in results.items():
            v = versions[vid_id]
            raw = frames(path(v, "raw"), tmp / f"{name}-raw")
            take = frames(path(v, "video"), tmp / f"{name}-take")
            guided = [psnr(tail[i], raw[i]) for i in (0, 10, 21)]
            start_s, whole = sound(path(v, "video"), 0.0, 0.5), sound(path(v, "video"), 0.0, 9)
            pay = v["payload"]
            smoke.say(f"   {name}: guided 0/10/21 {' / '.join(f'{x:.1f}' for x in guided)} dB, "
                      f"cut {psnr(tail[-1], take[0]):.1f} dB; first 0.5 s {start_s[0]} dBFS / "
                      f"{start_s[1]}, whole {whole[0]} dBFS / {whole[1]}; refs {pay.get('refs')}, "
                      f"window {pay.get('window')}, cuts {pay.get('cuts')}")  # fmt: skip
            shutil.copyfile(path(v, "video"), OUT / f"{name}-{label}.mp4")
            shutil.copyfile(path(v, "prompt"), SHEETS / f"prompt-{name}-{label}.txt")
            sheet(path(v, "video"), OUT / f"sheet-{name}-{label}.png")
            firsts.append(take[0])
        ins = [x for f in firsts for x in ("-i", str(f))]
        scaled = "".join(f"[{i}]scale=288:512[s{i}];" for i in range(len(firsts)))
        stack = "".join(f"[s{i}]" for i in range(len(firsts)))
        ff("-loglevel", "error", "-y", *ins, "-filter_complex",
           f"{scaled}{stack}hstack={len(firsts)}", "-pix_fmt", "yuvj420p", "-q:v", "4",
           str(SHEETS / f"cut-{label}.jpg"))  # fmt: skip
        jpeg_sheets(OUT, SHEETS)
    meter.stop()
    (SHEETS / f"report-{label}.txt").write_text("\n".join(smoke.lines) + "\n", "utf-8",
                                                 newline="\n")  # fmt: skip
    print(f"work dir: {work}")
    return 0 if smoke.ok else 1


if __name__ == "__main__":
    sys.exit(main())
