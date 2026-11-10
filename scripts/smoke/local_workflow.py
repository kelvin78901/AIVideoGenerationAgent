"""Local smoke test (M5 plan step 14): a community workflow on this machine's ComfyUI, for real:
imported from ComfyUI's own list, checked, its missing node pack installed after a
ComfyUI-Manager snapshot, checked again after ComfyUI restarts, tried, and made 「我的工作流」.
Nothing is spent (``DRAMA_REAL_LOCAL=1``: only ComfyUI runs).

    uv run --no-sync python scripts/smoke/local_workflow.py [--path 社区/文生图-qwen-rgthree.json]
        [--install] [--home <a kept data dir>]

Without ``--install`` it stops after the check and the change list (nothing is changed).
``--install`` **changes the ComfyUI you have open**: a snapshot, then ``git clone`` into its
``custom_nodes`` and ``pip install`` of the pack's requirements into its Python. ComfyUI loads
the pack when it restarts: the script waits (up to ``--wait`` minutes) for you to restart it,
then checks and tries the workflow. The data directory is kept (its snapshot record): a later
``--home <dir>`` reuses it, e.g. to roll back from the studio API.

The default file is ``scripts/smoke/workflows/文生图-qwen-rgthree.json`` (Qwen-Image Lightning with
``Seed (rgthree)``, API format): copy it into ComfyUI's ``user/default/workflows/社区/`` first.

The studio runs in a temporary data directory and scans this computer itself (read-only); the
studio you have open is not touched. The report goes to
``docs/studio/reports/m5-local-workflow.txt``.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from local_assets import V1, Smoke, VramMeter, gpu_query

REPORT = (
    Path(__file__).resolve().parents[2] / "docs" / "studio" / "reports" / "m5-local-workflow.txt"
)
DEFAULT_PATH = "社区/文生图-qwen-rgthree.json"


def wait_scan(smoke: Smoke, limit_s: float = 300) -> dict[str, Any]:
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        profile: dict[str, Any] = smoke.get("/setup/profile")
        if profile.get("phase") not in ("scanning", None):
            return profile
        time.sleep(1)
    raise RuntimeError("the scan did not finish")


def show_check(smoke: Smoke, wf: dict[str, Any]) -> None:
    check = wf.get("check") or {}
    smoke.say(f"   check: {check.get('status')}")
    for p in check.get("missing_packs") or []:
        smoke.say(
            f"   missing pack {p['name']} [{p['source']}] {p.get('url') or 'NO ADDRESS'}: "
            f"{', '.join(p['classes'])}"
        )
    for m in check.get("missing_models") or []:
        smoke.say(f"   missing model {m['folder']}/{m['name']}")
    for x in check.get("problems") or []:
        smoke.say(f"   problem {x['code']} {x.get('params') or ''}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--path", default=DEFAULT_PATH, help="the file in ComfyUI's workflow list")
    ap.add_argument("--install", action="store_true", help="install what is missing (see above)")
    ap.add_argument("--home", help="a data directory an earlier run left (reused)")
    ap.add_argument("--wait", type=float, default=20, help="minutes to wait for the restart")
    args = ap.parse_args()

    home = Path(args.home) if args.home else Path(tempfile.mkdtemp(prefix="drama-local-wf-"))
    out = home / "out"
    out.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        {"DRAMA_HOME": str(home), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1", "DRAMA_SETUP": "real"}
    )

    from fastapi.testclient import TestClient

    from drama_series_agent.api.app import create_app

    meter = VramMeter()
    meter.start()
    headers = {"X-Drama-Studio": "1"}
    with TestClient(create_app(), base_url="http://127.0.0.1", headers=headers) as client:
        state = client.app.state.studio  # type: ignore[attr-defined]
        smoke = Smoke(client, state, out, meter)
        smoke.say(f"M5 local workflow smoke · {datetime.now():%Y-%m-%d %H:%M}")
        smoke.say(f"GPU {' '.join(gpu_query('name'))}; data directory {home}")

        smoke.say("== scan (read-only)")
        profile = smoke.get("/setup/profile")
        if profile.get("phase") != "scanned" or not args.home:
            smoke.post("/setup/scan")
            time.sleep(1)
            profile = wait_scan(smoke)
        comfy_url = (smoke.get("/comfy/env").get("comfy") or {}).get("url")
        smoke.say(f"   phase {profile.get('phase')}; ComfyUI at {comfy_url}")
        if not comfy_url:
            smoke.say("   no ComfyUI found: start it first")
            return 1
        stats = httpx.get(f"{comfy_url}/system_stats", timeout=10).json()
        smoke.say(f"   ComfyUI {stats.get('system', {}).get('comfyui_version')}")

        smoke.say(f"== import {args.path}")
        files = smoke.get("/comfy/workflows")
        listed = next((f for f in files if f["path"] == args.path), None)
        if listed is None:
            smoke.say(f"   not in ComfyUI's list ({len(files)} files)")
            return 1
        if listed.get("imported_as"):
            wf = smoke.get(f"/workflows/{listed['imported_as']}")
            smoke.say(f"   already imported as {wf['name']} ({wf['id']})")
        else:
            wf = smoke.post("/workflows/import", {"comfy_path": args.path})
            smoke.say(f"   imported as {wf['name']} ({wf['id']}), tier {wf['tier']}")
        wid = wf["id"]
        smoke.say(f"   components {wf['components']}, {len(wf['nodes'])} nodes")
        for b in wf["bindings"]:
            where = f"{b['node_title']} ({b['node_class']}).{b.get('field') or ''}"
            smoke.say(f"   binding {b['slot']} → {where} [{b['state']}]")
        show_check(smoke, wf)

        guessed = [b for b in wf["bindings"] if b["state"] == "guessed"]
        if guessed:
            resp = client.put(f"{V1}/workflows/{wid}/bindings", json=wf["bindings"])
            resp.raise_for_status()
            smoke.say(f"   confirmed {len(guessed)} guessed binding(s)")

        missing = (wf.get("check") or {}).get("missing_packs") or []
        if missing:
            changes = smoke.post(f"/workflows/{wid}/deps")["changes"]
            smoke.say("== the change list (the 6.4.1 dialog)")
            for c in changes:
                smoke.say(f"   {c['code']} {c.get('params')}")
            if not args.install:
                smoke.say("   stopped here: run again with --install (and --home) to install")
                return finish(smoke, home)
            smoke.say("== install (snapshot first)")
            done = smoke.post(f"/workflows/{wid}/deps/install")
            smoke.say(f"   snapshot {done.get('snapshot')}")
            smoke.say(
                f"   packs {done['packs']}, restart {done['restart_required']}, "
                f"failed {done['failed']}"
            )
            if done.get("failed"):
                smoke.ok = False
                return finish(smoke, home)
            classes = [c for p in missing for c in p["classes"]]
            smoke.say(f"== restart ComfyUI now: waiting for {', '.join(classes)}")
            deadline = time.monotonic() + args.wait * 60
            while time.monotonic() < deadline:
                try:
                    ok = all(
                        httpx.get(f"{comfy_url}/object_info/{quote(c)}", timeout=5).json()
                        for c in classes
                    )
                except (httpx.HTTPError, ValueError):
                    ok = False
                if ok:
                    break
                time.sleep(3)
            else:
                smoke.ok = False
                smoke.say("   ComfyUI did not come back with them")
                return finish(smoke, home)
            smoke.say("   loaded")

        smoke.say("== check again")
        wf = smoke.post(f"/workflows/{wid}/check")
        show_check(smoke, wf)
        if (wf.get("check") or {}).get("status") != "ok":
            smoke.ok = False
            return finish(smoke, home)

        def trial() -> list[str]:
            got = smoke.post(f"/workflows/{wid}/trial", {})
            return [got["trial"]["job_id"]]

        if smoke.step("trial", "试跑（示例输入，真跑 ComfyUI）", trial):
            wf = smoke.get(f"/workflows/{wid}")
            t = wf.get("trial") or {}
            smoke.say(
                f"   trial {t.get('status')} {t.get('w')}x{t.get('h')}, "
                f"{t.get('duration_s')} s, VRAM {t.get('vram_gb')} GB, error {t.get('error')}"
            )
            if t.get("status") == "passed":
                resp = client.patch(f"{V1}/workflows/{wid}", json={"tier": "mine"})
                resp.raise_for_status()
                smoke.say(f"   tier → {resp.json()['tier']}")
            else:
                smoke.ok = False
    meter.stop()
    return finish(smoke, home)


def finish(smoke: Smoke, home: Path) -> int:
    smoke.say()
    smoke.say(f"result: {'ok' if smoke.ok else 'SOMETHING FAILED'}; data directory kept: {home}")
    REPORT.write_text("\n".join(smoke.lines) + "\n", encoding="utf-8", newline="\n")
    print(f"report: {REPORT}")
    return 0 if smoke.ok else 1


if __name__ == "__main__":
    sys.exit(main())
