"""Local smoke test (M4 plan step 9): keyframe drafts on this machine's ComfyUI, for real,
through the studio's own components on the Mock demo series. Nothing is spent: API and writing
models stay Mock (``DRAMA_REAL_LOCAL=1``), only the ComfyUI workflows run.

    uv run --no-sync python scripts/smoke/local_storyboard.py [--studio http://127.0.0.1:8000]
        [--only refs,kf,kf_no_refs] [--keep]

Steps, in this order:

- ``refs``: the demo's locked pictures are Mock placeholders (a colour and a name), so 林晚, 楼道
  and 红伞 are unlocked, drawn again on Qwen-Image-2512 (four candidates each) and locked on
  their first candidate (林晚's 补视图 that locking starts is cancelled: not what this tests).
  便利贴, 手机 and 手机锁屏时间 are unlocked and left so: a placeholder is never sent;
- ``kf``: 1-01 (林晚 + 楼道), 1-02 (楼道 + 红伞; 便利贴 not locked) and 1-04 (林晚 + 楼道)
  drafted on Qwen-Image-Edit-2511 from those pictures, three candidates each;
- ``kf_no_refs``: 1-07 (手机 and its lock screen, neither locked) has no picture to edit from,
  so its draft goes to Qwen-Image-2512 (``kf.model_for``).

The ComfyUI address comes from the studio you have open (its last scan; the studio itself is
not touched). The script runs in a temporary data directory with its own demo. ComfyUI must be
running; do not run it next to the full pytest (ComfyUI can fail to read the weights when
memory is short). Each step reports its model calls, seconds, the GPU memory peak and the
pictures each keyframe was given; the pictures are copied to ``<tmp>/out``. The report goes to
``docs/studio/reports/m4-local-smoke.txt``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from local_assets import V1, Smoke, VramMeter, gpu_query, studio_facts

REPORT = Path(__file__).resolve().parents[2] / "docs" / "studio" / "reports" / "m4-local-smoke.txt"
STEPS = ["refs", "kf", "kf_no_refs"]
DRAWN = ("linwan", "hall", "umbrella")  # drawn again and locked
LEFT_UNLOCKED = ("note", "phone", "txt2")  # unlocked, not drawn: never sent
KF_SHOTS = ("1-01", "1-02", "1-04")
NO_REFS_SHOT = "1-07"


def unlock(smoke: Smoke, asset_id: str) -> None:
    target = {"kind": "asset_unlock", "target_id": asset_id, "patch": {}}
    impact = smoke.post("/impact/preview", target)
    smoke.post("/impact/apply", {"impact_id": impact["id"], "action": "mark"})


def shots(smoke: Smoke) -> dict[str, dict[str, Any]]:
    return {s["label"]: s for s in smoke.get("/episodes/demo-e1/shots")}


def unconfirm(smoke: Smoke, label: str) -> None:
    shot = shots(smoke)[label]
    if shot["confirmed"]:
        resp = smoke.client.patch(f"{V1}/shots/{shot['id']}", json={"confirmed": False})
        resp.raise_for_status()


def cancel_views(smoke: Smoke) -> None:
    """Locking a character starts its 补视图: cancel it, the keyframes are what is measured."""
    views = smoke.product_of("asset:linwan", "ref_views")
    for job in smoke.get("/jobs", limit=50):
        if job["product_id"] == views and job["state"] in ("queued", "running"):
            smoke.post(f"/jobs/{job['id']}/cancel")


def report_keyframe(smoke: Smoke, label: str, product_id: str) -> None:
    version = smoke.latest(product_id)
    refs = version["payload"].get("refs") or []
    smoke.say(f"   {label}: refs sent {refs or 'none'} · aspect {version['payload'].get('aspect')}")
    smoke.keep_files(f"kf-{label}", version)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--studio", default="http://127.0.0.1:8000", help="the studio you have open")
    ap.add_argument("--only", default=",".join(STEPS), help="steps to run, comma-separated")
    ap.add_argument("--keep", action="store_true", help="keep the temporary data directory")
    args = ap.parse_args()
    only = [s for s in args.only.split(",") if s]
    unknown = set(only) - set(STEPS)
    if unknown:
        raise SystemExit(f"unknown steps: {', '.join(sorted(unknown))}")

    facts = studio_facts(args.studio.rstrip("/"))
    tmp = Path(tempfile.mkdtemp(prefix="drama-local-storyboard-"))
    out = tmp / "out"
    out.mkdir()
    os.environ.update({"DRAMA_HOME": str(tmp / "home"), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1"})

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
        smoke.say(f"M4 local smoke · {datetime.now():%Y-%m-%d %H:%M}")
        smoke.say(f"GPU {name} {total} MiB, driver {driver}; in use before {idle} MiB")
        version = comfy.get("system", {}).get("comfyui_version")
        smoke.say(f"ComfyUI {version} at {facts['comfy_url']}")
        spec = smoke.get("/series/demo/spec")
        smoke.say(f"output spec {spec['aspect']} {spec['delivery']}")
        smoke.say()

        if "refs" in only:

            def draw() -> list[str]:
                for a in (*DRAWN, *LEFT_UNLOCKED):
                    unlock(smoke, a)
                return [smoke.run(f"demo-p-asset-{a}")["id"] for a in DRAWN]

            title = "林晚、楼道、红伞重新画（先解锁）· Qwen-Image-2512，各锁第 1 张"
            if smoke.step("refs", title, draw):
                for a in DRAWN:
                    drawn = smoke.latest(f"demo-p-asset-{a}")
                    smoke.keep_files(a, drawn)
                    if drawn["where"] != "local":  # a Mock fallback is no reference to edit from
                        smoke.ok = False
                        smoke.say(f"   {a} was not drawn locally: {drawn['model_key']}")
                        continue
                    smoke.client.patch(f"{V1}/assets/{a}", json={"pick": 0}).raise_for_status()
                    smoke.post(f"/assets/{a}/lock", {})
                cancel_views(smoke)
        if "kf" in only:
            by_label = shots(smoke)

            def keyframes() -> list[str]:
                for label in KF_SHOTS:
                    unconfirm(smoke, label)
                return [smoke.run(by_label[x]["keyframe_product_id"])["id"] for x in KF_SHOTS]

            title = "1-01、1-02、1-04 关键帧草稿 · Qwen-Image-Edit-2511（锁定的参考图）"
            if smoke.step("kf", title, keyframes):
                for label in KF_SHOTS:
                    report_keyframe(smoke, label, by_label[label]["keyframe_product_id"])
        if "kf_no_refs" in only:
            shot = shots(smoke)[NO_REFS_SHOT]

            def no_refs() -> list[str]:
                status = {a["id"]: a["status"] for a in smoke.get("/series/demo/assets")}
                for a in LEFT_UNLOCKED:  # already unlocked when refs ran
                    if status.get(a) == "locked":
                        unlock(smoke, a)
                return [smoke.run(shot["keyframe_product_id"])["id"]]

            title = f"{NO_REFS_SHOT} 没有锁定的参考图 · 改走 Qwen-Image-2512"
            if smoke.step("kf_no_refs", title, no_refs):
                report_keyframe(smoke, NO_REFS_SHOT, shot["keyframe_product_id"])
                model = smoke.latest(shot["keyframe_product_id"])["model_key"]
                if model != "comfy/qwen-image":
                    smoke.ok = False
                    smoke.say(f"   expected comfy/qwen-image, ran on {model}")
        smoke.say()
        smoke.say(f"result: {'all local steps ran' if smoke.ok else 'SOME STEPS FAILED'}")
        smoke.say(f"files: {out}")
    meter.stop()
    # Only a run of every step replaces the report; a partial run writes next to its files.
    report = REPORT if set(only) == set(STEPS) else out / "report.txt"
    report.write_text("\n".join(smoke.lines) + "\n", encoding="utf-8", newline="\n")
    print(f"report: {report}")
    if not args.keep:
        shutil.rmtree(tmp / "home", ignore_errors=True)
    return 0 if smoke.ok else 1


if __name__ == "__main__":
    sys.exit(main())
