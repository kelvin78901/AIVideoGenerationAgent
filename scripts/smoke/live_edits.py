"""Picture edits smoke test (M5.5 plan step 18): 以这张为底重画, 局部修复 and 图片超分, for real,
through the studio's own components on the Mock demo series.

    uv run --no-sync python scripts/smoke/live_edits.py --only check,local     # free: ComfyUI only
    DRAMA_LIVE=1 uv run --no-sync python scripts/smoke/live_edits.py [--cap 1]  # + two API pictures
        [--only check,local,api] [--base <png>] [--studio http://127.0.0.1:8000] [--keep]

Steps, in this order:

- ``check``: the three local workflows (``flux3-klein-redraw``, ``klein-inpaint``,
  ``seedvr2-img``) checked against this machine's ComfyUI (node classes, model files,
  bindings), then each tried once with its sample inputs (试跑);
- ``local``: a real keyframe (``--base``, run 20's 1-04: 林晚 holding the sticky note, its
  writing garbled) uploaded as 1-04's first frame (cut to 9:16, the delivery size), then
  redrawn on FLUX 3 Klein (her coat dark navy, 改动幅度 0.5), its note inpainted on Klein
  (the mask over the note: 「等我」 handwritten) and the redraw upscaled on SeedVR2 to
  1080×1920. A local run that fell back to an API is reported as NOT LOCAL;
- ``api``: the same upload redrawn on Nano Banana 2.1 (~$0.05) and its note inpainted on
  GPT Image 2 with the mask (~$0.2). Needs ``DRAMA_LIVE=1``.

Spending (``api``, and a local run's fallback): the providers' connection tests first (free);
each component's per-run cap is set (``LIMITS``), a run over it waits for a yes and is canceled;
a step starts only if the spend so far plus its limit stays under ``--cap``, and a job is
canceled once the spend passes it.

The app runs in this process on a temporary data directory with the Mock demo series, then
switches every model to real. Local models use the install folder and ComfyUI of the studio you
have open (its last scan; it is not touched). Do not run it next to the full pytest. A run of
every step writes the report and side-by-side JPEG sheets to
``docs/studio/reports/m55-edits-smoke/`` and the full-size pictures to
``docs/studio/reports/m5-local-smoke/originals/m55-edits/`` (not in git); otherwise both stay in
``<tmp>/out``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import sys
import tempfile
import time
import zlib
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from live_assets import LiveSmoke, Stop
from local_assets import REAL_HOME, V1, studio_facts

from drama_series_agent.core import secrets

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "docs" / "studio" / "reports" / "m55-edits-smoke"
# Full-size pictures stay out of git (.gitignore), like the other local checks' originals.
ORIGINALS = ROOT / "docs" / "studio" / "reports" / "m5-local-smoke" / "originals" / "m55-edits"
# Side-by-side sheets for the report: (name, pictures); and the note at full size.
SHEETS = [
    ("local", ["upload", "local-redraw", "local-inpaint", "local-upscale"]),
    ("api", ["upload", "api-redraw", "api-inpaint"]),
]
BASE = ROOT / "docs/studio/reports/m5-local-smoke/originals/run20-fresh/kf-1-04-candidate-0.png"
STEPS = ["check", "local", "api"]
WORKFLOWS = ("flux3-klein-redraw", "klein-inpaint", "seedvr2-img")
SHOT, KEYFRAME = "demo-shot-1-04", "demo-p-kf-1-04"
LIMITS = {"redraw": 0.10, "inpaint": 0.40}
REDRAW_MODEL, INPAINT_MODEL = "google/nano-banana-2.1", "openai/gpt-image-2"
PROVIDERS = {
    "google_llm": ([REDRAW_MODEL], "GEMINI_API_KEY"),
    "openai_llm": ([INPAINT_MODEL], "OPENAI_API_KEY"),
}
REDRAW_PROMPT = "她的风衣换成深海军蓝色，其余不变"
INPAINT_PROMPT = "黄色便利贴，上面用黑色圆珠笔手写两个字「等我」，字迹潦草"
# The note in the 1080×1920 upload of run 20's 1-04 (378–540 × 958–1088 at 928×1664), with room.
NOTE_BOX = (420, 1090, 650, 1290)


def sheets(out: Path, dest: Path) -> list[str]:
    """JPEG sheets of the pictures side by side (each 464 wide) and the note cropped at full size
    (the delivery size), each well under 300 KB."""
    import subprocess

    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    found = {p.name.split("-candidate")[0]: p for p in out.glob("*-candidate-0.*")}
    made = []
    x0, y0, x1, y1 = NOTE_BOX
    crop = f"scale=1080:1920,crop={x1 - x0 + 120}:{y1 - y0 + 120}:{x0 - 60}:{y0 - 60}"
    for name, labels in SHEETS:
        pics = [found[x] for x in labels if x in found]
        for kind, each in (("side", "scale=464:824"), ("note", crop)):
            args = [ffmpeg, "-y", "-loglevel", "error"]
            for pic in pics:
                args += ["-i", str(pic)]
            chain = ";".join(f"[{i}]{each}[p{i}]" for i in range(len(pics)))
            stack = "".join(f"[p{i}]" for i in range(len(pics)))
            target = dest / f"{kind}-{name}.jpg"
            args += ["-filter_complex", f"{chain};{stack}hstack={len(pics)}", "-q:v", "4"]
            subprocess.run([*args, str(target)], check=True)
            made.append(target.name)
    return made


def mask_png(w: int, h: int, box: tuple[int, int, int, int]) -> bytes:
    """A grey PNG of ``w × h``, white (= change) inside ``box`` (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    off, on = b"\x00" * w, b"\x00" * x0 + b"\xff" * (x1 - x0) + b"\x00" * (w - x1)
    raw = b"".join(b"\x00" + (on if y0 <= y < y1 else off) for y in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    head = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", head)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


class EditsSmoke(LiveSmoke):
    def __init__(self, *args: Any, base: Path, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.base = base
        self.upload: dict[str, Any] | None = None

    def caps(self) -> None:
        for component, limit in LIMITS.items():
            body = {"scope": "component", "scope_id": None, "component_id": component,
                    "data": {"per_call_cap_usd": limit}}  # fmt: skip
            self.client.put(f"{V1}/config/override", json=body).raise_for_status()

    def budget(self, step: str) -> None:
        spent, limit = self.spent(), LIMITS[step]
        if spent + limit > self.cap:
            raise Stop(f"{step}: ${spent:.4f} spent + its ${limit} limit passes ${self.cap}")

    def connections(self, steps: list[str]) -> None:
        if "api" not in steps:
            return
        for provider, (models, _key) in PROVIDERS.items():
            test = self.post(f"/providers/{provider}/test")
            media = {m["key"]: m for m in test.get("media") or []}
            for key in models:
                check = media.get(key)
                if not test["ok"] or check is None or not check["ok"]:
                    detail = check["detail"] if check else test["detail"]
                    raise Stop(f"{provider} connection test failed for {key}: {detail}")
            self.say(f"connection {provider}: ok ({', '.join(models)})")

    # ------------------------------------------------------------------ helpers

    def edited(self, label: str, job: dict[str, Any], origin: str, where: str) -> dict[str, Any]:
        """The version a redraw / inpaint / upscale job made, checked and kept."""
        self.follow(job, label)
        v = self.latest(KEYFRAME)
        if v["origin"] != origin or v["job_id"] != job["id"]:
            raise Stop(f"{label}: the newest version is {v['origin']} from {v['job_id']}")
        if v["where"] != where:
            self.ok = False
            self.say(f"   NOT {where.upper()}: {v['model_key']} [{v['where']}] (a fallback ran)")
        payload = {k: v["payload"][k] for k in ("strength", "mask") if k in (v["payload"] or {})}
        self.say(f"   {v['model_key']} [{v['where']}] parent {v['parent_version_id']} {payload}")
        self.keep_files(label.replace(" ", "-"), v)
        return v

    def uploaded(self) -> dict[str, Any]:
        if self.upload is None:
            # The demo confirms every shot; a confirmed shot's first frame takes no upload.
            self.client.patch(f"{V1}/shots/{SHOT}", json={"confirmed": False}).raise_for_status()
            resp = self.client.post(
                f"{V1}/shots/{SHOT}/keyframe/upload",
                files={"file": (self.base.name, self.base.read_bytes(), "image/png")},
            )
            if resp.status_code >= 400:
                raise Stop(f"upload: {resp.status_code} {resp.text[:300]}")
            self.upload = resp.json()["versions"][-1]
            crop = self.upload["payload"].get("crop")
            self.say(f"== upload: {self.base.name} as 1-04's first frame, cut {crop}")
            self.keep_files("upload", self.upload)
        return self.upload

    def inpaint(self, version: dict[str, Any], where: str, model: str | None) -> dict[str, Any]:
        (cand,) = [f for f in version["files"] if f["role"] == "candidate"]
        mask = mask_png(cand["w"], cand["h"], NOTE_BOX)
        (self.out / "mask.png").write_bytes(mask)
        data = {"idx": "0", "prompt": INPAINT_PROMPT, "where": where}
        if model:
            data["model"] = model
        resp = self.client.post(
            f"{V1}/versions/{version['id']}/inpaint",
            files={"mask": ("mask.png", mask, "image/png")},
            data=data,
        )
        if resp.status_code >= 400:
            raise Stop(f"inpaint: {resp.status_code} {resp.text[:300]}")
        return dict(resp.json())

    # ------------------------------------------------------------------ steps

    def check(self) -> None:
        listed = {w["slug"]: w for w in self.get("/workflows")}
        for slug in WORKFLOWS:
            wf = listed.get(slug)
            if wf is None:
                raise Stop(f"check: no workflow {slug}")
            self.say(f"== check {slug}")
            wf = self.post(f"/workflows/{wf['id']}/check")
            check = wf.get("check") or {}
            self.say(f"   check: {check.get('status')}")
            for p in check.get("missing_packs") or []:
                self.say(f"   missing pack {p['name']}: {', '.join(p['classes'])}")
            for m in check.get("missing_models") or []:
                self.say(f"   missing model {m['folder']}/{m['name']}")
            for x in check.get("problems") or []:
                self.say(f"   problem {x['code']} {x.get('params') or ''}")
            if check.get("status") != "ok":
                self.ok = False
                continue
            started = time.monotonic()
            got = self.post(f"/workflows/{wf['id']}/trial", {})
            job = self.get(f"/jobs/{got['trial']['job_id']}")
            while job["state"] not in ("succeeded", "failed", "canceled"):
                time.sleep(0.5)
                job = self.get(f"/jobs/{job['id']}")
            t = self.get(f"/workflows/{wf['id']}").get("trial") or {}
            self.say(
                f"   trial {t.get('status')} {t.get('w')}x{t.get('h')}: the job "
                f"{time.monotonic() - started:.1f} s, the run {t.get('duration_s')} s "
                f"{t.get('error') or ''}"
            )
            if t.get("status") != "passed":
                self.ok = False

    def local(self) -> None:
        base = self.uploaded()
        self.say("== local redraw: FLUX 3 Klein, 改动幅度 0.5")
        body = {"idx": 0, "prompt": REDRAW_PROMPT, "strength": 0.5, "where": "local"}
        job = self.post(f"/versions/{base['id']}/redraw", body)
        redrawn = self.edited("local redraw", job, "redraw", "local")
        self.say("== local inpaint: Klein, the note")
        self.edited("local inpaint", self.inpaint(base, "local", None), "inpaint", "local")
        self.say("== local upscale: SeedVR2, the redraw → 1080×1920")
        job = self.post(f"/versions/{redrawn['id']}/upscale", {"idx": 0})
        self.edited("local upscale", job, "upscale", "local")

    def api(self) -> None:
        base = self.uploaded()
        self.say(f"== api redraw: {REDRAW_MODEL}")
        self.budget("redraw")
        body = {"idx": 0, "prompt": REDRAW_PROMPT, "strength": 0.5, "where": "api",
                "model": REDRAW_MODEL}  # fmt: skip
        job = self.post(f"/versions/{base['id']}/redraw", body)
        self.edited("api redraw", job, "redraw", "api")
        self.say(f"== api inpaint: {INPAINT_MODEL} with the mask")
        self.budget("inpaint")
        job = self.inpaint(base, "api", INPAINT_MODEL)
        self.edited("api inpaint", job, "inpaint", "api")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--cap", type=float, default=1.0, help="hard spending cap in USD")
    ap.add_argument("--only", default=",".join(STEPS), help="steps to run, comma-separated")
    ap.add_argument("--base", default=str(BASE), help="the keyframe picture to start from")
    ap.add_argument("--studio", default="http://127.0.0.1:8000", help="the studio you have open")
    ap.add_argument("--keep", action="store_true", help="keep the temporary data directory")
    args = ap.parse_args()
    only = [s for s in args.only.split(",") if s]
    unknown = set(only) - set(STEPS)
    if unknown:
        raise SystemExit(f"unknown steps: {', '.join(sorted(unknown))}")
    if "api" in only:
        if os.environ.get("DRAMA_LIVE") != "1":
            print("the api step costs money: set DRAMA_LIVE=1 to run it", file=sys.stderr)
            return 2
        for _models, key in PROVIDERS.values():
            if secrets.has_secret(key) == "none":
                print(f"no {key} in the keyring or .env", file=sys.stderr)
                return 2

    facts = studio_facts(args.studio.rstrip("/"))
    tmp = Path(tempfile.mkdtemp(prefix="drama-edits-smoke-"))
    out = tmp / "out"
    out.mkdir()
    os.environ.update({"DRAMA_HOME": str(tmp / "home"), "DRAMA_MOCK": "1"})
    os.environ.pop("DRAMA_REAL_LOCAL", None)

    from fastapi.testclient import TestClient

    from drama_series_agent.api.app import create_app
    from drama_series_agent.modelhub.adapters.comfyui import ComfyTarget
    from drama_series_agent.modelhub.adapters.local_python import RuntimePaths
    from drama_series_agent.wflib.comfy import HttpComfy

    async def runtime_paths() -> RuntimePaths:
        return RuntimePaths(envs=REAL_HOME / "envs", models=facts["models"])

    async def comfy_target() -> ComfyTarget:
        return ComfyTarget(url=facts["comfy_url"], env_hash=facts["env_hash"])

    async def comfy_url() -> str:
        return str(facts["comfy_url"])

    code = 0
    headers = {"X-Drama-Studio": "1"}
    with TestClient(create_app(), base_url="http://127.0.0.1", headers=headers) as client:
        state = client.app.state.studio  # type: ignore[attr-defined]
        state.setup.runtime_paths = runtime_paths
        state.setup.comfy_target = comfy_target
        # The workflow library checks against this machine's ComfyUI, not the sample machine's.
        state.workflows.comfy = lambda: HttpComfy(comfy_url, state.http_transport)
        # The demo is seeded (Mock mode); from here on every model is real.
        state.registry.mock = False
        state.registry._adapters.clear()
        smoke = EditsSmoke(client, state, out, args.cap, mock=False, base=Path(args.base))
        smoke.say(f"M5.5 picture edits smoke · {datetime.now():%Y-%m-%d %H:%M} · cap ${args.cap}")
        smoke.say(f"steps {only}; base {Path(args.base).name}")
        try:
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
        if code == 0 and not smoke.ok:
            code = 1
        smoke.say()
        smoke.say(f"result: {'every step ran' if code == 0 else 'PROBLEMS (see above)'}")
    full = code == 0 and set(only) == set(STEPS)
    if full:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        ORIGINALS.mkdir(parents=True, exist_ok=True)
        for f in out.iterdir():
            shutil.copyfile(f, ORIGINALS / f.name)
        smoke.say(f"sheets: {', '.join(sheets(out, REPORT_DIR))}; originals in {ORIGINALS}")
    report = (REPORT_DIR if full else out) / "report.txt"
    with open(report, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(smoke.lines) + "\n")
    print(f"report: {report}\nfiles: {out}")
    if not args.keep:
        shutil.rmtree(tmp / "home", ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
