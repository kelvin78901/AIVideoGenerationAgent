"""Local smoke test (M6 step 5a): the QA tools on this machine's CPU, for real, on takes an
earlier local run made (round 19 by default). Nothing is spent and nothing is generated: the
script opens a **copy** of that run's data directory with ``DRAMA_MOCK=1 DRAMA_REAL_LOCAL=1``
(local Python runtimes real, everything else Mock) and, for every take of the episode, runs the
measuring half of 自动质检 (``pipeline/qa.py:Measure``) one tool at a time, timed.

    uv run --no-sync python scripts/smoke/local_qa.py [--home <data dir>] [--episode 1]
        [--only face,asr,speaker,ocr] [--shots 1-04,1-06] [--studio http://127.0.0.1:8000]

- It does **not** go through the QA job: the job's last step is 不达标自动重跑 (``qa_policy``),
  which would start real H3 takes. Nothing is written to the copy either; jobs left queued in it
  are cancelled before the app opens it.
- The tools must be installed (环境与安装: 「自动质检运行环境」 ``rt_qa`` and 「自动质检模型」
  ``w_qa``); the envs folder is ``~/.drama-studio/envs`` and the models folder the open studio's
  install folder (its ``/setup/profile``), as in ``local_video.py``.
- 画面检查 (``vlm``) is left out: in Mock mode it would only ask the Mock VLM.

Each check prints its value, what the tool saw (``detail``) and the seconds it took, and the
whole run goes to ``docs/studio/reports/m6-qa-local/<run>.json`` for the calibration (step 5c),
with a readable summary next to it (``<run>.txt``).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from local_assets import REAL_HOME, studio_facts

ROUND19 = Path(tempfile.gettempdir()) / "drama-ep19-5Oilw8" / "home"
OUT = Path(__file__).resolve().parents[2] / "docs" / "studio" / "reports" / "m6-qa-local"
TOOLS = ("face", "lipsync", "asr", "speaker", "ocr")


def copy_home(src: Path) -> Path:
    """A throwaway copy (the app migrates the database it opens); its unfinished jobs cancelled."""
    if not (src / "studio.db").is_file():
        raise SystemExit(f"no data directory at {src}")
    dest = Path(tempfile.mkdtemp(prefix="drama-local-qa-")) / "home"
    shutil.copytree(src, dest)
    with sqlite3.connect(dest / "studio.db") as db:
        n = db.execute(
            "update job set state = 'canceled'"
            " where state in ('queued', 'running', 'waiting_confirm')"
        ).rowcount
    print(f"copied {src} → {dest} ({n} unfinished jobs cancelled)")
    return dest


def short(check: dict[str, Any]) -> str:
    if check.get("error"):
        return f"未检查（{check['error']}）"
    if check.get("na"):
        return "不适用"
    value = check.get("value")
    if value is None and check.get("match") is not None:
        return "一致" if check["match"] else f"不一致：{check.get('text')!r}"
    return f"{value}" + (f" {check['text']!r}" if check.get("text") else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--home", default=str(ROUND19), help="the data directory of a local run")
    ap.add_argument("--run", default="run19", help="the report's name")
    ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--only", default="face,asr,speaker,ocr", help=f"of {','.join(TOOLS)}")
    ap.add_argument("--shots", default="", help="only these, e.g. 1-04,1-06")
    ap.add_argument("--studio", default="http://127.0.0.1:8000", help="the studio you have open")
    args = ap.parse_args()
    only = [t for t in args.only.split(",") if t]
    if unknown := set(only) - set(TOOLS):
        raise SystemExit(f"unknown tools: {sorted(unknown)}")
    picked = {s for s in args.shots.split(",") if s}

    facts = studio_facts(args.studio.rstrip("/"))
    home = copy_home(Path(args.home))
    os.environ.update({"DRAMA_HOME": str(home), "DRAMA_MOCK": "1", "DRAMA_REAL_LOCAL": "1"})

    from fastapi.testclient import TestClient
    from sqlmodel import select

    from drama_series_agent.api.app import create_app
    from drama_series_agent.core.models_db import Episode, Product, ProductVersion, Shot
    from drama_series_agent.modelhub.adapters.base import CallContext
    from drama_series_agent.modelhub.adapters.local_python import RuntimePaths
    from drama_series_agent.pipeline.components.vid import take_asks
    from drama_series_agent.pipeline.qa import QA, VIDEO_COMPONENT, Measure, has_clip
    from drama_series_agent.pipeline.runs import item_of

    async def runtime_paths() -> RuntimePaths:
        return RuntimePaths(envs=REAL_HOME / "envs", models=facts["models"])

    print(f"envs {REAL_HOME / 'envs'} · models {facts['models']}")
    results: list[dict[str, Any]] = []
    lines: list[str] = [f"M6 local QA tools · {args.run} · {datetime.now():%Y-%m-%d %H:%M}", ""]
    headers = {"X-Drama-Studio": "1"}
    with TestClient(create_app(), base_url="http://127.0.0.1", headers=headers) as client:
        state = client.app.state.studio  # type: ignore[attr-defined]
        state.setup.runtime_paths = runtime_paths
        state.registry._adapters.clear()
        services = state.components.services

        async def takes() -> list[tuple[str, Any, Any]]:
            async with state.db.session() as s:
                ep = (await s.exec(select(Episode).where(Episode.idx == args.episode))).first()
                if ep is None:
                    raise SystemExit(f"no episode {args.episode}")
                shots = {
                    x.id: x for x in (await s.exec(select(Shot).where(Shot.episode_id == ep.id)))
                }
                rows = (
                    await s.exec(
                        select(ProductVersion, Product)
                        .join(Product, Product.id == ProductVersion.product_id)  # type: ignore[arg-type]
                        .where(Product.component_id == VIDEO_COMPONENT)
                    )
                ).all()
            out = []
            for version, product in rows:
                shot = shots.get(product.owner_id)
                if shot is None or not has_clip(version):
                    continue
                label = f"{ep.idx}-{shot.idx:02d}"
                if not picked or label in picked:
                    out.append((f"{label} T{version.n}", product, version))
            return sorted(out, key=lambda x: (x[0].split()[0], x[2].n))

        async def measure(product: Any, version: Any) -> list[tuple[str, dict[str, Any], float]]:
            comp = state.components.get(VIDEO_COMPONENT)
            async with state.db.session() as s:
                inputs = await comp.inputs(s, product)
            ctx = CallContext(
                component_id=QA,
                series_id=product.series_id,
                episode_id=inputs.episode_id,
                shot_id=product.owner_id,
                product_id=product.id,
                version_id=version.id,
            )
            m = Measure(
                services, product, version, inputs, ctx, take_asks=take_asks, item=item_of(product)
            )
            done = []
            for tool in only:
                t0 = time.perf_counter()
                check = await getattr(m, tool)()
                done.append((tool, check, round(time.perf_counter() - t0, 2)))
            return done

        portal = client.portal
        assert portal is not None
        listed = portal.call(takes)
        print(f"{len(listed)} takes · tools {', '.join(only)}")
        for name, product, version in listed:
            checks = portal.call(measure, product, version)
            row = {"take": name, "version_id": version.id, "model": version.model_key, "checks": []}
            lines.append(f"== {name} ({version.model_key})")
            for tool, check, seconds in checks:
                row["checks"].append({**check, "seconds": seconds})
                detail = json.dumps(check.get("detail") or {}, ensure_ascii=False)
                lines.append(f"  {tool:8} {short(check)} · {seconds} s · {detail[:300]}")
            print("\n".join(lines[-len(checks) - 1 :]), flush=True)
            results.append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.run}.json").write_text(
        json.dumps(
            {"run": args.run, "home": str(args.home), "takes": results},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    with open(OUT / f"{args.run}.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"→ {OUT / args.run}.json / .txt")
    shutil.rmtree(home.parent, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
