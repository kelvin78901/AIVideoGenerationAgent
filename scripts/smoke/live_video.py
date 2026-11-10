"""Live smoke test (M5 plan step 15): video takes on the real APIs, through the studio's own
components, on a data directory a local run left (its keyframes and 林晚's voice are real).
Real calls cost real money (about $1.7 at 720p for Seedance).

    uv run --no-sync python scripts/smoke/local_video.py --only frames,chain --keep
    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/live_video.py --home <its data dir>\\home
        [--cap 3] [--only select,h3,regen,seedance] [--studio http://127.0.0.1:8000]

Steps, cheapest first:

- ``select``: the series' rules table emptied and the LLM suggestion on, so 1-01's first local
  take asks the ``vselect`` route (DeepSeek V4.1 Flash) which workflow to use; the take is made
  on this machine's H3 (its prompt rewritten by DeepSeek too). Reported: the answer and why.
- ``h3``: 1-04 back to 原生同步 (``local_video.py --only tts104`` leaves it 先配音) and one
  take on the H3 API (``minimax/h3-api``): 林晚's locked voice sample, her picture and the
  stairwell as references, the official Context-IR rewrite.
- ``regen``: 「用 API 出终版」 on 1-04's local 原生同步 draft: H3 Regenerate-2K.
- ``seedance``: one take of 1-01 on Seedance 2.5 **at 720p** (Kelvin 2026-11-08: at the
  output spec's 1080p one 4 s clip is about $2.1, which leaves no room under the cap; the
  delivery tiers are 1080p and 2K only, so the adapter's tier is pinned for this run).

Spending as in ``live_storyboard.py``: the provider connection tests run first (free calls); the
video component's per-run cap is set to the step's limit (``LIMITS``), so a run estimated above
it waits for a yes and the script cancels it; a step starts only if the spend so far plus its
limit stays under ``--cap``. ComfyUI is the one of the studio you have open (for ``select``).
Keys come from the OS keyring, else ``.env``. The takes are copied to ``<home>/../live-out``; a
run of every step writes ``docs/studio/reports/m5-live-smoke.txt``.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from live_assets import LiveSmoke, Stop
from local_assets import REAL_HOME, V1, studio_facts
from local_storyboard import shots
from local_video import keep_take

from drama_series_agent.core import secrets

REPORT = Path(__file__).resolve().parents[2] / "docs" / "studio" / "reports" / "m5-live-smoke.txt"
STEPS = ["select", "h3", "regen", "seedance"]
EPISODE = "demo-e1"
SERIES = "demo"
H3_API, REGEN, SEEDANCE = "minimax/h3-api", "minimax/h3-regenerate-2k", "volc/seedance-2.5"
SELECT_MODEL = "deepseek/v4.1-flash"
# Per-run caps (USD) of the step's component while it runs: its estimate with some room.
LIMITS = {"select": ("vid", 0.05), "h3": ("vid", 0.70), "regen": ("vid", 0.70)}
LIMITS["seedance"] = ("vid", 1.10)
# Provider → the step needing it, the media models its connection test should list, the key.
PROVIDERS = {
    "deepseek": ("select", [], "DEEPSEEK_API_KEY"),
    "minimax_llm": ("h3", [H3_API, REGEN], "MINIMAX_API_KEY"),
    "volcengine": ("seedance", [SEEDANCE], "ARK_API_KEY"),
}


class VideoSmoke(LiveSmoke):
    def limit(self, step: str) -> None:
        component, usd = LIMITS[step]
        spent = self.spent()
        if spent + usd > self.cap:
            raise Stop(f"{step}: ${spent:.4f} spent + its ${usd} limit passes ${self.cap}")
        body = {
            "scope": "component",
            "scope_id": None,
            "component_id": component,
            "data": {"per_call_cap_usd": usd},
        }
        self.client.put(f"{V1}/config/override", json=body).raise_for_status()

    def connections(self, steps: list[str]) -> None:
        for provider, (step, models, _key) in PROVIDERS.items():
            if step not in steps and not (provider == "minimax_llm" and "regen" in steps):
                continue
            test = self.post(f"/providers/{provider}/test")
            if not test["ok"]:
                raise Stop(f"{provider} connection test failed: {test.get('detail')}")
            media = {m["key"]: m for m in test.get("media") or []}
            for key in models:
                check = media.get(key)
                if check is not None and not check["ok"]:
                    raise Stop(f"{provider} connection test failed for {key}: {check['detail']}")
                state = "ok" if check is not None else "not checked by the test"
                self.say(f"connection {provider}: {key} {state}")
            if not models:
                self.say(f"connection {provider}: ok")

    def take(self, label: str, product_id: str, title: str, **body: Any) -> dict[str, Any]:
        before = {v["id"] for v in self.get(f"/products/{product_id}")["versions"]}
        estimate = self.get(f"/products/{product_id}").get("estimate") or {}
        self.say(f"== {title}")
        job = self.start(product_id, label, count=1, **body)
        made = [v for v in self.get(f"/products/{product_id}")["versions"] if v["id"] not in before]
        if not made:
            raise Stop(f"{label}: no new take (job {job['id']})")
        v = made[-1]
        keep_take(self, label, v)
        cost = sum(float(c.cost_usd or 0) for c in self.calls() if c.job_id == job["id"])
        self.say(
            f"   est (route default) ${float(estimate.get('cost_usd') or 0):.4f}; "
            f"job est ${float(job.get('est_cost_usd') or 0):.4f}; billed ${cost:.4f}; "
            f"spent so far ${self.spent():.4f}"
        )
        return v

    # ------------------------------------------------------------------ steps

    def select(self) -> None:
        self.limit("select")
        resp = self.client.put(
            f"{V1}/series/{SERIES}/workflow-rules", json={"rules": [], "suggest": True}
        )
        resp.raise_for_status()
        shot = shots(self)["1-01"]
        v = self.take("select-1-01", shot["video_product_id"], "select: 1-01 本地出片，先问 LLM")
        if v["where"] != "local":
            raise Stop(f"select: the take ran on {v['model_key']}, not locally")
        asked = [c for c in self.calls() if c.component_id == "vselect"]
        made = [c for c in self.calls() if c.component_id == "vid" and c.where == "local"]
        for c in asked:
            self.say(f"   vselect call {c.model_key} {c.status} ${float(c.cost_usd or 0):.4f}")
        chosen = made[-1].select_json if made else None
        self.say(f"   select_json {chosen}")
        if not asked or not chosen or chosen.get("by") != "suggest":
            raise Stop("select: the LLM was not asked, or its answer was not used")

    def native_104(self) -> dict[str, Any]:
        shot = shots(self)["1-04"]
        if shot["audio_mode"] != "native":
            target = {
                "kind": "shot_edit",
                "target_id": shot["id"],
                "patch": {"audio_mode": "native"},
            }
            impact = self.post("/impact/preview", target)
            self.post("/impact/apply", {"impact_id": impact["id"], "action": "mark"})
            resp = self.client.patch(f"{V1}/shots/{shot['id']}", json={"confirmed": True})
            resp.raise_for_status()
            self.post("/gates/storyboard/confirm", {"scope_id": EPISODE})
            shot = shots(self)["1-04"]
            self.say(f"   1-04 audio_mode → {shot['audio_mode']}")
        return shot

    def h3(self) -> None:
        self.limit("h3")
        shot = self.native_104()
        v = self.take(
            "h3-1-04", shot["video_product_id"], f"h3: 1-04 原生同步 · {H3_API}", where="api",
            model=H3_API,
        )  # fmt: skip
        if v["model_key"] != H3_API:
            raise Stop(f"h3: ran on {v['model_key']}")
        sent = v["params"].get("request") or {}
        self.say(
            f"   payload {v['payload'].get('resolution')} refs {v['payload'].get('refs')} "
            f"voices {v['payload'].get('voices')} rewritten {v['payload'].get('prompt_ir')}; "
            f"sent {sorted(k for k in sent if k not in ('prompt',))}"
        )

    def regen(self) -> None:
        self.limit("regen")
        shot = self.native_104()
        product = shot["video_product_id"]
        drafts = [
            v
            for v in self.get(f"/products/{product}")["versions"]
            if v["where"] == "local" and v["model_key"] == "comfy/h3-r2v"
        ]
        if not drafts:
            raise Stop("regen: no local 原生同步 draft of 1-04 (run local_video.py tts104 first)")
        draft = drafts[-1]
        self.say(f"== regen: 1-04 本地草稿 {draft['id'][:8]} → {REGEN}")
        final = self.final(product, "regen-1-04", draft, REGEN)
        keep_take(self, "regen-1-04", final)
        cost = sum(float(c.cost_usd or 0) for c in self.calls() if c.model_key == REGEN)
        self.say(f"   billed ${cost:.4f}; spent so far ${self.spent():.4f}")

    def seedance(self) -> None:
        self.limit("seedance")
        from drama_series_agent.modelhub.adapters import seedance

        seedance.resolution_tier = lambda spec, params: "720p"  # type: ignore[assignment]
        shot = shots(self)["1-01"]
        v = self.take(
            "seedance-1-01", shot["video_product_id"], f"seedance: 1-01 · {SEEDANCE}（720p）",
            where="api", model=SEEDANCE,
        )  # fmt: skip
        if v["model_key"] != SEEDANCE:
            raise Stop(f"seedance: ran on {v['model_key']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--home", required=True, help="the data directory a local_video.py run kept")
    ap.add_argument("--cap", type=float, default=3.0, help="hard spending cap in USD")
    ap.add_argument("--only", default=",".join(STEPS), help="steps to run, comma-separated")
    ap.add_argument("--studio", default="http://127.0.0.1:8000", help="the studio you have open")
    args = ap.parse_args()
    only = [s for s in args.only.split(",") if s]
    unknown = set(only) - set(STEPS)
    if unknown:
        raise SystemExit(f"unknown steps: {', '.join(sorted(unknown))}")
    if os.environ.get("DRAMA_LIVE") != "1":
        print("real calls cost money: set DRAMA_LIVE=1 to run this", file=sys.stderr)
        return 2
    for _provider, (step, _models, key) in PROVIDERS.items():
        if step in only and secrets.has_secret(key) == "none":
            print(f"no {key} in the keyring or .env", file=sys.stderr)
            return 2

    facts = studio_facts(args.studio.rstrip("/"))
    home = Path(args.home)
    out = home.parent / "live-out"
    out.mkdir(exist_ok=True)
    os.environ.update({"DRAMA_HOME": str(home), "DRAMA_MOCK": "1"})
    os.environ.pop("DRAMA_REAL_LOCAL", None)

    from fastapi.testclient import TestClient

    from drama_series_agent.api.app import create_app
    from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget
    from drama_series_agent.modelhub.adapters.local_python import RuntimePaths

    code = 0
    headers = {"X-Drama-Studio": "1"}
    with TestClient(create_app(), base_url="http://127.0.0.1", headers=headers) as client:
        state = client.app.state.studio  # type: ignore[attr-defined]

        async def runtime_paths() -> RuntimePaths:
            return RuntimePaths(envs=REAL_HOME / "envs", models=facts["models"])

        async def comfy_target() -> ComfyTarget:
            return ComfyTarget(url=facts["comfy_url"], env_hash=facts["env_hash"])

        state.setup.runtime_paths = runtime_paths
        state.setup.comfy_target = comfy_target
        # The demo is seeded (Mock mode); from here on every model is real.
        state.registry.mock = False
        state.registry._adapters.clear()
        smoke = VideoSmoke(client, state, out, args.cap, mock=False)
        smoke.say(f"M5 live smoke · {datetime.now():%Y-%m-%d %H:%M} · cap ${args.cap} · {only}")
        try:
            comfy = httpx.get(f"{facts['comfy_url']}/system_stats", timeout=10).json()
            version = comfy.get("system", {}).get("comfyui_version")
            smoke.say(f"ComfyUI {version} at {facts['comfy_url']}; data {home}")
            smoke.connections(only)
            for step in STEPS:
                if step in only:
                    getattr(smoke, step)()
        except (Stop, RuntimeError, httpx.HTTPError) as exc:
            smoke.say(f"\nSTOPPED: {exc}")
            code = 1
        finally:
            smoke.report_calls()
        smoke.say()
        smoke.say(f"spent ${smoke.spent():.4f} of ${args.cap}")
        smoke.say(f"result: {'all steps ran' if code == 0 else 'STOPPED'}")
        smoke.say(f"files: {out}")
    full = code == 0 and set(only) == set(STEPS)
    report = REPORT if full else out / "report.txt"
    with open(report, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(smoke.lines) + "\n")
    print(f"report: {report}")
    return code


if __name__ == "__main__":
    sys.exit(main())
