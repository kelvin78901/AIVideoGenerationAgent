"""Live smoke test (M4 plan step 10): shot planning and one keyframe final, for real, through
the studio's own components on the Mock demo series. Real calls cost real money (about $0.16).

    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/live_storyboard.py [--cap 1]
        [--only plan,kf] [--studio http://127.0.0.1:8000] [--keep]
    uv run --no-sync python scripts/smoke/live_storyboard.py --mock  # on Mock, free

- ``plan``: 分镜规划 of episode 1 run again on DeepSeek V4 Pro (~$0.02) from the demo's adopted
  script; the new version is reported (shots per scene, types, lines, references) and saved as
  ``plan.json``, not adopted (the keyframe step uses the demo's plan);
- ``kf``: the demo's locked pictures are Mock placeholders, so 林晚 and 楼道 are unlocked, drawn
  on Qwen-Image-2512 (local) and locked on their first candidate (林晚's 补视图 is cancelled);
  1-04 (close on 林晚 reading the note) is drafted on Qwen-Image-Edit-2511 (local), and its first
  candidate finished on Nano Banana Pro (~$0.14) with the draft, 林晚 and 楼道 as references.

Spending as in ``live_assets.py``: the provider connection tests run first (free calls); each
component's per-run cap is set to its step's limit (``LIMITS``), so a run estimated above it
waits for a yes and the script cancels it instead; a step starts only if the spend so far plus
its limit stays under ``--cap``, and a job is cancelled once the spend passes it. A local draft
that fell back to an API stops the script.

The app runs in this process on a temporary data directory with the Mock demo series, then
switches every model to real. ComfyUI is the one of the studio you have open (its last scan),
so it must be running for ``kf``. Keys come from the OS keyring, else ``.env``. The pictures are
copied to ``<tmp>/out``; a full live run writes ``docs/studio/reports/m4-live-smoke.txt``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from live_assets import LiveSmoke, Stop
from local_assets import REAL_HOME, V1, studio_facts

from drama_series_agent.core import secrets

REPORT = Path(__file__).resolve().parents[2] / "docs" / "studio" / "reports" / "m4-live-smoke.txt"
STEPS = ["plan", "kf"]
EPISODE = "demo-e1"
PLAN_MODEL = "deepseek/v4-pro"
FINAL_MODEL = "google/nano-banana-pro"
SHOT = "1-04"
DRAWN = ("linwan", "hall")  # 1-04's references, drawn again locally and locked
# Per-run caps (USD) while the smoke runs: each step's estimate with some room.
LIMITS = {"plan": 0.10, "kf": 0.25}
# Provider → the models its connection test must find (media models only), the step, the key.
PROVIDERS = {
    "deepseek": ("plan", [], "DEEPSEEK_API_KEY"),
    "google_llm": ("kf", [FINAL_MODEL], "GEMINI_API_KEY"),
}


class StoryboardSmoke(LiveSmoke):
    def caps(self) -> None:
        for component, limit in LIMITS.items():
            body = {
                "scope": "component",
                "scope_id": None,
                "component_id": component,
                "data": {"per_call_cap_usd": limit},
            }
            self.client.put(f"{V1}/config/override", json=body).raise_for_status()

    def budget(self, step: str) -> None:
        spent, limit = self.spent(), LIMITS[step]
        if spent + limit > self.cap:
            raise Stop(f"{step}: ${spent:.4f} spent + its ${limit} limit passes ${self.cap}")

    def connections(self, steps: list[str]) -> None:
        for provider, (step, models, _key) in PROVIDERS.items():
            if step not in steps:
                continue
            test = self.post(f"/providers/{provider}/test")
            media = {m["key"]: m for m in test.get("media") or []}
            if not test["ok"]:
                raise Stop(f"{provider} connection test failed: {test.get('detail')}")
            for key in models:
                check = media.get(key)
                if check is None or not check["ok"]:
                    detail = check["detail"] if check else "not listed"
                    raise Stop(f"{provider} connection test failed for {key}: {detail}")
            self.say(f"connection {provider}: ok {', '.join(models)}".rstrip())

    # ------------------------------------------------------------------ steps

    def plan(self) -> None:
        self.say(f"== plan: 第 1 集分镜规划 · {PLAN_MODEL}")
        self.budget("plan")
        product = self.product_of(f"episode:{EPISODE}", "shot_plan")
        before = self.latest(product)
        self.start(product, "plan", mode="rerun", model=PLAN_MODEL)
        version = self.latest(product)
        if version["id"] == before["id"] or version["model_key"] != PLAN_MODEL:
            raise Stop(f"plan: no new version on {PLAN_MODEL} (got {version['model_key']})")
        shots: list[dict[str, Any]] = version["payload"]["shots"]
        (self.out / "plan.json").write_text(
            json.dumps(version["payload"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        demo = before["payload"]["shots"]
        scenes = Counter(s["scene_id"] for s in shots)
        self.say(f"   {len(shots)} shots (the demo's plan: {len(demo)}), per scene {dict(scenes)}")
        types = Counter(s["shot_type"] for s in shots)
        self.say(f"   types {dict(types)}")
        for i, s in enumerate(shots, 1):
            tail = f" ← {s['tail_from']}" if s.get("tail_from") else ""
            secs = f"{s['duration_s']} s" if s.get("duration_s") is not None else "audio"
            self.say(
                f"   {i:>2}. {s['shot_type']}/{s['framing']}/{s['camera_move']} {secs}{tail} · "
                f"lines {','.join(s.get('line_ids') or [])} · "
                f"refs {','.join(s.get('asset_ids') or [])}"
            )
            self.say(f"       {s.get('summary') or ''} | {s.get('intent') or ''}")

    def cancel_views(self) -> None:
        """Locking 林晚 starts her 补视图 on the GPU: not what this measures."""
        views = self.product_of("asset:linwan", "ref_views")
        for job in self.get("/jobs", limit=50):
            if job["product_id"] == views and job["state"] in ("queued", "running"):
                self.post(f"/jobs/{job['id']}/cancel")

    def kf(self) -> None:
        self.say(
            f"== kf: {SHOT} · 林晚、楼道本地重画锁定 → Qwen-Image-Edit 草稿 → {FINAL_MODEL} 终版"
        )
        self.budget("kf")
        for a in DRAWN:
            target = {"kind": "asset_unlock", "target_id": a, "patch": {}}
            impact = self.post("/impact/preview", target)
            self.post("/impact/apply", {"impact_id": impact["id"], "action": "mark"})
            drawn = self.local_draft(f"demo-p-asset-{a}", a, "comfy/qwen-image")
            self.keep_files(a, drawn)
            self.client.patch(f"{V1}/assets/{a}", json={"pick": 0}).raise_for_status()
            self.post(f"/assets/{a}/lock", {})
            if a == "linwan":
                self.cancel_views()
        shot = next(s for s in self.get(f"/episodes/{EPISODE}/shots") if s["label"] == SHOT)
        product = shot["keyframe_product_id"]
        draft = self.local_draft(product, SHOT, "comfy/qwen-image-edit")
        self.say(f"   draft refs {draft['payload'].get('refs')}")
        self.keep_files(f"kf-{SHOT}-draft", draft)
        final = self.final(product, f"{SHOT} final", draft, FINAL_MODEL)
        self.say(f"   final refs 草稿 + {final['payload'].get('refs')}")
        self.keep_files(f"kf-{SHOT}-final", final)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--cap", type=float, default=1.0, help="hard spending cap in USD")
    ap.add_argument("--only", default=",".join(STEPS), help="steps to run, comma-separated")
    ap.add_argument("--studio", default="http://127.0.0.1:8000", help="the studio you have open")
    ap.add_argument("--mock", action="store_true", help="the same flow on Mock (free)")
    ap.add_argument("--keep", action="store_true", help="keep the temporary data directory")
    args = ap.parse_args()
    only = [s for s in args.only.split(",") if s]
    unknown = set(only) - set(STEPS)
    if unknown:
        raise SystemExit(f"unknown steps: {', '.join(sorted(unknown))}")
    if not args.mock:
        if os.environ.get("DRAMA_LIVE") != "1":
            print("real calls cost money: set DRAMA_LIVE=1 to run this", file=sys.stderr)
            return 2
        for _provider, (step, _models, key) in PROVIDERS.items():
            if step in only and secrets.has_secret(key) == "none":
                print(f"no {key} in the keyring or .env", file=sys.stderr)
                return 2

    facts = None if args.mock else studio_facts(args.studio.rstrip("/"))
    tmp = Path(tempfile.mkdtemp(prefix="drama-live-storyboard-"))
    out = tmp / "out"
    out.mkdir()
    os.environ.update({"DRAMA_HOME": str(tmp / "home"), "DRAMA_MOCK": "1"})
    os.environ.pop("DRAMA_REAL_LOCAL", None)

    from fastapi.testclient import TestClient

    from drama_series_agent.api.app import create_app
    from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget
    from drama_series_agent.modelhub.adapters.local_python import RuntimePaths

    code = 0
    headers = {"X-Drama-Studio": "1"}
    with TestClient(create_app(), base_url="http://127.0.0.1", headers=headers) as client:
        state = client.app.state.studio  # type: ignore[attr-defined]
        if facts is not None:

            async def runtime_paths() -> RuntimePaths:
                return RuntimePaths(envs=REAL_HOME / "envs", models=facts["models"])

            async def comfy_target() -> ComfyTarget:
                return ComfyTarget(url=facts["comfy_url"], env_hash=facts["env_hash"])

            state.setup.runtime_paths = runtime_paths
            state.setup.comfy_target = comfy_target
            # The demo is seeded (Mock mode); from here on every model is real.
            state.registry.mock = False
            state.registry._adapters.clear()
        smoke = StoryboardSmoke(client, state, out, args.cap, mock=args.mock)
        mode = "Mock (free)" if args.mock else f"LIVE, cap ${args.cap}"
        smoke.say(f"M4 live smoke · {datetime.now():%Y-%m-%d %H:%M} · {mode} · steps {only}")
        try:
            if facts is not None:
                comfy = httpx.get(f"{facts['comfy_url']}/system_stats", timeout=10).json()
                version = comfy.get("system", {}).get("comfyui_version")
                smoke.say(f"ComfyUI {version} at {facts['comfy_url']}; models {facts['models']}")
                smoke.connections(only)
            smoke.caps()
            for step in STEPS:
                if step in only:
                    getattr(smoke, step)()
        except (Stop, RuntimeError, httpx.HTTPError) as exc:
            smoke.say(f"\nSTOPPED: {exc}")
            code = 1
        finally:
            smoke.report_calls()
        smoke.say()
        smoke.say(f"result: {'all steps ran' if code == 0 else 'STOPPED'}")
        smoke.say(f"files: {out}")
    full = not args.mock and code == 0 and set(only) == set(STEPS)
    report = REPORT if full else out / "report.txt"
    with open(report, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(smoke.lines) + "\n")
    print(f"report: {report}")
    if not args.keep:
        shutil.rmtree(tmp / "home", ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
