"""Keyframe model bake-off (M4, Kelvin 2026-10-26): the same locked references, the same
shots, several keyframe models. Local drafts are free; the API finals cost real money (about
$0.6) and run only with ``DRAMA_LIVE=1``.

    uv run --no-sync python scripts/smoke/kf_bakeoff.py                  # local drafts only
    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/kf_bakeoff.py [--cap 1]   # and the API finals
        [--local comfy/qwen-image-edit,comfy/flux3-klein] [--api google/nano-banana-pro,...]

- ``refs``: 林晚, 楼道 and 红伞 drawn again on Qwen-Image-2512 and locked on their first
  candidate (the demo's locked pictures are Mock placeholders); 便利贴, 手机 and its lock screen
  unlocked and left so. Every keyframe model gets these same pictures.
- ``drafts``: 1-01 (林晚 + 楼道, the script's 「米色风衣湿了半边」 left as it is), 1-02 (楼道 + 红伞,
  nobody in it), 1-04 (林晚 + 楼道, close) and 1-07 (no locked picture: each edit model goes to
  its own family's text-to-image workflow) on each local model, three candidates each.
- ``finals`` (live only): candidate 0 of the first local model's draft of 1-01, 1-04 and 1-07
  finished on each API model (「用 API 出终版」, one picture each).

Spending, the ComfyUI target and the temporary data directory work as in ``live_storyboard.py``.
The pictures go to ``<tmp>/out`` as ``<model>-<shot>-<file>``; a full live run writes its report
to ``docs/studio/reports/m4-kf-bakeoff.txt``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from live_assets import LiveSmoke, Stop
from local_assets import REAL_HOME, V1, VramMeter, gpu_query, studio_facts

from drama_series_agent.core import secrets

REPORT = Path(__file__).resolve().parents[2] / "docs" / "studio" / "reports" / "m4-kf-bakeoff.txt"
EPISODE = "demo-e1"
DRAWN = ("linwan", "hall", "umbrella")
LEFT_UNLOCKED = ("note", "phone", "txt2")
SHOTS = ("1-01", "1-02", "1-04", "1-07")
FINAL_SHOTS = ("1-01", "1-04", "1-07")
LOCAL = ("comfy/qwen-image-edit", "comfy/flux3-klein")
API = ("google/nano-banana-pro", "google/nano-banana-2.1")
LIMITS = {"kf": 0.25, "img": 0.0}


class Bakeoff(LiveSmoke):
    def caps(self) -> None:
        body = {
            "scope": "component",
            "scope_id": None,
            "component_id": "kf",
            "data": {"per_call_cap_usd": LIMITS["kf"]},
        }
        self.client.put(f"{V1}/config/override", json=body).raise_for_status()

    def connections_for(self, apis: list[str]) -> None:
        """Free calls: the Gemini key and each image model id we use (no generation)."""
        test = self.post("/providers/google_llm/test")
        media = {m["key"]: m for m in test.get("media") or []}
        for key in apis:
            check = media.get(key)
            if not test["ok"] or check is None or not check["ok"]:
                detail = check["detail"] if check else test.get("detail")
                raise Stop(f"google_llm connection test failed for {key}: {detail}")
        self.say(f"connection google_llm: ok {', '.join(apis)}")

    def shots(self) -> dict[str, dict[str, Any]]:
        return {s["label"]: s for s in self.get(f"/episodes/{EPISODE}/shots")}

    def unlock(self, asset_id: str) -> None:
        target = {"kind": "asset_unlock", "target_id": asset_id, "patch": {}}
        impact = self.post("/impact/preview", target)
        self.post("/impact/apply", {"impact_id": impact["id"], "action": "mark"})

    def refs(self) -> None:
        self.say("== refs: 林晚、楼道、红伞 · Qwen-Image-2512（本地），各锁第 1 张")
        for a in (*DRAWN, *LEFT_UNLOCKED):
            self.unlock(a)
        for a in DRAWN:
            drawn = self.local_draft(f"demo-p-asset-{a}", a, "comfy/qwen-image")
            self.keep_files(f"ref-{a}", drawn)
            self.client.patch(f"{V1}/assets/{a}", json={"pick": 0}).raise_for_status()
            self.post(f"/assets/{a}/lock", {})
            if a == "linwan":  # locking her starts 补视图 on the GPU: not what is measured
                views = self.product_of("asset:linwan", "ref_views")
                for job in self.get("/jobs", limit=50):
                    if job["product_id"] == views and job["state"] in ("queued", "running"):
                        self.post(f"/jobs/{job['id']}/cancel")
        for label in ("1-01", "1-02"):  # the demo confirms them; a run needs them open
            shot = self.shots()[label]
            if shot["confirmed"]:
                resp = self.client.patch(f"{V1}/shots/{shot['id']}", json={"confirmed": False})
                resp.raise_for_status()

    def drafts(self, models: list[str]) -> dict[str, dict[str, Any]]:
        """Each local model's draft of each shot; returns the first model's versions."""
        first: dict[str, dict[str, Any]] = {}
        shots = self.shots()
        for model in models:
            self.say(f"== drafts: {model}")
            for label in SHOTS:
                product = shots[label]["keyframe_product_id"]
                t0 = time.monotonic()
                peak_from = t0
                self.follow(self.run(product, mode="rerun", model=model), f"{label} {model}")
                version = self.latest(product)
                peak = self.meter.peak(peak_from, time.monotonic())
                refs = version["payload"].get("refs") or []
                self.say(
                    f"   {label}: ran on {version['model_key']} [{version['where']}] · refs "
                    f"{refs or 'none'} · GPU memory peak {peak} MiB"
                )
                if version["where"] != "local":
                    raise Stop(f"{label} on {model} fell back to {version['model_key']}")
                self.keep_files(f"{_slug(model)}-{label}", version)
                if model == models[0]:
                    first[label] = version
        return first

    def finals(self, apis: list[str], drafts: dict[str, dict[str, Any]]) -> None:
        shots = self.shots()
        for model in apis:
            self.say(f"== finals: {model}（以 {drafts['1-01']['model_key']} 的草稿 #0 为参考）")
            for label in FINAL_SHOTS:
                product = shots[label]["keyframe_product_id"]
                version = self.final(product, f"{label} {model}", drafts[label], model)
                self.keep_files(f"{_slug(model)}-{label}", version)


def _slug(model: str) -> str:
    return model.split("/", 1)[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--cap", type=float, default=1.0, help="hard spending cap in USD")
    ap.add_argument("--local", default=",".join(LOCAL), help="local keyframe models")
    ap.add_argument("--api", default=",".join(API), help="API models for the finals (live only)")
    ap.add_argument("--studio", default="http://127.0.0.1:8000", help="the studio you have open")
    ap.add_argument("--keep", action="store_true", help="keep the temporary data directory")
    args = ap.parse_args()
    live = os.environ.get("DRAMA_LIVE") == "1"
    local = [m for m in args.local.split(",") if m]
    apis = [m for m in args.api.split(",") if m] if live else []
    if apis and secrets.has_secret("GEMINI_API_KEY") == "none":
        print("no GEMINI_API_KEY in the keyring or .env", file=sys.stderr)
        return 2

    facts = studio_facts(args.studio.rstrip("/"))
    tmp = Path(tempfile.mkdtemp(prefix="drama-kf-bakeoff-"))
    out = tmp / "out"
    out.mkdir()
    os.environ.update({"DRAMA_HOME": str(tmp / "home"), "DRAMA_MOCK": "1"})
    if live:
        os.environ.pop("DRAMA_REAL_LOCAL", None)
    else:
        os.environ["DRAMA_REAL_LOCAL"] = "1"  # local models real, API models Mock (unused)

    from fastapi.testclient import TestClient

    from drama_series_agent.api.app import create_app
    from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget
    from drama_series_agent.modelhub.adapters.local_python import RuntimePaths

    async def runtime_paths() -> RuntimePaths:
        return RuntimePaths(envs=REAL_HOME / "envs", models=facts["models"])

    async def comfy_target() -> ComfyTarget:
        return ComfyTarget(url=facts["comfy_url"], env_hash=facts["env_hash"])

    code = 0
    headers = {"X-Drama-Studio": "1"}
    with TestClient(create_app(), base_url="http://127.0.0.1", headers=headers) as client:
        state = client.app.state.studio  # type: ignore[attr-defined]
        state.setup.runtime_paths = runtime_paths
        state.setup.comfy_target = comfy_target
        if live:
            state.registry.mock = False  # the demo is seeded; from here on every model is real
        state.registry._adapters.clear()
        smoke = Bakeoff(client, state, out, args.cap, mock=False)
        smoke.meter = VramMeter()
        smoke.meter.start()
        mode = f"LIVE, cap ${args.cap}" if live else "local only (API models not run)"
        smoke.say(f"M4 keyframe bake-off · {datetime.now():%Y-%m-%d %H:%M} · {mode}")
        name, total = " ".join(gpu_query("name")), " ".join(gpu_query("memory.total"))
        smoke.say(f"GPU {name} {total} MiB; local {local}; API {apis or '-'}")
        comfy = httpx.get(f"{facts['comfy_url']}/system_stats", timeout=10).json()
        smoke.say(f"ComfyUI {comfy.get('system', {}).get('comfyui_version')} at {facts['comfy_url']}")
        try:
            if apis:
                smoke.connections_for(apis)
            smoke.caps()
            smoke.refs()
            drafts = smoke.drafts(local)
            if apis:
                smoke.finals(apis, drafts)
        except (Stop, RuntimeError, httpx.HTTPError) as exc:
            smoke.say(f"\nSTOPPED: {exc}")
            code = 1
        finally:
            smoke.report_calls()
            smoke.meter.stop()
        smoke.say()
        smoke.say(f"result: {'all steps ran' if code == 0 else 'STOPPED'}")
        smoke.say(f"files: {out}")
    full = live and code == 0 and set(local) == set(LOCAL) and set(apis) == set(API)
    report = REPORT if full else out / "report.txt"
    with open(report, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(smoke.lines) + "\n")
    print(f"report: {report}")
    if not args.keep:
        shutil.rmtree(tmp / "home", ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
