"""1-09 with or without its locked references (M5 step 15f, Kelvin 2026-11-08).

1-09 (close-up: 林晚 picks up the umbrella at the door; continues 1-08; no spoken line) went to
``h3-i2v`` in the episode run, which takes no reference pictures: the umbrella came out black
in every take. Now both local H3 workflows take the shot before's tail (step 15e), so the
question is which one a silent shot with locked references should go to:

  i2v  ``comfy/h3``      the tail of 1-08 + the prompt, no references (today's default)
  r2v  ``comfy/h3-r2v``  the tail of 1-08 + 1-08's last frame as <Picture 1> + the locked
                         pictures of 林晚, the umbrella and the hall
  r2v-noscene            the same without the scene's picture (the tail shows the place):
                         a patch on the references this process sends, not in the product

Both made by the studio itself (no patched graph), the same seed (the episode run's first 1-09
take), on a copy of run9's data directory where B's 1-08 is adopted. The prompt rewrite goes to
DeepSeek (r2v's layout differs, so it is asked once; i2v's is cached from run9).

    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/refs_compare.py
        --home <run9's data dir> [--only i2v,r2v,cut] [--work <an earlier copy>]

One take a run keeps each step under 10 minutes in the foreground (``--only i2v``, then
``--work <copy> --only r2v``, then ``--only cut``).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "smoke"))

OUT = REPO / "docs/studio/reports/m5-local-smoke/originals/run10-refs"
SHEETS = REPO / "docs/studio/reports/m5-local-smoke/run10-refs"
REWRITE_MODEL = "deepseek/v4.1-flash"
MODELS = {"i2v": "comfy/h3", "r2v": "comfy/h3-r2v", "r2v-noscene": "comfy/h3-r2v"}
LABEL = "1-09"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True, help="run9's data directory (B's 1-08 adopted)")
    ap.add_argument("--work", help="a copy made by an earlier run (reused)")
    ap.add_argument("--only", default="i2v,r2v,cut")
    args = ap.parse_args()
    only = set(args.only.split(","))
    if os.environ.get("DRAMA_LIVE") != "1":
        raise SystemExit("the prompt rewrite goes to DeepSeek (money): set DRAMA_LIVE=1")
    OUT.mkdir(parents=True, exist_ok=True)
    SHEETS.mkdir(parents=True, exist_ok=True)
    if args.work:
        work = Path(args.work)
    else:
        work = Path(tempfile.mkdtemp(prefix="drama-refs-")) / "home"
        shutil.copytree(args.home, work)
    os.environ.update({"DRAMA_HOME": str(work), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1",
                       "DRAMA_REAL_MODELS": REWRITE_MODEL})  # fmt: skip

    from continuity_abc import cut_parts, ff
    from fastapi.testclient import TestClient
    from local_assets import V1, Smoke, VramMeter, studio_facts
    from local_storyboard import shots
    from local_video import EP_RECORD, free_comfy, sheet

    from drama_series_agent.api.app import create_app
    from drama_series_agent.core.models_db import LlmCache
    from drama_series_agent.media.video import probe
    from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget
    from drama_series_agent.pipeline import runs
    from drama_series_agent.pipeline.components import vid

    pick_refs = vid.pick_refs
    no_scene = {"on": False}

    def patched(inputs: Any, draft: Any, limit: Any) -> Any:
        if no_scene["on"]:
            refs = [r for r in inputs.context.get("refs") or [] if r["kind"] != "scene"]
            inputs = dataclasses.replace(inputs, context={**inputs.context, "refs": refs})
        return pick_refs(inputs, draft, limit)

    vid.pick_refs = patched  # type: ignore[assignment]

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
        smoke.expected_api.add(REWRITE_MODEL)
        store = state.store
        smoke.say(f"1-09 with or without references · work dir {work}")

        def clear_media_cache() -> None:
            from sqlmodel import delete

            async def go() -> None:
                async with state.db.session() as s:
                    await s.exec(delete(LlmCache).where(LlmCache.key.like("media:%")))  # type: ignore[attr-defined]
                    await s.commit()

            client.portal.call(go)

        def product(label: str) -> dict[str, Any]:
            got: dict[str, Any] = smoke.get(f"/products/{shots(smoke)[label]['video_product_id']}")
            return got

        def version(label: str, vid: str) -> dict[str, Any]:
            return next(v for v in product(label)["versions"] if v["id"] == vid)

        def adopted(label: str) -> dict[str, Any]:
            p = product(label)
            return next(v for v in p["versions"] if v["id"] == p["adopted_version_id"])

        def path(v: dict[str, Any], role: str) -> Path:
            return store.path_for(next(f for f in v["files"] if f["role"] == role)["sha256"])

        # Fallback off (a failed take is not made on the Mock API); the timeout grows with the
        # clip on its own now (step 15d).
        off = {"enabled": False, "on": [], "qa_fail_n": 2, "timeout_s": 600, "to": None}
        off["notify"] = "after"
        put = client.put(f"{V1}/config/override", json={"scope": "component", "scope_id": None,
                         "component_id": "vid", "data": {"fallback": off}})  # fmt: skip
        put.raise_for_status()
        b8 = adopted("1-08")
        smoke.say(f"   1-08 adopted: {b8['id']} (run9's B), {b8['model_key']}")
        seed = int(version(LABEL, record[LABEL]["takes"][0])["seed"])
        res_file = work / "refs-results.json"
        results: dict[str, str] = (
            json.loads(res_file.read_text("utf-8")) if res_file.exists() else {}
        )

        for name, model in MODELS.items():
            if name not in only:
                continue
            pid = shots(smoke)[LABEL]["video_product_id"]
            runs.random.randrange = lambda *_: seed  # type: ignore[attr-defined]
            no_scene["on"] = name == "r2v-noscene"
            clear_media_cache()

            def start(pid: str = pid, model: str = model) -> list[str]:
                free_comfy(facts["comfy_url"])
                return [smoke.run(pid, count=1, model=model)["id"]]

            job = smoke.step(name, f"{LABEL} on {model}, seed {seed}, tail of 1-08", start)
            if job is None or job["state"] != "succeeded":
                continue
            v = smoke.latest(pid)
            sent = (v.get("params") or {}).get("request") or {}
            raw, clip = path(v, "raw"), path(v, "video")
            info = asyncio.run(probe(raw.read_bytes()))
            cut = asyncio.run(probe(clip.read_bytes()))
            smoke.say(f"   seed {v['seed']}, raw {info.w}x{info.h} {info.duration_s:.2f}s, "
                      f"take {cut.duration_s:.2f}s, sound {info.has_audio}, "
                      f"tail_frames {sent.get('tail_frames')}, refs {v['payload'].get('refs')}, "
                      f"rewritten by {v['payload'].get('prompt_rewrite')}")  # fmt: skip
            shutil.copyfile(clip, OUT / f"{name}-{LABEL}.mp4")
            shutil.copyfile(path(v, "prompt"), OUT / f"{name}-prompt.txt")
            sheet(clip, OUT / f"sheet-{name}-{LABEL}.png")
            results[name] = v["id"]
            res_file.write_text(json.dumps(results), "utf-8")

        if "cut" in only:
            # 1-06 → 1-07 → 1-08 (B) → 1-09: whole takes (the tail frames are already off).
            first = {x: path(version(x, record[x]["takes"][0]), "video") for x in ("1-06", "1-07")}
            made = []
            for name in MODELS:
                if name not in results:
                    continue
                parts = [(first["1-06"], 0.0, None),
                         (first["1-07"], 0.0, float(record["1-07"]["seconds"])),
                         (path(b8, "raw"), 22 / 24, None),
                         (path(version(LABEL, results[name]), "video"), 0.0, None)]  # fmt: skip
                dest = OUT / f"chain-{name}.mp4"
                cut_parts(parts, dest)
                sheet(dest, OUT / f"sheet-chain-{name}.png")
                made.append(name)
                length = asyncio.run(probe(dest.read_bytes())).duration_s
                smoke.say(f"   chain-{name}.mp4 {length:.2f}s")

            if len(made) > 1:
                ins = [x for n in made for x in ("-i", str(OUT / f"{n}-{LABEL}.mp4"))]
                stack = "".join(f"[{i}:v]" for i in range(len(made)))
                ff(*ins, "-filter_complex", f"{stack}hstack={len(made)}[v]", "-map", "[v]",
                   "-map", "0:a",
                   "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac",
                   "-shortest", str(OUT / f"side-by-side-{LABEL}.mp4"))  # fmt: skip
            for png in OUT.glob("sheet-*.png"):
                ff("-i", str(png), "-q:v", "4", str(SHEETS / f"{png.stem}.jpg"))
            for txt in OUT.glob("*-prompt.txt"):
                shutil.copyfile(txt, SHEETS / txt.name)
        calls = smoke.get("/dev/model-calls", limit=500)
        paid = sum(
            float(c.get("cost_usd") or 0) for c in calls if c.get("model_key") == REWRITE_MODEL
        )
        smoke.say(f"   DeepSeek in this work dir (incl. earlier runs): ${paid:.4f}")
    meter.stop()
    report = SHEETS / f"report-{'-'.join(sorted(only))}.txt"
    report.write_text("\n".join(smoke.lines) + "\n", "utf-8", newline="\n")
    print(f"work dir: {work}")
    return 0 if smoke.ok else 1


if __name__ == "__main__":
    sys.exit(main())
