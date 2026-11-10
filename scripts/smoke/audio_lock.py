"""先配音: the dubbed line as a guide vs locked into the audio stream (M5 step 15k).

Today a 先配音再对口型 take hangs the dubbed track on ``MiniMaxH3AddGuide``: a condition, not
the sound itself, so H3 still makes its own sound track and moves the lips to that one. Locked
instead: the track is encoded with H3's audio VAE, swapped into the joint AV latent with a
noise mask of 0 (``LTXVConcatAVLatent`` keeps the video stream and replaces the audio one;
``fit_audio`` leaves a shorter track's tail to be made), and only the picture is generated.

On a copy of run11's data directory 1-04 is switched to 先配音 (impact preview, confirmed
again), then made twice on run11's seed: A as the studio does it, B with the lock (this
process patches the graph; the product is not changed). Each is measured: where the loud part
is, how close its sound is to the dub (envelope correlation), and the mouth around the line.

    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/audio_lock.py --home <run11's dir>
        [--label 1-04] [--work <an earlier copy>] [--only a,b]
"""

from __future__ import annotations

import argparse
import asyncio
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
OUT = REPO / "docs/studio/reports/m5-local-smoke/originals/run14-audio-lock"
SHEETS = REPO / "docs/studio/reports/m5-local-smoke/run14-audio-lock"
REAL = "deepseek/v4.1-flash,google/gemini-3.1-flash-lite"
PATCH: dict[str, Any] = {"lock": False}


def install_patch() -> None:
    from drama_series_agent.modelhub.adapters import comfyui as cm

    orig = cm.ComfyUIAdapter._one

    async def _one(self, client, socket, url, wf, graph, progress):  # type: ignore[no-untyped-def]
        g = graph
        by_title = {x.get("_meta", {}).get("title"): n for n, x in g.items()}
        audio, guide = by_title.get("Dialogue audio"), by_title.get("Dialogue guide")
        if PATCH["lock"] and audio and guide:
            i2v, avae = by_title["Image to video"], by_title["Audio VAE"]
            sample = by_title["Sample"]
            source = g[guide]["inputs"]["positive"]
            for node in g.values():  # the guide goes; what read it reads what it read
                for k, v in node["inputs"].items():
                    if v == [guide, 0]:
                        node["inputs"][k] = source
            del g[guide]
            g["960"] = {"class_type": "VAEEncodeAudio",
                        "inputs": {"audio": [audio, 0], "vae": [avae, 0]}}  # fmt: skip
            g["961"] = {"class_type": "SolidMask",
                        "inputs": {"value": 0.0, "width": 64, "height": 64}}  # fmt: skip
            g["962"] = {"class_type": "SetLatentNoiseMask",
                        "inputs": {"samples": ["960", 0], "mask": ["961", 0]}}  # fmt: skip
            av = {"video_latent": [i2v, 1], "audio_latent": ["962", 0]}
            g["963"] = {"class_type": "LTXVConcatAVLatent", "inputs": av}
            g[sample]["inputs"]["latent_image"] = ["963", 0]
            (OUT / "graph-lock.json").write_text(json.dumps(g, ensure_ascii=False, indent=1))
        return await orig(self, client, socket, url, wf, graph, progress)

    cm.ComfyUIAdapter._one = _one  # type: ignore[method-assign]


def ff(*args: str, **kw: Any) -> subprocess.CompletedProcess[bytes]:
    from drama_series_agent.media.audio import ffmpeg_exe

    return subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostdin", *args],
                          capture_output=True, check=True, **kw)  # fmt: skip


def envelope(path: Path, seconds: float | None = None) -> list[float]:
    """Loudness every 50 ms."""
    pcm = ff("-loglevel", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "16000",
             *(["-t", f"{seconds}"] if seconds else []), "-f", "s16le", "-").stdout  # fmt: skip
    s = memoryview(pcm).cast("h")
    return [(sum(x * x for x in s[i : i + 800]) / 800) ** 0.5 for i in range(0, len(s) - 799, 800)]


def correlation(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True))
    va = sum((x - ma) ** 2 for x in a) ** 0.5
    vb = sum((y - mb) ** 2 for y in b) ** 0.5
    return round(cov / (va * vb), 3) if va and vb else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True)
    ap.add_argument("--work")
    ap.add_argument("--label", default="1-04")
    ap.add_argument("--only", default="a,b")
    args = ap.parse_args()
    if os.environ.get("DRAMA_LIVE") != "1":
        raise SystemExit("the rewrite and the look are real calls: set DRAMA_LIVE=1")
    OUT.mkdir(parents=True, exist_ok=True)
    SHEETS.mkdir(parents=True, exist_ok=True)
    if args.work:
        work = Path(args.work)
    else:
        work = Path(tempfile.mkdtemp(prefix="drama-lock-")) / "home"
        shutil.copytree(args.home, work)
    os.environ.update({"DRAMA_HOME": str(work), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1",
                       "DRAMA_REAL_MODELS": REAL})  # fmt: skip

    from fastapi.testclient import TestClient
    from local_assets import V1, Smoke, VramMeter, studio_facts
    from local_storyboard import shots
    from local_video import EP_RECORD, free_comfy, sheet

    from drama_series_agent.api.app import create_app
    from drama_series_agent.core.models_db import LlmCache
    from drama_series_agent.media.video import _speech
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
        label = args.label
        shot = shots(smoke)[label]
        pid = shot["video_product_id"]
        old = next(
            v for v in smoke.get(f"/products/{pid}")["versions"]
            if v["id"] == record[label]["takes"][0]
        )  # fmt: skip
        if shot["audio_mode"] != "tts":
            target = {"kind": "shot_edit", "target_id": shot["id"], "patch": {"audio_mode": "tts"}}
            impact = smoke.post("/impact/preview", target)
            smoke.post("/impact/apply", {"impact_id": impact["id"], "action": "mark"})
            client.patch(f"{V1}/shots/{shot['id']}", json={"confirmed": True}).raise_for_status()
            smoke.post("/gates/storyboard/confirm", {"scope_id": "demo-e1"})
            smoke.say(f"   {label} audio_mode → {shots(smoke)[label]['audio_mode']}")
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

        res_file = work / "lock-results.json"
        results: dict[str, str] = (
            json.loads(res_file.read_text("utf-8")) if res_file.exists() else {}
        )
        for name, lock in (("a", False), ("b", True)):
            if name not in args.only.split(","):
                continue
            client.portal.call(clear)
            runs.random.randrange = lambda *_: int(old["seed"])  # type: ignore[attr-defined]
            PATCH["lock"] = lock

            def start() -> list[str]:
                free_comfy(facts["comfy_url"])
                return [smoke.run(pid, count=1, model="comfy/h3")["id"]]

            what = "台词锁进音轨" if lock else "台词挂引导（现在的做法）"
            job = smoke.step(name, f"{label} 先配音 · {what} · seed {old['seed']}", start)
            if job is None or job["state"] != "succeeded":
                continue
            results[name] = smoke.latest(pid)["id"]
            res_file.write_text(json.dumps(results), "utf-8")

        versions = {v["id"]: v for v in smoke.get(f"/products/{pid}")["versions"]}
        for name, vid in results.items():
            v = versions[vid]
            clip = path(v, "video")
            dub = store.path_for(v["params"]["request"]["dialogue_audio"])
            shutil.copyfile(clip, OUT / f"{name}-{label}.mp4")
            shutil.copyfile(dub, OUT / f"dub-{label}.wav")
            span = _speech(clip)
            # The take lost its first 0.3 s; the dub starts with the take.
            r = correlation(envelope(clip), envelope(dub)[6:])
            pay = v["payload"]
            smoke.say(f"   {name}: loud {span}, sound vs dub envelope r = {r}, "
                      f"window {pay.get('window')}, cuts {pay.get('cuts')}")  # fmt: skip
            sheet(clip, OUT / f"sheet-{name}-{label}.png")
            if span:
                t0, t1 = max(0.0, span[0] - 0.3), span[1] + 0.3
                ff("-loglevel", "error", "-y", "-i", str(clip), "-vf",
                   f"select='between(t,{t0:.2f},{t1:.2f})*not(mod(n,3))',"
                   "crop=iw/2:ih/5:iw/4:ih*0.35,scale=192:-1,tile=8x2",
                   "-frames:v", "1", str(OUT / f"mouth-{name}-{label}.png"))  # fmt: skip
        from local_video import jpeg_sheets

        jpeg_sheets(OUT, SHEETS)
        for png in OUT.glob("mouth-*.png"):
            ff("-loglevel", "error", "-y", "-i", str(png), "-q:v", "4",
               str(SHEETS / f"{png.stem}.jpg"))  # fmt: skip
    meter.stop()
    (SHEETS / "report.txt").write_text("\n".join(smoke.lines) + "\n", "utf-8", newline="\n")
    print(f"work dir: {work}")
    return 0 if smoke.ok else 1


if __name__ == "__main__":
    asyncio.set_event_loop_policy(None)
    sys.exit(main())
