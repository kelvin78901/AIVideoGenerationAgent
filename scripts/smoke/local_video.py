"""Local smoke test (M5 plan step 14a): video takes on this machine's ComfyUI, for real, through
the studio's own components on the Mock demo series. Nothing is spent: API and writing models
stay Mock (``DRAMA_REAL_LOCAL=1``), only the ComfyUI workflows run, and a fallback to the API
would land on Mock (and be reported as NOT LOCAL).

    uv run --no-sync python scripts/smoke/local_video.py [--studio http://127.0.0.1:8000]
        [--only frames,vid,ab] [--keep] [--home <a kept data dir>]

Steps, in this order:

- ``frames``: the demo's locked pictures are Mock placeholders, and a take starts from its
  shot's keyframe, so 林晚, 楼道 and 红伞 are drawn again on Qwen-Image-2512 and locked (as in
  ``local_storyboard.py``), then 1-01 and 1-04 take back their confirmation (which reopens
  分镜), get a keyframe draft on the route's local model (FLUX.2 Klein), are confirmed on its
  first picture; the other shots whose keyframes used those pictures turned 待更新, so they are
  drawn again and confirmed too, and 分镜 is confirmed again;
- ``vid``: one take each of 1-01 (no dialogue: H3 image-to-video, ``comfy/h3``) and 1-04
  (原生同步 with 林晚's locked voice: ``comfy/h3-r2v``). Each is checked: made locally, the
  length asked minus the 0.3 s cut, the draft size, a sound track, a poster and a last frame.
- ``ab`` (not run by default): 1-04 on fixed seeds, with the prompt as the studio writes it (A)
  and with one more line asking for one continuous take in the stairwell (B); a contact sheet
  of each take is written to look at (FFmpeg's scene score misses a camera that drifts to
  another place, 2026-10-27, so nothing is counted). ``--home`` reuses a data
  directory a ``--keep`` run left (its keyframes), so ``--only ab --home …`` skips ``frames``.
- ``rewrite`` (M5 step 14c, not run by default; **spends money**, needs ``DRAMA_LIVE=1``): the
  prompt rewrite (``vprompt``) on its real writing model, DeepSeek V4.1 Flash, and nothing else
  real but ComfyUI (``DRAMA_REAL_MODELS``); 1-01 and 1-04 on the seeds of the 2026-10-27
  comparison (``reports/m5-local-smoke/run4-1-04-cut``), so a take, its prompt and a contact
  sheet sit next to the hand-written ones. Stops once DeepSeek's spend passes ``--cap``.

The ComfyUI address comes from the studio you have open (its last scan; the studio itself is
not touched). ComfyUI must be running; do not run it next to the full pytest. The takes (and
the keyframes) are copied to ``<tmp>/out``; the report goes to
``docs/studio/reports/m5-local-smoke.txt``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from local_assets import V1, Smoke, VramMeter, gpu_query, studio_facts
from local_storyboard import DRAWN, LEFT_UNLOCKED, cancel_views, shots, unconfirm, unlock

REPORT = Path(__file__).resolve().parents[2] / "docs" / "studio" / "reports" / "m5-local-smoke.txt"
STEPS = ["frames", "vid", "ab", "rewrite"]
REWRITE_SEEDS = {"1-01": (325085565, 22), "1-04": (191503631, 22)}
REWRITE_MODEL = "deepseek/v4.1-flash"  # the vprompt route's writing model (components.yaml)
DEFAULT_STEPS = ["frames", "vid"]
AB_SEEDS = (11, 22, 33)
AB_SHOT = "1-04"
ONE_TAKE = (
    "一镜到底：不切镜、不换地方，机位一直在楼道里。"
    " One continuous take in the stairwell: no cut, no change of location."
)
VID_SHOTS = {"1-01": "comfy/h3", "1-04": "comfy/h3-r2v"}
TRIM_S = 0.3


def keep_take(smoke: Smoke, label: str, version: dict[str, Any]) -> None:
    """Copy the take's clip, raw clip and frames out and say what they are."""
    from drama_series_agent.media.video import probe

    store = smoke.state.store
    ext = {"video/mp4": ".mp4", "image/png": ".png"}
    kept = []
    for f in version["files"]:
        if f["role"] == "prompt":
            continue
        name = f"take-{label}-{f['role']}{ext.get(f['mime'], '')}"
        shutil.copyfile(store.path_for(f["sha256"]), smoke.out / name)
        size = f"{f['w']}x{f['h']}" if f.get("w") else "?"
        secs = f" {f['duration_s']:.2f}s" if f.get("duration_s") else ""
        kept.append(f"{name} ({size}{secs})")
    smoke.say(f"   model {version['model_key']} [{version['where']}], files: {', '.join(kept)}")
    video = next(f for f in version["files"] if f["role"] == "video")
    info = asyncio.run(probe(store.path_for(video["sha256"]).read_bytes()))
    asked = float(version["payload"].get("asked_s") or 0)
    smoke.say(
        f"   clip {info.w}x{info.h} {info.duration_s:.2f}s @ {info.fps} fps, sound "
        f"{'yes' if info.has_audio else 'NO'}; asked {asked:.2f}s (minus the {TRIM_S}s cut: "
        f"{asked - TRIM_S:.2f}s; a model's shortest clip can be longer); "
        f"voices {version['payload'].get('voices')}, refs "
        f"{version['payload'].get('refs')}"
    )
    # A model makes at least its shortest clip (H3: 5 s, frames 17k + 5); post trims to the shot.
    if info.duration_s < asked - TRIM_S - 0.1:
        smoke.ok = False
        smoke.say("   SHORTER than the shot")


def sheet(src: Path, dest: Path) -> None:
    """Two frames a second, side by side."""
    import subprocess

    from drama_series_agent.media.audio import ffmpeg_exe

    subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(src),
         "-vf", "fps=2,scale=192:-1,tile=6x2", "-frames:v", "1", str(dest)],
        check=True,
    )  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--studio", default="http://127.0.0.1:8000", help="the studio you have open")
    ap.add_argument("--only", default=",".join(DEFAULT_STEPS), help="steps, comma-separated")
    ap.add_argument("--keep", action="store_true", help="keep the temporary data directory")
    ap.add_argument("--home", help="a data directory a --keep run left (reused, kept)")
    ap.add_argument("--cap", type=float, default=0.10, help="rewrite: DeepSeek spend cap, USD")
    args = ap.parse_args()
    only = [s for s in args.only.split(",") if s]
    unknown = set(only) - set(STEPS)
    if unknown:
        raise SystemExit(f"unknown steps: {', '.join(sorted(unknown))}")
    if "rewrite" in only:
        if os.environ.get("DRAMA_LIVE") != "1":
            raise SystemExit("rewrite calls DeepSeek for real (money): set DRAMA_LIVE=1")
        os.environ["DRAMA_REAL_MODELS"] = REWRITE_MODEL

    facts = studio_facts(args.studio.rstrip("/"))
    tmp = Path(tempfile.mkdtemp(prefix="drama-local-video-"))
    out = tmp / "out"
    out.mkdir()
    home = Path(args.home) if args.home else tmp / "home"
    os.environ.update({"DRAMA_HOME": str(home), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1"})

    from fastapi.testclient import TestClient

    from drama_series_agent.api.app import create_app
    from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget

    async def comfy_target() -> ComfyTarget:
        return ComfyTarget(url=facts["comfy_url"], env_hash=facts["env_hash"])

    meter = VramMeter()
    meter.start()
    headers = {"X-Drama-Studio": "1"}
    with TestClient(create_app(), base_url="http://127.0.0.1", headers=headers) as client:
        state = client.app.state.studio  # type: ignore[attr-defined]
        state.setup.comfy_target = comfy_target
        state.registry._adapters.clear()
        smoke = Smoke(client, state, out, meter)
        name, total = " ".join(gpu_query("name")), " ".join(gpu_query("memory.total"))
        driver, idle = " ".join(gpu_query("driver_version")), " ".join(gpu_query("memory.used"))
        comfy = httpx.get(f"{facts['comfy_url']}/system_stats", timeout=10).json()
        smoke.say(f"M5 local smoke · {datetime.now():%Y-%m-%d %H:%M}")
        smoke.say(f"GPU {name} {total} MiB, driver {driver}; in use before {idle} MiB")
        version = comfy.get("system", {}).get("comfyui_version")
        smoke.say(f"ComfyUI {version} at {facts['comfy_url']}")
        spec = smoke.get("/series/demo/spec")
        smoke.say(f"output spec {spec['aspect']} {spec['delivery']} {spec['fps']} fps")
        smoke.say()

        if "frames" in only:

            def draw() -> list[str]:
                for a in (*DRAWN, *LEFT_UNLOCKED):
                    unlock(smoke, a)
                return [smoke.run(f"demo-p-asset-{a}")["id"] for a in DRAWN]

            title = "林晚、楼道、红伞重新画（先解锁）· Qwen-Image-2512，各锁第 1 张"
            if smoke.step("refs", title, draw):
                for a in DRAWN:
                    smoke.client.patch(f"{V1}/assets/{a}", json={"pick": 0}).raise_for_status()
                    smoke.post(f"/assets/{a}/lock", {})
                cancel_views(smoke)
            by_label = shots(smoke)

            def keyframes() -> list[str]:
                for label in VID_SHOTS:
                    unconfirm(smoke, label)
                return [smoke.run(by_label[x]["keyframe_product_id"])["id"] for x in VID_SHOTS]

            title = "1-01、1-04 关键帧草稿（本地），确认第 1 张"
            if smoke.step("kf", title, keyframes):
                for label in VID_SHOTS:
                    kf = smoke.latest(by_label[label]["keyframe_product_id"])
                    smoke.keep_files(f"kf-{label}", kf)
                    resp = smoke.client.patch(
                        f"{V1}/shots/{by_label[label]['id']}", json={"confirmed": True}
                    )
                    resp.raise_for_status()
            # The other shots whose keyframes used the pictures drawn again are 待更新: drawn
            # again on their first picture (a continuous shot only needs the decision).
            stale = [s for s in shots(smoke).values() if not s["confirmed"] or s["confirm_stale"]]
            drawn = [s for s in stale if s["keyframe_product_id"]]

            def redraw() -> list[str]:
                for s in drawn:
                    unconfirm(smoke, s["label"])
                return [smoke.run(s["keyframe_product_id"])["id"] for s in drawn]

            labels = "、".join(s["label"] for s in drawn) or "无"
            if not drawn or smoke.step("kf-stale", f"待更新的 {labels} 重画，再确认分镜", redraw):
                for s in stale:
                    resp = smoke.client.patch(f"{V1}/shots/{s['id']}", json={"confirmed": True})
                    if resp.status_code >= 400:
                        smoke.say(f"   {s['label']} not confirmed: {resp.text[:200]}")
                smoke.post("/gates/storyboard/confirm", {"scope_id": "demo-e1"})
                board = smoke.get("/episodes/demo-e1/progress")["steps"]["storyboard"]
                smoke.say(f"   分镜 {board['state']} {board['done']}/{board['total']}")
        if "vid" in only:
            by_label = shots(smoke)
            for label, model in VID_SHOTS.items():
                product_id = by_label[label]["video_product_id"]

                def take(product_id: str = product_id) -> list[str]:
                    return [smoke.run(product_id)["id"]]

                title = f"{label} 视频草稿 · 应走 {model}（本地 H3，768P，8 步 Turbo）"
                if smoke.step(f"vid-{label}", title, take):
                    v = smoke.latest(product_id)
                    keep_take(smoke, label, v)
                    if v["model_key"] != model:
                        smoke.ok = False
                        smoke.say(f"   expected {model}, ran on {v['model_key']}")
        if "ab" in only:
            from drama_series_agent.pipeline import runs

            product_id = shots(smoke)[AB_SHOT]["video_product_id"]
            compiled = smoke.get(f"/products/{product_id}")["prompt"]["compiled"]
            for seed in AB_SEEDS:
                for variant, text in (("A", compiled), ("B", f"{compiled}\n{ONE_TAKE}")):
                    runs.random.randrange = lambda *_, seed=seed: seed  # type: ignore[assignment]

                    def ab_take(text: str = text) -> list[str]:
                        return [smoke.run(product_id, compiled=text)["id"]]

                    what = "原提示词" if variant == "A" else "加一镜到底"
                    title = f"{AB_SHOT} 种子 {seed} · {variant}（{what}）"
                    if smoke.step(f"ab-{seed}-{variant}", title, ab_take):
                        v = smoke.latest(product_id)
                        raw = next(f for f in v["files"] if f["role"] == "raw")
                        path = smoke.state.store.path_for(raw["sha256"])
                        name = f"ab-{seed}-{variant}"
                        shutil.copyfile(path, out / f"{name}.mp4")
                        sheet(path, out / f"{name}.png")
                        smoke.say(f"   seed {v['seed']} → {name}.mp4, {name}.png")
        if "rewrite" in only:
            from drama_series_agent.pipeline import runs

            def spent() -> float:
                calls = smoke.get("/dev/model-calls", limit=500)
                return sum(
                    float(c.get("cost_usd") or 0)
                    for c in calls
                    if c.get("model_key") == REWRITE_MODEL
                )

            def free_comfy() -> None:
                """Let ComfyUI drop its models and caches (no job runs): loading H3 with RAM
                short fails (``hostbuf_file_reader_read failed``, 2026-10-27)."""
                body = {"unload_models": True, "free_memory": True}
                httpx.post(f"{facts['comfy_url']}/free", json=body, timeout=30)

            def cancel_left(product_id: str) -> None:
                """Jobs an earlier, stopped run of a kept data directory left (they resume
                when the app starts and keep the product busy)."""
                for j in smoke.get("/jobs", limit=200):
                    if j.get("product_id") == product_id and j["state"] in ("queued", "running"):
                        smoke.post(f"/jobs/{j['id']}/cancel")
                        smoke.wait(j["id"])

            # No fallback in this check: a local failure is retried locally, not made on the
            # (Mock) API.
            off = {"enabled": False, "on": [], "qa_fail_n": 2, "timeout_s": 600, "to": None}
            off["notify"] = "after"
            override = {"scope": "component", "scope_id": None, "component_id": "vid"}
            put = smoke.client.put(
                f"{V1}/config/override", json={**override, "data": {"fallback": off}}
            )
            put.raise_for_status()
            by_label = shots(smoke)
            for label, seeds in REWRITE_SEEDS.items():
                product_id = by_label[label]["video_product_id"]
                cancel_left(product_id)
                for seed in seeds:
                    if spent() > args.cap:
                        smoke.ok = False
                        smoke.say(
                            f"   stopped: DeepSeek spent ${spent():.4f}, over the ${args.cap} cap"
                        )
                        break
                    runs.random.randrange = lambda *_, seed=seed: seed  # type: ignore[assignment]

                    def rw_take(product_id: str = product_id) -> list[str]:
                        # A take that failed in ComfyUI is made again once, after freeing its
                        # memory (the rewrite is cached, so DeepSeek is not asked again).
                        ids: list[str] = []
                        for _ in range(2):
                            free_comfy()
                            job = smoke.run(product_id)
                            ids.append(job["id"])
                            if smoke.wait(job["id"])["state"] == "succeeded":
                                break
                        return ids

                    title = f"{label} 种子 {seed} · DeepSeek 按官方写法改写 + 本地 H3"
                    if smoke.step(f"rewrite-{label}-s{seed}", title, rw_take):
                        v = smoke.latest(product_id)
                        name = f"rewrite-{label}-s{seed}"
                        if v["where"] != "local" or v["seed"] != seed:
                            smoke.ok = False
                            smoke.say(f"   {name}: no local take on seed {seed} (twice)")
                            continue
                        prompt = next(f for f in v["files"] if f["role"] == "prompt")
                        text = smoke.state.store.path_for(prompt["sha256"]).read_text("utf-8")
                        (out / f"{name}.txt").write_text(text, encoding="utf-8", newline="\n")
                        raw = next(f for f in v["files"] if f["role"] == "raw")
                        path = smoke.state.store.path_for(raw["sha256"])
                        shutil.copyfile(path, out / f"{name}.mp4")
                        sheet(path, out / f"{name}.png")
                        words = len(text.split())
                        rewriter = v["payload"].get("prompt_rewrite")
                        smoke.say(
                            f"   seed {v['seed']}, rewritten by {rewriter} ({words} words) → "
                            f"{name}.mp4 / .png / .txt"
                        )
            smoke.say(f"   DeepSeek spent ${spent():.4f} (cap ${args.cap})")
        smoke.say()
        smoke.say(f"result: {'all local steps ran' if smoke.ok else 'SOME STEPS FAILED'}")
        smoke.say(f"files: {out}")
    meter.stop()
    # Only a run of every step replaces the report; a partial run writes next to its files.
    report = REPORT if set(only) == set(DEFAULT_STEPS) else out / "report.txt"
    report.write_text("\n".join(smoke.lines) + "\n", encoding="utf-8", newline="\n")
    print(f"report: {report}")
    if not args.keep and not args.home:
        shutil.rmtree(home, ignore_errors=True)
    return 0 if smoke.ok else 1


if __name__ == "__main__":
    sys.exit(main())
