"""Live smoke test (M2 plan step 13): the demo novel's first chapter through 补全 → 设定提取 →
分集规划 → 第 1 集剧本化 on DeepSeek, with real calls that cost real money.

    DRAMA_LIVE=1 uv run python scripts/smoke/live_script.py [--cap 1.0] [--ask-above 0.2]
    uv run python scripts/smoke/live_script.py --mock     # the same flow on Mock, no spending

The DeepSeek key comes from the OS keyring (模型与兜底 → 填密钥), else ``.env``. The script
starts its own backend (``DRAMA_MOCK=0``) on a free port with a temporary data directory, so
the studio you have open is not touched and Mock stays the default everywhere else.

Spending: a step whose estimate is above ``--ask-above`` is not run (the script stops and says
so; rerun with a higher value once you agree). The backend's per-call cap is set to the same
value, so a model call above it fails instead of spending. The steps never start if the spend
so far plus the estimate would pass ``--cap``, and a running step is canceled once the spend
passes it. At the end it prints the script and every ``model_call`` row.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from drama_series_agent.core import secrets
from drama_series_agent.core.paths import REPO_ROOT

NOVEL = REPO_ROOT / "tests" / "fixtures" / "demo" / "雨停之前.txt"
HEADERS = {"X-Drama-Studio": "1"}
KEY_NAME = "DEEPSEEK_API_KEY"
# All four on DeepSeek: 设定提取 defaults to a local model, the rest already use DeepSeek.
MODELS = {
    "enrich": "deepseek/v4-pro",
    "extract": "deepseek/v4.1-flash",
    "split": "deepseek/v4.1-flash",
    "script": "deepseek/v4-pro",
}
MODEL_IDS = {"deepseek-v4-pro", "deepseek-flash"}


class Stop(Exception):
    """Stopped on purpose (spending, a failed step); the message says why."""


class Smoke:
    def __init__(self, home: Path, cap: float, ask_above: float, *, mock: bool = False) -> None:
        self.home = home
        self.mock = mock
        self.cap = cap
        self.ask_above = ask_above
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}/api/v1"
        self.proc: subprocess.Popen[bytes] | None = None
        self.series = ""
        self.steps: list[tuple[str, str, float]] = []  # (component, job id, seconds)

    # ------------------------------------------------------------------ backend

    def start(self) -> None:
        env = {**os.environ, "DRAMA_HOME": str(self.home), "DRAMA_MOCK": "1" if self.mock else "0"}
        log = (self.home / "backend.log").open("wb")
        cmd = [sys.executable, "-m", "drama_series_agent.studio_cli", "dev", "--port"]
        self.proc = subprocess.Popen([*cmd, str(self.port)], env=env, stdout=log, stderr=log)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                health = httpx.get(f"{self.base}/health", timeout=1)
                if health.status_code == 200:
                    if health.json().get("mock") != self.mock:
                        raise Stop(f"the backend came up with mock={health.json().get('mock')}")
                    return
            except httpx.HTTPError:
                time.sleep(0.3)
        raise Stop(f"the backend did not start (log: {self.home / 'backend.log'})")

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None

    # ------------------------------------------------------------------ http

    def get(self, path: str, **params: Any) -> Any:
        resp = httpx.get(f"{self.base}{path}", params=params or None, timeout=30)
        if resp.status_code != 200:
            raise Stop(f"GET {path}: {resp.status_code} {resp.text[:300]}")
        return resp.json()

    def send(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = httpx.request(method, f"{self.base}{path}", headers=HEADERS, timeout=60, **kwargs)
        if resp.status_code not in (200, 201):
            raise Stop(f"{method} {path}: {resp.status_code} {resp.text[:300]}")
        return resp.json()

    def calls(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = self.get("/dev/model-calls", limit=500)
        return sorted((r for r in rows if r["series_id"] == self.series), key=lambda r: r["id"])

    def spent(self) -> float:
        return sum(float(r["cost_usd"] or 0) for r in self.calls())

    # ------------------------------------------------------------------ steps

    def setup(self) -> None:
        if not self.mock:  # GET /models with the key: free, checks the ids in providers.yaml
            test = self.send("POST", "/providers/deepseek/test")
            if not test["ok"]:
                raise Stop(f"DeepSeek connection test failed: {test['detail']}")
            missing = MODEL_IDS - set(test["models"])
            print(f"DeepSeek models: {', '.join(test['models'])}")
            if missing:
                raise Stop(f"model ids not offered by DeepSeek: {sorted(missing)}")
        for component, model in MODELS.items():
            data = {"mode": "api", "api_model": model, "per_call_cap_usd": self.ask_above}
            override = {"scope": "component", "scope_id": None, "component_id": component}
            self.send("PUT", "/config/override", json={**override, "data": data})

    def import_first_chapter(self) -> None:
        text = NOVEL.read_text(encoding="utf-8")
        first = text[: text.index("第二章")].strip() + "\n"
        self.series = self.send("POST", "/series", json={"title": "雨停之前 · 真实冒烟"})["id"]
        imported = self.send(
            "POST",
            f"/series/{self.series}/novel",
            files={"file": ("雨停之前-第一章.txt", first.encode("utf-8"))},
            data={"rights_confirmed": "true"},
        )
        chapters = ", ".join(f"{c['title']}" for c in imported["chapters"])
        print(f"imported: {chapters} ({len(first)} chars)")

    def product(self, owner: str, component: str) -> dict[str, Any]:
        listed: list[dict[str, Any]] = self.get("/products", owner=owner)
        return next(p for p in listed if p["component_id"] == component)

    def run(self, owner: str, component: str) -> None:
        product = self.product(owner, component)
        estimate = float((product.get("estimate") or {}).get("cost_usd") or 0)
        spent = self.spent()
        model = (product.get("estimate") or {}).get("model_key")
        print(f"\n== {component}: {model}, estimate ${estimate:.4f} (spent so far ${spent:.4f})")
        if estimate > self.ask_above:
            raise Stop(
                f"{component}: the estimate ${estimate:.4f} is above ${self.ask_above:.2f}; "
                "not run (ask first, then rerun with a higher --ask-above)"
            )
        if spent + estimate > self.cap:
            raise Stop(f"{component}: ${spent:.4f} + ${estimate:.4f} passes the ${self.cap} cap")
        started = time.monotonic()
        job = self.send("POST", f"/products/{product['id']}/run", json={"mode": "run"})
        while job["state"] not in ("succeeded", "failed", "canceled", "waiting_confirm"):
            time.sleep(1)
            job = self.get(f"/jobs/{job['id']}")
            if self.spent() > self.cap:
                self.send("POST", f"/jobs/{job['id']}/cancel")
                raise Stop(f"{component}: canceled, the spend passed the ${self.cap} cap")
        seconds = time.monotonic() - started
        self.steps.append((component, job["id"], seconds))
        if job["state"] == "waiting_confirm":
            confirm = job["params"].get("confirm") or {}
            self.send("POST", f"/jobs/{job['id']}/cancel")
            raise Stop(f"{component}: the backend asks first ({confirm}); canceled, not run")
        if job["state"] != "succeeded":
            raise Stop(f"{component}: {job['state']} {job.get('error') or ''}")
        print(f"   done in {seconds:.1f}s")

    def flow(self) -> str:
        owner = f"series:{self.series}"
        self.run(owner, "enrich")
        sugs = self.get(f"/series/{self.series}/suggestions")["suggestions"]
        print(f"   {len(sugs)} suggestions; accepting all")
        self.send("POST", f"/series/{self.series}/suggestions/accept-all")
        self.run(owner, "extract")
        entities = self.get(f"/series/{self.series}/bible")["entities"]
        print(f"   bible: {', '.join(e['name'] for e in entities)}")
        self.run(owner, "split")
        episodes = self.get(f"/series/{self.series}/episodes")
        for e in episodes:
            print(f"   第 {e['idx']} 集 {e['title']}（{len(e['beats'])} 个节拍）")
        e1 = str(episodes[0]["id"])
        self.run(f"episode:{e1}", "script")
        return e1

    # ------------------------------------------------------------------ report

    def print_script(self, episode_id: str) -> None:
        script = self.get(f"/episodes/{episode_id}/script")
        print("\n== 第 1 集剧本")
        for scene in script["scenes"]:
            print(f"\n场 {scene['idx']}　{scene['heading']}")
            for line in (x for x in script["lines"] if x["scene_id"] == scene["id"]):
                tone = f"（{line['tone']}）" if line["tone"] else ""
                if line["type"] in ("dialogue", "vo"):
                    print(f"  {line['character_name'] or '?'}{tone}：{line['text']}")
                else:
                    print(f"  [{line['type']}] {line['text']}")

    def print_calls(self) -> None:
        rows = self.calls()
        print("\n== model_call")
        print("id  component  model                 status   fb  in      out     cost      secs")
        for r in rows:
            secs = _seconds(r["started_at"], r["finished_at"])
            fb = "yes" if r["is_fallback"] else "-"
            print(
                f"{r['id']:<3} {r['component_id'] or '-':<10} {r['model_key']:<21} "
                f"{r['status']:<8} {fb:<3} {r['tokens_in'] or 0:<7} {r['tokens_out'] or 0:<7} "
                f"${float(r['cost_usd'] or 0):<8.4f} {secs:.1f}"
                + (f"  {r['error_code']}" if r["error_code"] else "")
            )
        total = sum(float(r["cost_usd"] or 0) for r in rows)
        failed = [r for r in rows if r["status"] != "success"]
        print(
            f"\ntotal ${total:.4f} over {len(rows)} calls; "
            f"fallbacks {sum(1 for r in rows if r['is_fallback'])}; failures {len(failed)}"
        )
        for component, job_id, seconds in self.steps:
            models = sorted({r["model_key"] for r in rows if r["job_id"] == job_id})
            print(f"  {component:<8} {', '.join(models) or '-':<40} {seconds:.1f}s")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _seconds(start: str | None, end: str | None) -> float:
    if not start or not end:
        return 0.0
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--cap", type=float, default=1.0, help="hard spending cap in USD")
    parser.add_argument(
        "--ask-above", type=float, default=0.2, help="stop before a step estimated above this"
    )
    parser.add_argument("--mock", action="store_true", help="the same flow on Mock (free)")
    args = parser.parse_args()
    if not args.mock:
        if os.environ.get("DRAMA_LIVE") != "1":
            print("real calls cost money: set DRAMA_LIVE=1 to run this", file=sys.stderr)
            return 2
        source = secrets.has_secret(KEY_NAME)
        if source == "none":
            print(f"no {KEY_NAME} in the keyring or .env", file=sys.stderr)
            return 2
        print(f"{KEY_NAME}: from {source}")
    home = Path(tempfile.mkdtemp(prefix="drama-smoke-"))
    print(f"data directory: {home}")
    smoke = Smoke(home, args.cap, args.ask_above, mock=args.mock)
    code = 0
    episode: str | None = None
    try:
        smoke.start()
        smoke.setup()
        smoke.import_first_chapter()
        episode = smoke.flow()
    except Stop as stop:
        print(f"\nSTOPPED: {stop}")
        code = 1
    finally:
        try:
            if episode:
                smoke.print_script(episode)
            if smoke.series:
                smoke.print_calls()
        finally:
            smoke.stop()
    print(f"\nbackend log: {home / 'backend.log'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
