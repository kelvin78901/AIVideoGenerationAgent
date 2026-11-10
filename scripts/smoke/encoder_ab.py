"""H3's text encoder: nvfp4_awq (today) against int8_convrot (M5 step 15l).

The research (``reports/m5-h3-research.md``) suggests the 4-bit encoder may mispronounce
Chinese lines and blur fine actions. On a copy of run11's data directory each shot is made
twice on the seed of its run11 first take, through the studio as it is now; the only change
is the ``Text encoder`` node's ``clip_name``, patched in this process (the product does not
change). The prompt rewrite and the first-frame look come from the cache the second time, so
both takes get the same words.

Each take: still opening, where the loud part is (the line), cuts inside, and a side-by-side
clip with both sound tracks one after the other for listening (A, then B).

    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/encoder_ab.py --home <run11's dir>
        [--shots 1-04,1-08] [--only nvfp4,int8] [--work <an earlier copy>]
"""

from __future__ import annotations

import argparse
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
OUT = REPO / "docs/studio/reports/m5-local-smoke/originals/run16-encoder"
SHEETS = REPO / "docs/studio/reports/m5-local-smoke/run16-encoder"
REAL = "deepseek/v4.1-flash,google/gemini-3.1-flash-lite"
ENCODERS = {
    "nvfp4": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "int8": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
}
PATCH: dict[str, Any] = {"clip": None}


def install_patch() -> None:
    from drama_series_agent.modelhub.adapters import comfyui as cm

    orig = cm.ComfyUIAdapter._one

    async def _one(self, client, socket, url, wf, graph, progress):  # type: ignore[no-untyped-def]
        for node in graph.values():
            if node.get("_meta", {}).get("title") == "Text encoder" and PATCH["clip"]:
                node["inputs"]["clip_name"] = PATCH["clip"]
        return await orig(self, client, socket, url, wf, graph, progress)

    cm.ComfyUIAdapter._one = _one  # type: ignore[method-assign]


def ff(*args: str) -> None:
    from drama_series_agent.media.audio import ffmpeg_exe

    subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args],
                   capture_output=True, check=True)  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True)
    ap.add_argument("--work")
    ap.add_argument("--shots", default="1-04,1-08")
    ap.add_argument("--only", default="nvfp4,int8")
    args = ap.parse_args()
    if os.environ.get("DRAMA_LIVE") != "1":
        raise SystemExit("the rewrite and the look are real calls: set DRAMA_LIVE=1")
    OUT.mkdir(parents=True, exist_ok=True)
    SHEETS.mkdir(parents=True, exist_ok=True)
    if args.work:
        work = Path(args.work)
    else:
        work = Path(tempfile.mkdtemp(prefix="drama-encoder-")) / "home"
        shutil.copytree(args.home, work)
    os.environ.update({"DRAMA_HOME": str(work), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1",
                       "DRAMA_REAL_MODELS": REAL})  # fmt: skip

    from fastapi.testclient import TestClient
    from local_assets import V1, Smoke, VramMeter, studio_facts
    from local_storyboard import shots
    from local_video import EP_RECORD, free_comfy, jpeg_sheets, sheet
    from retake_compare import measure

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
        off = {"enabled": False, "on": [], "qa_fail_n": 2, "timeout_s": 900, "to": None}
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

        res_file = work / "encoder-results.json"
        results: dict[str, dict[str, str]] = (
            json.loads(res_file.read_text("utf-8")) if res_file.exists() else {}
        )
        for label in args.shots.split(","):
            pid = by_label[label]["video_product_id"]
            old = next(
                v for v in smoke.get(f"/products/{pid}")["versions"]
                if v["id"] == record[label]["takes"][0]
            )  # fmt: skip
            seed = int(old["seed"])
            for name in args.only.split(","):
                client.portal.call(clear)
                runs.random.randrange = lambda *_, s=seed: s  # type: ignore[attr-defined]
                PATCH["clip"] = ENCODERS[name]

                def start(pid: str = pid) -> list[str]:
                    free_comfy(facts["comfy_url"])
                    return [smoke.run(pid, count=1, model="comfy/h3")["id"]]

                job = smoke.step(f"{label}-{name}", f"{label} · {ENCODERS[name]} · seed {seed}",
                                 start)  # fmt: skip
                if job is None or job["state"] != "succeeded":
                    continue
                results.setdefault(label, {})[name] = smoke.latest(pid)["id"]
                res_file.write_text(json.dumps(results), "utf-8")
        PATCH["clip"] = None

        for label, made in results.items():
            pid = by_label[label]["video_product_id"]
            versions = {v["id"]: v for v in smoke.get(f"/products/{pid}")["versions"]}
            clips = {}
            for name, vid_id in made.items():
                v = versions[vid_id]
                clip = path(v, "video")
                m = measure(clip.read_bytes(), 24.0)
                same = hashlib.sha256(path(v, "prompt").read_bytes()).hexdigest()[:8]
                smoke.say(f"   {label} {name:5}: {m['s']}s, still opening {m['still_s']}s, "
                          f"loud {m['loud']}, cuts {m['cuts']}, "
                          f"window {v['payload'].get('window')},"
                          f" prompt {same}")  # fmt: skip
                shutil.copyfile(clip, OUT / f"{name}-{label}.mp4")
                shutil.copyfile(path(v, "prompt"), SHEETS / f"prompt-{name}-{label}.txt")
                sheet(clip, OUT / f"sheet-{name}-{label}.png")
                clips[name] = clip
            if len(clips) == 2:
                a, b = clips["nvfp4"], clips["int8"]
                # Side by side (A left, B right), A's sound and then B's: listen to both.
                ff("-i", str(a), "-i", str(b), "-filter_complex",
                   "[0:v][1:v]hstack[v];[v]split[v1][v2];[v1][v2]concat=n=2:v=1:a=0[vv];"
                   "[0:a][1:a]concat=n=2:v=0:a=1[aa]",
                   "-map", "[vv]", "-map", "[aa]", "-c:v", "libx264", "-crf", "20",
                   "-pix_fmt", "yuv420p", "-c:a", "aac", str(OUT / f"ab-{label}.mp4"))  # fmt: skip
        jpeg_sheets(OUT, SHEETS)
    meter.stop()
    (SHEETS / "report.txt").write_text("\n".join(smoke.lines) + "\n", "utf-8", newline="\n")
    print(f"work dir: {work}")
    return 0 if smoke.ok else 1


if __name__ == "__main__":
    sys.exit(main())
