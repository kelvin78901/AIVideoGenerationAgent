"""Local smoke test (M3 plan step 13): this machine's local models, for real, through the
studio's own components on the Mock demo series. Nothing is spent: API and writing models stay
Mock (``DRAMA_REAL_LOCAL=1``), only the ComfyUI workflows and the Python workers run.

    uv run --no-sync python scripts/smoke/local_assets.py [--studio http://127.0.0.1:8000]
        [--only img,text,views,voice,voice_final,dub] [--keep]

Steps, in this order (ComfyUI first, then the TTS models, so the VRAM lease changes hands):

- ``img``: 「林晚出租屋」 drafts on Qwen-Image-2512 (``comfy/qwen-image``), four candidates;
- ``text``: 「便利贴手写」 drafts on Qwen-Image-2512, each read back by RapidOCR;
- ``views``: 周屿 drawn on Qwen-Image-2512 and locked (the demo's locked pictures are Mock
  placeholders), then his six views from that picture on Qwen-Image-Edit-2511 (40 steps);
- ``voice``: 林晚's voice unlocked (the demo's is a Mock tone) and auditioned again on Qwen3-TTS
  VoiceDesign: three drafts reading her first two lines;
- ``voice_final``: her local final from the first draft: five emotions on IndexTTS-2.5, locked;
- ``dub``: 「全部配音」: her lines go to IndexTTS-2.5 (a local voice has no MiniMax voice_id).

The install folder and the ComfyUI address come from the studio you have open (its last scan;
the studio itself is not touched). The script runs in a temporary data directory with its own
demo. ComfyUI must be running. Each step reports its model calls, seconds and the GPU memory
peak (``nvidia-smi``, the whole card); the pictures and clips are copied to ``<tmp>/out``.
The report goes to ``docs/studio/reports/m3-local-smoke.txt``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

REAL_HOME = Path(os.environ.get("DRAMA_HOME") or Path.home() / ".drama-studio")
REPORT = Path(__file__).resolve().parents[2] / "docs" / "studio" / "reports" / "m3-local-smoke.txt"
STEPS = ["img", "text", "views", "voice", "voice_final", "dub"]
V1 = "/api/v1"
JOB_LIMIT_S = 1800


class VramMeter:
    """``nvidia-smi`` every half second: the card's memory in use (MiB)."""

    def __init__(self) -> None:
        self.samples: list[tuple[float, int]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            used = gpu_query("memory.used")
            if used and used[0].isdigit():
                self.samples.append((time.monotonic(), int(used[0])))
            self._stop.wait(0.5)

    def peak(self, since: float, until: float) -> int | None:
        window = [mb for t, mb in self.samples if since <= t <= until]
        return max(window) if window else None


def gpu_query(field: str) -> list[str]:
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={field}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [x.strip() for x in out.strip().splitlines()[0].split(",")] if out.strip() else []


def env_torch(envs: Path, name: str) -> str:
    python = envs / name / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        return "not installed"
    code = (
        "import torch, sys; ok = torch.cuda.is_available(); "
        "cap = torch.cuda.get_device_capability(0) if ok else None; "
        "print(sys.version.split()[0], torch.__version__, torch.version.cuda, cap, "
        "torch.cuda.get_arch_list() if ok else [])"
    )
    try:
        res = subprocess.run([str(python), "-c", code], capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"error: {exc}"
    lines = res.stdout.strip().splitlines()
    return lines[-1] if lines else f"error: {res.stderr.strip()[-200:]}"


def studio_facts(studio: str) -> dict[str, Any]:
    """Where the open studio installed things, and the ComfyUI its last scan found."""
    profile = httpx.get(f"{studio}{V1}/setup/profile", timeout=10).json()
    comfy = (httpx.get(f"{studio}{V1}/comfy/env", timeout=10).json() or {}).get("comfy") or {}
    install = profile.get("install") or {}
    if not install.get("dir"):
        raise SystemExit("the studio has no install folder yet: install from 环境与安装 first")
    return {
        "models": Path(install["dir"]),
        "comfy_url": comfy.get("url") or "http://127.0.0.1:8188",
        "env_hash": comfy.get("env_hash"),
    }


class Smoke:
    def __init__(self, client: Any, state: Any, out: Path, meter: VramMeter) -> None:
        self.client = client
        self.state = state
        self.out = out
        self.meter = meter
        self.lines: list[str] = []
        self.ok = True

    def say(self, text: str = "") -> None:
        print(text, flush=True)
        self.lines.append(text)

    # ------------------------------------------------------------------ api

    def get(self, path: str, **params: Any) -> Any:
        resp = self.client.get(f"{V1}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        resp = self.client.post(f"{V1}{path}", json=body or {})
        if resp.status_code >= 400:
            raise RuntimeError(f"POST {path}: {resp.status_code} {resp.text[:300]}")
        return resp.json()

    def wait(self, job_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + JOB_LIMIT_S
        while time.monotonic() < deadline:
            job: dict[str, Any] = self.get(f"/jobs/{job_id}")
            if job["state"] in ("succeeded", "failed", "canceled", "waiting_confirm"):
                return job
            time.sleep(0.5)
        raise RuntimeError(f"job {job_id} still running after {JOB_LIMIT_S} s")

    def run(self, product_id: str, **body: Any) -> dict[str, Any]:
        return self.post(f"/products/{product_id}/run", {"mode": "run", **body})

    def rows(self, model: Any) -> list[Any]:
        from sqlmodel import select

        async def read() -> list[Any]:
            async with self.state.db.session() as s:
                return list((await s.exec(select(model))).all())

        return list(self.client.portal.call(read))

    # ------------------------------------------------------------------ steps

    def step(self, name: str, title: str, start: Any) -> dict[str, Any] | None:
        """Run ``start()`` (returns the job ids), wait, report calls, time, memory, files."""
        from drama_series_agent.core.models_db import ModelCall

        self.say(f"== {name}: {title}")
        t0 = time.monotonic()
        try:
            job_ids: list[str] = start()
            jobs = [self.wait(j) for j in job_ids]
        except Exception as exc:  # report and go on with the next step
            self.ok = False
            self.say(f"   FAILED to run: {exc}")
            return None
        t1 = time.monotonic()
        calls = [c for c in self.rows(ModelCall) if c.job_id in job_ids]
        calls.sort(key=lambda c: c.id or 0)
        failed = [j for j in jobs if j["state"] != "succeeded"]
        not_local = [c for c in calls if c.where != "local" and c.status == "success"]
        peak = self.meter.peak(t0, t1)
        self.say(f"   {len(jobs)} job(s) in {t1 - t0:.1f} s, GPU memory peak {peak} MiB")
        for c in calls:
            secs = (
                (c.finished_at - c.started_at).total_seconds()
                if c.finished_at and c.started_at
                else None
            )
            took = f"{secs:.1f} s" if secs is not None else "?"
            extra = f" {c.error_code}" if c.error_code else ""
            what = f"images={c.images}" if c.images else f"audio={c.output_seconds}s"
            self.say(f"   call {c.model_key} [{c.where}] {c.status}{extra} {took} {what}")
        for j in failed:
            self.ok = False
            self.say(f"   job {j['id']} {j['state']}: {j.get('error')}")
        if not_local:
            self.ok = False
            self.say(f"   NOT LOCAL: {[c.model_key for c in not_local]} (a fallback ran)")
        return jobs[-1] if jobs else None

    def latest(self, product_id: str) -> dict[str, Any]:
        version: dict[str, Any] = self.get(f"/products/{product_id}")["versions"][-1]
        return version

    def keep_files(self, label: str, version: dict[str, Any]) -> None:
        store = self.state.store
        kept = []
        for f in version["files"]:
            if f["role"] == "prompt":
                continue
            ext = {"image/png": ".png", "image/jpeg": ".jpg", "audio/wav": ".wav"}.get(
                f["mime"], ""
            )
            idx, line = f.get("idx", ""), f.get("line")
            parts = [label, f["role"], idx, line, f.get("emotion") or f.get("view")]
            name = "-".join(str(p) for p in parts if p not in (None, "")) + ext
            shutil.copyfile(store.path_for(f["sha256"]), self.out / name)
            size = f"{f['w']}x{f['h']}" if f.get("w") else f"{f.get('duration_s') or 0:.2f}s"
            kept.append(f"{name} ({size})")
        self.say(f"   model {version['model_key']} [{version['where']}], files: {', '.join(kept)}")
        if version.get("payload", {}).get("candidates"):
            for i, cand in enumerate(version["payload"]["candidates"]):
                if "ocr" in cand:
                    self.say(f"   OCR #{i}: {cand.get('ocr')!r} ok={cand.get('ocr_ok')}")

    def product_of(self, owner: str, slot: str) -> str:
        listed = self.get("/products", owner=owner)
        return str(next(p["id"] for p in listed if p["slot"] == slot))


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
    envs = REAL_HOME / "envs"
    tmp = Path(tempfile.mkdtemp(prefix="drama-local-smoke-"))
    out = tmp / "out"
    out.mkdir()
    os.environ.update({"DRAMA_HOME": str(tmp / "home"), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1"})

    from fastapi.testclient import TestClient

    from drama_series_agent.api.app import create_app
    from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget
    from drama_series_agent.modelhub.adapters.local_python import RuntimePaths

    async def runtime_paths() -> RuntimePaths:
        return RuntimePaths(envs=envs, models=facts["models"])

    async def comfy_target() -> ComfyTarget:
        return ComfyTarget(url=facts["comfy_url"], env_hash=facts["env_hash"])

    meter = VramMeter()
    meter.start()
    headers = {"X-Drama-Studio": "1"}
    with TestClient(create_app(), base_url="http://127.0.0.1", headers=headers) as client:
        state = client.app.state.studio  # type: ignore[attr-defined]
        state.setup.runtime_paths = runtime_paths
        state.setup.comfy_target = comfy_target
        state.registry._adapters.clear()
        smoke = Smoke(client, state, out, meter)
        name, total = " ".join(gpu_query("name")), " ".join(gpu_query("memory.total"))
        driver, idle = " ".join(gpu_query("driver_version")), " ".join(gpu_query("memory.used"))
        comfy = httpx.get(f"{facts['comfy_url']}/system_stats", timeout=10).json()
        smoke.say(f"M3 local smoke · {datetime.now():%Y-%m-%d %H:%M}")
        smoke.say(f"GPU {name} {total} MiB, driver {driver}; in use before {idle} MiB")
        version = comfy.get("system", {}).get("comfyui_version")
        smoke.say(f"ComfyUI {version} at {facts['comfy_url']}")
        smoke.say(f"models {facts['models']} · envs {envs}")
        for env in ("qwentts", "indextts", "ocr"):
            smoke.say(f"env {env}: {env_torch(envs, env) if env != 'ocr' else _exists(envs, env)}")
        smoke.say()

        if "img" in only:
            pid = "demo-p-asset-room"
            if smoke.step("img", "林晚出租屋 · Qwen-Image-2512", lambda: [smoke.run(pid)["id"]]):
                smoke.keep_files("room", smoke.latest(pid))
        if "text" in only:
            pid = "demo-p-asset-txt1"
            if smoke.step("text", "便利贴手写 · Qwen-Image-2512 + RapidOCR",
                          lambda: [smoke.run(pid)["id"]]):  # fmt: skip
                smoke.keep_files("txt1", smoke.latest(pid))
        if "views" in only:
            views: list[str] = []

            def from_a_real_picture() -> list[str]:
                # The demo's locked pictures are Mock placeholders (a colour and a name): draw
                # 周屿 locally first, lock his first candidate, then draw his views from it.
                smoke.wait(smoke.run("demo-p-asset-zhouyu")["id"])
                drawn = smoke.latest("demo-p-asset-zhouyu")
                if drawn["where"] != "local":  # views from a Mock fallback tell us nothing
                    raise RuntimeError(f"周屿 was not drawn locally: {drawn['model_key']}")
                smoke.client.patch(f"{V1}/assets/zhouyu", json={"pick": 0}).raise_for_status()
                smoke.post("/assets/zhouyu/lock", {})  # starts his views (补视图)
                views.append(smoke.product_of("asset:zhouyu", "ref_views"))
                jobs = [j for j in smoke.get("/jobs", limit=50) if j["product_id"] == views[0]]
                return [jobs[0]["id"]] if jobs else [smoke.run(views[0])["id"]]

            title = "周屿六张视图（先本地出图、锁定）· Qwen-Image-Edit-2511 40 步"
            if smoke.step("views", title, from_a_real_picture):
                smoke.keep_files("zhouyu-ref", smoke.latest("demo-p-asset-zhouyu"))
                smoke.keep_files("zhouyu-views", smoke.latest(views[0]))
        voice = "demo-p-asset-vlinwan"
        if "voice" in only:

            def audition() -> list[str]:
                # The demo's voice is a Mock tone: unlock it (lines marked stale) and redo it.
                target = {"kind": "asset_unlock", "target_id": "vlinwan", "patch": {}}
                impact = smoke.post("/impact/preview", target)
                smoke.post("/impact/apply", {"impact_id": impact["id"], "action": "mark"})
                return [smoke.run(voice)["id"]]

            if smoke.step("voice", "林晚重新试听（先解锁）· Qwen3-TTS VoiceDesign", audition):
                smoke.keep_files("linwan-audition", smoke.latest(voice))
        if "voice_final" in only:
            draft = next(
                (v for v in reversed(smoke.get(f"/products/{voice}")["versions"])
                 if v.get("stage") == "draft" and v["model_key"] == "local/qwen3-tts"), None,
            )  # fmt: skip
            if draft is None:
                smoke.say("== voice_final: skipped (no local audition; run the voice step first)")
            else:
                params = {"source_version_id": draft["id"], "source_idx": 0}

                def final() -> list[str]:
                    return [smoke.run(voice, model="local/indextts2", params=params)["id"]]

                if smoke.step("voice_final", "林晚本地终版 · IndexTTS-2.5 五个情绪", final):
                    smoke.keep_files("linwan-final", smoke.latest(voice))
                    locked = smoke.post("/assets/vlinwan/lock", {})
                    smoke.say(f"   lock: {locked.get('status')}")
        if "dub" in only:

            def dub_all() -> list[str]:
                return list(smoke.post("/episodes/demo-e1/dub").get("jobs") or [])

            # A local voice has no MiniMax voice_id, so its lines go to IndexTTS (local_final).
            if smoke.step("dub", "全部配音 · 林晚的本地音色走 IndexTTS-2.5", dub_all):
                lines = smoke.get("/episodes/demo-e1/dub")["lines"]
                for i, x in enumerate(lines[:3]):
                    smoke.say(f"   line {i}: {x['text']} ({x['emotion']})")
                    smoke.keep_files(f"dub-{i}", smoke.latest(x["product_id"]))
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


def _exists(envs: Path, name: str) -> str:
    python = envs / name / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return "installed" if python.is_file() else "not installed"


if __name__ == "__main__":
    sys.exit(main())
