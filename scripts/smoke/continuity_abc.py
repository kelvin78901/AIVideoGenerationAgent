"""Continuity experiment (M5 step 15c-2, Kelvin 2026-11-08): 1-06 -> (1-07 insert) -> 1-08 -> 1-09.

A  as the studio does it: the continuing shot starts from the adopted take's last frame
   (the episode run's adopted takes, nothing new is made).
B  "continue from the end of the previous clip" (PLAN): the previous clip's last 22 frames and
   their sound anchored at frame 0 with MiniMaxH3AddGuide (official node), the first-frame
   anchor removed; the clip asks 22 frames more and the cut drops them.
C  one long take: 1-06's keyframe, 15 s, one prompt with three beats (drafted from the three
   shots' compiled prompts, rewritten by the studio's vprompt on DeepSeek); the cut puts the
   1-07 insert after its first 5 s.

Same seeds as A, same inputs, same rewritten prompts for B (the rewrite cache is kept; the
media cache is cleared, or B would get A's clips back). Runs on a COPY of the episode's data
directory. Experimental graphs only live in this process (a patch on ComfyUIAdapter._one).

    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/continuity_abc.py
        --home <the episode run's data dir> [--only b,c,cut] [--work <an earlier copy>]
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

OUT = REPO / "docs/studio/reports/m5-local-smoke/originals/run9-continuity"
SHEETS = REPO / "docs/studio/reports/m5-local-smoke/run9-continuity"
TAIL_FRAMES = 22  # H3 clip guides: 5, 22, 39 ... (17k + 5) frames
FPS = 24
LONG_S = 15.0
REWRITE_MODEL = "deepseek/v4.1-flash"
W, H = 768, 1344

PATCH: dict[str, Any] = {"label": None, "tail": None, "seconds": None}


def ff(*args: str) -> None:
    from drama_series_agent.media.audio import ffmpeg_exe

    subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args],
                   check=True)  # fmt: skip


def tail_clip(src: Path, dest: Path) -> None:
    """The last TAIL_FRAMES frames of ``src`` with their sound."""
    from drama_series_agent.media.video import probe

    info = asyncio.run(probe(src.read_bytes()))
    frames = round(info.duration_s * FPS)
    start = max(0, frames - TAIL_FRAMES) / FPS
    ff("-ss", f"{start:.4f}", "-i", str(src), "-frames:v", str(TAIL_FRAMES),
       "-t", f"{TAIL_FRAMES / FPS:.4f}", "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", str(dest))  # fmt: skip


def install_patch() -> None:
    from drama_series_agent.modelhub.adapters import comfyui as cm

    orig = cm.ComfyUIAdapter._one

    async def _one(self, client, socket, url, wf, graph, progress):  # type: ignore[no-untyped-def]
        g = graph
        by_class = {}
        for nid, node in g.items():
            by_class.setdefault(node["class_type"], []).append(nid)
        if PATCH["seconds"]:
            for nid in by_class.get("PrimitiveFloat", []):
                if g[nid].get("_meta", {}).get("title") == "Duration":
                    g[nid]["inputs"]["value"] = float(PATCH["seconds"])
        if PATCH["tail"]:
            data = await asyncio.to_thread(Path(PATCH["tail"]).read_bytes)
            name = await self._upload(
                client, f"tail-{hashlib.sha256(data).hexdigest()[:16]}.mp4", data, "video/mp4"
            )
            i2v = g[by_class["MiniMaxH3ImageToVideo"][0]]
            i2v["inputs"].pop("first_frame", None)  # the clip is the start now
            guider = g[by_class["BasicGuider"][0]]
            sampler = g[by_class["SamplerCustomAdvanced"][0]]
            vaes = {g[n]["inputs"]["vae_name"]: n for n in by_class["VAELoader"]}
            vvae = next(n for k, n in vaes.items() if "video" in k)
            avae = next(n for k, n in vaes.items() if "audio" in k)
            g["900"] = {"class_type": "LoadVideo", "inputs": {"file": name},
                        "_meta": {"title": "Tail clip"}}  # fmt: skip
            g["901"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["900", 0]},
                        "_meta": {"title": "Tail parts"}}  # fmt: skip
            g["902"] = {
                "class_type": "MiniMaxH3AddGuide",
                "inputs": {
                    "positive": guider["inputs"]["conditioning"],
                    "latent": sampler["inputs"]["latent_image"],
                    "frame_idx": 0,
                    "vae": [vvae, 0],
                    "audio_vae": [avae, 0],
                    "image": ["901", 0],
                    "audio": ["901", 1],
                },
                "_meta": {"title": "Tail guide"},
            }
            guider["inputs"]["conditioning"] = ["902", 0]
        (OUT / f"graph-{PATCH['label']}.json").write_text(
            json.dumps(g, ensure_ascii=False, indent=1), "utf-8"
        )
        return await orig(self, client, socket, url, wf, graph, progress)

    cm.ComfyUIAdapter._one = _one  # type: ignore[method-assign]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True, help="the episode run's data directory")
    ap.add_argument("--work", help="a copy made by an earlier run (reused)")
    ap.add_argument("--only", default="b,c,cut")
    args = ap.parse_args()
    only = set(args.only.split(","))
    if os.environ.get("DRAMA_LIVE") != "1":
        raise SystemExit("C rewrites a prompt on DeepSeek (money): set DRAMA_LIVE=1")
    OUT.mkdir(parents=True, exist_ok=True)
    SHEETS.mkdir(parents=True, exist_ok=True)
    if args.work:
        work = Path(args.work)
    else:
        work = Path(tempfile.mkdtemp(prefix="drama-cont-")) / "home"
        shutil.copytree(args.home, work)
    os.environ.update({"DRAMA_HOME": str(work), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1",
                       "DRAMA_REAL_MODELS": REWRITE_MODEL})  # fmt: skip

    from fastapi.testclient import TestClient
    from local_assets import Smoke, VramMeter, studio_facts
    from local_storyboard import shots
    from local_video import EP_RECORD, free_comfy, no_video_fallback, sheet

    from drama_series_agent.api.app import create_app
    from drama_series_agent.core.models_db import LlmCache
    from drama_series_agent.media.video import probe
    from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget
    from drama_series_agent.pipeline import runs

    install_patch()
    facts = studio_facts("http://127.0.0.1:8000")
    record = json.loads((Path(args.home) / EP_RECORD).read_text("utf-8"))

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
        store = state.store
        smoke.say(f"continuity A/B/C · work dir {work}")

        def clear_media_cache() -> None:
            from sqlmodel import delete

            async def go() -> None:
                async with state.db.session() as s:
                    await s.exec(delete(LlmCache).where(LlmCache.key.like("media:%")))  # type: ignore[attr-defined]
                    await s.commit()

            client.portal.call(go)

        def version(label: str, vid: str) -> dict[str, Any]:
            pid = shots(smoke)[label]["video_product_id"]
            return next(v for v in smoke.get(f"/products/{pid}")["versions"] if v["id"] == vid)

        def adopted(label: str) -> dict[str, Any]:
            pid = shots(smoke)[label]["video_product_id"]
            p = smoke.get(f"/products/{pid}")
            return next(v for v in p["versions"] if v["id"] == p["adopted_version_id"])

        def path(v: dict[str, Any], role: str) -> Path:
            return store.path_for(next(f for f in v["files"] if f["role"] == role)["sha256"])

        def one_take(label: str, seed: int, title: str, **body: Any) -> dict[str, Any] | None:
            pid = shots(smoke)[label]["video_product_id"]
            runs.random.randrange = lambda *_: seed  # type: ignore[attr-defined]
            clear_media_cache()

            def start() -> list[str]:
                free_comfy(facts["comfy_url"])
                return [smoke.run(pid, count=1, **body)["id"]]

            job = smoke.step(PATCH["label"], title, start)
            if job is None or job["state"] != "succeeded":
                return None
            v = smoke.latest(pid)
            raw = path(v, "raw")
            info = asyncio.run(probe(raw.read_bytes()))
            smoke.say(f"   seed {v['seed']}, raw {info.w}x{info.h} {info.duration_s:.2f}s, "
                      f"sound {info.has_audio}, model {v['model_key']}")  # fmt: skip
            shutil.copyfile(raw, OUT / f"{PATCH['label']}.mp4")
            sheet(raw, OUT / f"sheet-{PATCH['label']}.png")
            return v

        a = {x: adopted(x) for x in ("1-06", "1-07", "1-08", "1-09")}
        for x, v in a.items():
            smoke.say(f"   A {x}: {v['id']} seed {v['seed']} {v['model_key']}")
        no_video_fallback(smoke)
        results: dict[str, Any] = {}
        res_file = work / "cont-results.json"
        if res_file.exists():
            results = json.loads(res_file.read_text("utf-8"))

        if "b" in only:
            prev = path(a["1-06"], "video")
            for label in ("1-08", "1-09"):
                tail = OUT / f"tail-before-{label}.mp4"
                tail_clip(prev, tail)
                asked = float(a[label]["payload"].get("asked_s") or record[label]["seconds"])
                PATCH.update(label=f"B-{label}", tail=str(tail),
                             seconds=asked + TAIL_FRAMES / FPS)  # fmt: skip
                what = f"B {label}: 上一条最后 {TAIL_FRAMES} 帧 + 声音钉在开头，种子同 A"
                v = one_take(label, int(a[label]["seed"]), what)
                PATCH.update(tail=None, seconds=None)
                if v is None:
                    break
                smoke.post(f"/versions/{v['id']}/adopt")  # 1-09 continues B's 1-08
                results[f"B-{label}"] = v["id"]
                prev = path(v, "raw")
            res_file.write_text(json.dumps(results), "utf-8")

        if "c" in only:
            beats = []
            spans = (("1-06", 0, 5), ("1-08", 5, 11), ("1-09", 11, 15))
            for label, t0, t1 in spans:
                pid = shots(smoke)[label]["video_product_id"]
                compiled = smoke.get(f"/products/{pid}")["prompt"]["compiled"]
                beats.append(f"【{t0}–{t1} 秒】\n{compiled.strip()}")
            draft = (
                f"一镜到底的长镜头，共 {LONG_S:.0f} 秒，不切镜，机位跟着林晚在出租屋门口，"
                "按时间分三拍连续演完（中间不跳、不换景）：\n\n" + "\n\n".join(beats)
            )
            (OUT / "C-draft.txt").write_text(draft, "utf-8")
            PATCH.update(label="C-long", seconds=LONG_S)
            v = one_take("1-06", int(a["1-06"]["seed"]),
                         f"C 1-06+1-08+1-09 一条 {LONG_S:.0f} 秒，种子同 A 的 1-06",
                         compiled=draft)  # fmt: skip
            PATCH.update(seconds=None)
            if v is not None:
                results["C-long"] = v["id"]
                prompt = path(v, "prompt").read_text("utf-8")
                (OUT / "C-prompt-as-sent.txt").write_text(prompt, "utf-8")
                smoke.say(f"   C prompt: {len(prompt.split())} words, rewritten by "
                          f"{v['payload'].get('prompt_rewrite')}")  # fmt: skip
            res_file.write_text(json.dumps(results), "utf-8")

        if "cut" in only:
            # Shots in the chain use their whole clip: H3 rounds a clip up to 17k + 5 frames,
            # and the next shot starts from the clip's LAST frame, so cutting a clip to its
            # shot's length would hide a jump at every continuous cut (A and B alike).
            segs: dict[str, list[tuple[Path, float, float | None]]] = {}
            vid = {x: path(v, "video") for x, v in a.items()}
            lens = {x: float(record[x]["seconds"]) for x in a}
            segs["A"] = [(vid["1-06"], 0.0, None), (vid["1-07"], 0.0, lens["1-07"]),
                         (vid["1-08"], 0.0, None), (vid["1-09"], 0.0, None)]  # fmt: skip
            if "B-1-08" in results and "B-1-09" in results:
                b8 = path(version("1-08", results["B-1-08"]), "raw")
                b9 = path(version("1-09", results["B-1-09"]), "raw")
                skip = TAIL_FRAMES / FPS  # those frames are the previous clip's tail
                segs["B"] = [(vid["1-06"], 0.0, None), (vid["1-07"], 0.0, lens["1-07"]),
                             (b8, skip, None), (b9, skip, None)]  # fmt: skip
            if "C-long" in results:
                c = path(version("1-06", results["C-long"]), "video")
                segs["C"] = [(c, 0.0, 5.0), (vid["1-07"], 0.0, lens["1-07"]),
                             (c, 5.0, None)]  # fmt: skip
            made = []
            for name, parts in segs.items():
                dest = OUT / f"chain-{name}.mp4"
                cut_parts(parts, dest)
                info = asyncio.run(probe(dest.read_bytes()))
                smoke.say(f"   chain-{name}.mp4 {info.duration_s:.2f}s")
                sheet(dest, OUT / f"sheet-chain-{name}.png")
                made.append(name)
            if len(made) > 1:
                labelled = []
                for name in made:
                    labelled += ["-i", str(OUT / f"chain-{name}.mp4")]
                font = "C\\:/Windows/Fonts/arial.ttf"
                chains = "".join(
                    f"[{i}:v]drawtext=fontfile='{font}':text='{n}':fontsize=64:fontcolor=white:"
                    f"box=1:boxcolor=black@0.5:x=20:y=20[s{i}];"
                    for i, n in enumerate(made)
                )
                inputs = "".join(f"[s{i}]" for i in range(len(made)))
                ff(*labelled, "-filter_complex",
                   f"{chains}{inputs}hstack=inputs={len(made)}[v]", "-map", "[v]",
                   "-map", "0:a", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-shortest", str(OUT / "chain-side-by-side.mp4"))  # fmt: skip
                smoke.say(f"   chain-side-by-side.mp4 ({' | '.join(made)}; sound from {made[0]})")
            for png in OUT.glob("sheet-*.png"):
                ff("-i", str(png), "-q:v", "4", str(SHEETS / f"{png.stem}.jpg"))
            for txt in ("C-draft.txt", "C-prompt-as-sent.txt"):
                if (OUT / txt).exists():
                    shutil.copyfile(OUT / txt, SHEETS / txt)
        calls = smoke.get("/dev/model-calls", limit=500)
        paid = sum(
            float(c.get("cost_usd") or 0) for c in calls if c.get("model_key") == REWRITE_MODEL
        )
        smoke.say(f"   DeepSeek in this work dir (incl. the episode run's): ${paid:.4f}")
    meter.stop()
    (SHEETS / "report.txt").write_text("\n".join(smoke.lines) + "\n", "utf-8", newline="\n")
    print(f"work dir: {work}")
    return 0 if smoke.ok else 1


def cut_parts(parts: list[tuple[Path, float, float | None]], dest: Path) -> None:
    """Pieces (file, start, length; None = to the end) one after another, at the draft size."""
    from drama_series_agent.media.video import probe

    args: list[str] = []
    graph = []
    for i, (src, start, wanted) in enumerate(parts):
        args += ["-i", str(src)]
        whole = asyncio.run(probe(src.read_bytes())).duration_s
        length = (whole - start) if wanted is None else min(wanted, whole - start)
        end = start + length
        graph.append(
            f"[{i}:v]trim={start:.4f}:{end:.4f},setpts=PTS-STARTPTS,"
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}[v{i}];"
            f"[{i}:a]atrim={start:.4f}:{end:.4f},asetpts=PTS-STARTPTS,aresample=48000,"
            f"aformat=channel_layouts=stereo,apad=whole_dur={length:.4f}[a{i}];"
        )
    joined = "".join(f"[v{i}][a{i}]" for i in range(len(parts)))
    ff(*args, "-filter_complex", "".join(graph) + f"{joined}concat=n={len(parts)}:v=1:a=1[v][a]",
       "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", str(dest))  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
