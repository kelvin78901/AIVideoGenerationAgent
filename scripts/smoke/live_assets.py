"""Live smoke test (M3 plan step 14): the API picture and voice models, for real, through the
studio's own components on the Mock demo series. Real calls cost real money (about $1.8).

    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/live_assets.py [--cap 3]
        [--only img,text,voice,dub] [--studio http://127.0.0.1:8000] [--keep]
    uv run --no-sync python scripts/smoke/live_assets.py --mock     # the same flow on Mock, free

Every API step finishes one candidate of a free local draft (「用 API 出终版」), so it pays
for one picture or one voice:

- ``img``: 「林晚出租屋」 drafted on Qwen-Image-2512 (local), candidate 0 finished on Nano
  Banana Pro (~$0.134) and on Seedream 5.0 flash (~$0.017);
- ``text``: 「便利贴手写」 drafted locally, candidate 0 finished on GPT Image 2 (~$0.23) and
  read back by RapidOCR (local);
- ``voice``: 林晚's voice unlocked (the demo's is a Mock tone), auditioned on Qwen3-TTS (local),
  candidate 0 finished on MiniMax (China site): a voice design and five emotions (~$1.40, the
  design's ¥9.90 billed on the first), locked;
- ``dub``: her two lines in episode 1 with that voice on MiniMax (~$0.0006; the whispered one
  on speech-2.6-hd); needs ``voice``.

Spending: the provider connection tests run first (free calls). Each component's per-run cap
is set to its step's limit (``LIMITS``), so a run estimated above it waits for a yes and the
script cancels it instead. A step starts only if the spend so far plus its limit stays under
``--cap``; while it runs the spend is checked every half second and the job is canceled once
it passes. A local draft or audition that fell back to an API stops the script.

The app runs in this process on a temporary data directory with the Mock demo series, then
switches every model to real (``DRAMA_MOCK=0`` would skip the demo). Local models use the
install folder and ComfyUI of the studio you have open (its last scan; it is not touched), so
ComfyUI must be running. Keys come from the OS keyring (模型与兜底 → 填密钥), else ``.env``.
The pictures and clips are copied to ``<tmp>/out``; a full live run writes its report to
``docs/studio/reports/m3-live-smoke.txt``.
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
from local_assets import REAL_HOME, V1, Smoke, VramMeter, studio_facts

from drama_series_agent.core import secrets

REPORT = Path(__file__).resolve().parents[2] / "docs" / "studio" / "reports" / "m3-live-smoke.txt"
STEPS = ["img", "text", "voice", "dub"]
EPISODE = "demo-e1"
ROOM, NOTE, VOICE = "demo-p-asset-room", "demo-p-asset-txt1", "demo-p-asset-vlinwan"
# Per-run caps (USD) while the smoke runs: each step's estimate with some room.
LIMITS = {"img": 0.20, "text": 0.30, "voice": 1.60, "dub": 0.01}
FINALS = {"google": "google/nano-banana-pro", "seedream": "volc/seedream-5.0"}
TEXT_MODEL = "openai/gpt-image-2"
VOICE_MODEL = "minimax/speech-2.8-hd"
# Provider → the media models of ours its connection test must find, and the step needing it.
PROVIDERS = {
    "google_llm": ("img", [FINALS["google"]], "GEMINI_API_KEY"),
    "volcengine": ("img", [FINALS["seedream"]], "ARK_API_KEY"),
    "openai_llm": ("text", [TEXT_MODEL], "OPENAI_API_KEY"),
    "minimax_llm": ("voice", [VOICE_MODEL], "MINIMAX_API_KEY"),
}
TERMINAL = ("succeeded", "failed", "canceled")


class Stop(Exception):
    """Stopped on purpose (spending, a failed step); the message says why."""


class LiveSmoke(Smoke):
    def __init__(self, client: Any, state: Any, out: Path, cap: float, *, mock: bool) -> None:
        super().__init__(client, state, out, VramMeter())
        self.cap = cap
        self.mock = mock
        self.first_call = self._last_call_id()
        self.jobs: list[tuple[str, str, float, float]] = []  # (label, job id, seconds, estimate)

    # ------------------------------------------------------------------ spending

    def _last_call_id(self) -> int:
        from drama_series_agent.core.models_db import ModelCall

        return max((c.id or 0 for c in self.rows(ModelCall)), default=0)

    def calls(self) -> list[Any]:
        from drama_series_agent.core.models_db import ModelCall

        rows = [c for c in self.rows(ModelCall) if (c.id or 0) > self.first_call]
        return sorted(rows, key=lambda c: c.id or 0)

    def spent(self) -> float:
        return sum(float(c.cost_usd or 0) for c in self.calls())

    def caps(self) -> None:
        for component, limit in LIMITS.items():
            body = {
                "scope": "component",
                "scope_id": None,
                "component_id": component,
                "data": {"per_call_cap_usd": limit},
            }
            resp = self.client.put(f"{V1}/config/override", json=body)
            resp.raise_for_status()

    def budget(self, step: str) -> None:
        spent, limit = self.spent(), LIMITS[step]
        if spent + limit > self.cap:
            raise Stop(f"{step}: ${spent:.4f} spent + its ${limit} limit passes ${self.cap}")

    def follow(self, job: dict[str, Any], label: str) -> dict[str, Any]:
        """Wait for a job; cancel it if it asks first or the spend passes the cap."""
        started = time.monotonic()
        while job["state"] not in TERMINAL:
            if job["state"] == "waiting_confirm":
                self.post(f"/jobs/{job['id']}/cancel")
                confirm = (job.get("params") or {}).get("confirm")
                raise Stop(f"{label}: the studio asks first ({confirm}); canceled, not run")
            if self.spent() > self.cap:
                self.post(f"/jobs/{job['id']}/cancel")
                raise Stop(f"{label}: canceled, the spend passed the ${self.cap} cap")
            time.sleep(0.5)
            job = self.get(f"/jobs/{job['id']}")
        seconds = time.monotonic() - started
        self.jobs.append((label, job["id"], seconds, float(job.get("est_cost_usd") or 0)))
        if job["state"] != "succeeded":
            raise Stop(f"{label}: {job['state']} {job.get('error') or ''}")
        self.say(f"   {label}: done in {seconds:.1f} s")
        return job

    def start(self, product_id: str, label: str, **body: Any) -> dict[str, Any]:
        return self.follow(self.run(product_id, **body), label)

    # ------------------------------------------------------------------ checks

    def connections(self, steps: list[str]) -> None:
        """Free calls: each provider's key and the model ids we use (no generation)."""
        for provider, (step, models, _key) in PROVIDERS.items():
            if step not in steps:
                continue
            test = self.post(f"/providers/{provider}/test")
            media = {m["key"]: m for m in test.get("media") or []}
            for key in models:
                check = media.get(key)
                if not test["ok"] or check is None or not check["ok"]:
                    detail = check["detail"] if check else test["detail"]
                    raise Stop(f"{provider} connection test failed for {key}: {detail}")
            self.say(f"connection {provider}: ok ({', '.join(models)})")

    def local_draft(self, product_id: str, label: str, model_prefix: str) -> dict[str, Any]:
        self.start(product_id, f"{label} draft")
        draft = self.latest(product_id)
        if draft["stage"] != "draft" or draft["where"] != "local":
            raise Stop(f"{label}: the draft fell back to {draft['model_key']} (it was to be local)")
        if not self.mock and not draft["model_key"].startswith(model_prefix):
            raise Stop(f"{label}: the draft is {draft['model_key']}")
        return draft

    def final(
        self, product_id: str, label: str, draft: dict[str, Any], model: str
    ) -> dict[str, Any]:
        params = {"source_version_id": draft["id"], "source_idx": 0}
        self.start(product_id, label, where="api", model=model, params=params)
        version = self.latest(product_id)
        if (version["stage"], version["model_key"]) != ("final", model):
            raise Stop(f"{label}: got {version['stage']} on {version['model_key']}, not {model}")
        return version

    # ------------------------------------------------------------------ steps

    def img(self) -> None:
        self.say("== img: 林晚出租屋 · local draft → Nano Banana Pro, Seedream 5.0")
        self.budget("img")
        draft = self.local_draft(ROOM, "room", "comfy/")
        self.keep_files("room-draft", draft)
        for name, model in FINALS.items():
            self.keep_files(f"room-{name}", self.final(ROOM, f"room final {name}", draft, model))

    def text(self) -> None:
        self.say("== text: 便利贴手写 · local draft → GPT Image 2, RapidOCR")
        self.budget("text")
        settings = self.get("/products/" + NOTE)["versions"][-1].get("payload", {}).get("text")
        self.say(f"   text settings: {settings}")
        draft = self.local_draft(NOTE, "note", "comfy/")
        self.keep_files("note-draft", draft)
        self.keep_files("note-gpt", self.final(NOTE, "note final gpt-image-2", draft, TEXT_MODEL))

    def voice(self) -> None:
        self.say("== voice: 林晚 · unlocked, Qwen3-TTS audition → MiniMax design + 5 emotions")
        self.budget("voice")
        # The demo's voice is a locked Mock tone: unlock it (her lines are marked stale).
        target = {"kind": "asset_unlock", "target_id": "vlinwan", "patch": {}}
        impact = self.post("/impact/preview", target)
        self.post("/impact/apply", {"impact_id": impact["id"], "action": "mark"})
        draft = self.local_draft(VOICE, "voice audition", "local/")
        self.keep_files("linwan-audition", draft)
        version = self.final(VOICE, "voice final minimax", draft, VOICE_MODEL)
        payload = version.get("payload") or {}
        self.say(f"   voice_id {payload.get('voice_id')}, emotions {payload.get('emotions')}")
        self.keep_files("linwan-voice", version)
        locked = self.post("/assets/vlinwan/lock", {})
        self.say(f"   lock: {locked.get('status')}")

    def dub(self) -> None:
        self.say("== dub: 林晚's two lines · MiniMax")
        self.budget("dub")
        lines = [x for x in self.get(f"/episodes/{EPISODE}/dub")["lines"]
                 if x["voice_asset_id"] == "vlinwan"][:2]  # fmt: skip
        if len(lines) < 2:
            raise Stop("dub: 林晚 has fewer than two lines in the demo episode")
        started = self.post(f"/episodes/{EPISODE}/dub", {"line_ids": [x["line_id"] for x in lines]})
        for i, job_id in enumerate(started["jobs"]):
            self.follow(self.get(f"/jobs/{job_id}"), f"dub line {i}")
        done = {x["line_id"]: x for x in self.get(f"/episodes/{EPISODE}/dub")["lines"]}
        for i, x in enumerate(lines):
            line = done[x["line_id"]]
            self.say(f"   line {i}: {line['text']} ({line['emotion']}, {line['seconds']:.2f} s)")
            self.keep_files(f"dub-{i}", self.latest(line["product_id"]))

    # ------------------------------------------------------------------ report

    def report_calls(self) -> None:
        rows = self.calls()
        self.say()
        self.say("== model_call")
        self.say("id   component  model                       where  status   fb  out        cost")
        for c in rows:
            out = f"{c.images} img" if c.images else f"{c.chars or 0} chars"
            fb = "yes" if c.is_fallback else "-"
            err = f"  {c.error_code}" if c.error_code else ""
            self.say(
                f"{c.id:<4} {c.component_id or '-':<10} {c.model_key:<27} {c.where:<6} "
                f"{c.status:<8} {fb:<3} {out:<10} ${float(c.cost_usd or 0):.4f}{err}"
            )
        paid = sum(float(c.cost_usd or 0) for c in rows)
        failed = sum(1 for c in rows if c.status != "success")
        self.say(f"total ${paid:.4f} over {len(rows)} calls; failures {failed}")
        self.say()
        self.say("job                          estimate   spent      seconds")
        for label, job_id, seconds, estimate in self.jobs:
            cost = sum(float(c.cost_usd or 0) for c in rows if c.job_id == job_id)
            self.say(f"{label:<28} ${estimate:<9.4f} ${cost:<9.4f} {seconds:.1f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--cap", type=float, default=3.0, help="hard spending cap in USD")
    ap.add_argument("--only", default=",".join(STEPS), help="steps to run, comma-separated")
    ap.add_argument("--studio", default="http://127.0.0.1:8000", help="the studio you have open")
    ap.add_argument("--mock", action="store_true", help="the same flow on Mock (free)")
    ap.add_argument("--keep", action="store_true", help="keep the temporary data directory")
    args = ap.parse_args()
    only = [s for s in args.only.split(",") if s]
    unknown = set(only) - set(STEPS)
    if unknown:
        raise SystemExit(f"unknown steps: {', '.join(sorted(unknown))}")
    if "dub" in only and "voice" not in only:
        raise SystemExit("dub needs voice (林晚's voice is made and locked in the same run)")
    if not args.mock:
        if os.environ.get("DRAMA_LIVE") != "1":
            print("real calls cost money: set DRAMA_LIVE=1 to run this", file=sys.stderr)
            return 2
        for _provider, (step, _models, key) in PROVIDERS.items():
            if step in only and secrets.has_secret(key) == "none":
                print(f"no {key} in the keyring or .env", file=sys.stderr)
                return 2

    facts = None if args.mock else studio_facts(args.studio.rstrip("/"))
    tmp = Path(tempfile.mkdtemp(prefix="drama-live-smoke-"))
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
        smoke = LiveSmoke(client, state, out, args.cap, mock=args.mock)
        mode = "Mock (free)" if args.mock else f"LIVE, cap ${args.cap}"
        smoke.say(f"M3 live smoke · {datetime.now():%Y-%m-%d %H:%M} · {mode} · steps {only}")
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
