"""Read-only real scan of this machine (M1 step 8, SPEC 12.2-1 and 6.4.1).

Runs the same detectors as ``POST /setup/scan`` with ``DRAMA_SETUP=real``, then identifies the
ComfyUI it found the way the setup page does (path, port, versions, node packs, model files).
Changes nothing: no database, no installs, nothing written unless ``--out`` is given.

    uv run --no-sync python scripts/setup_scan_real.py              # readable report (Chinese)
    uv run --no-sync python scripts/setup_scan_real.py --lang en    # in English
    uv run --no-sync python scripts/setup_scan_real.py --out scan.json   # everything, as JSON

Start ComfyUI first to also see its node classes and model files as the server lists them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from drama_series_agent.core.paths import REPO_ROOT, drama_home
from drama_series_agent.setup.comfy import identify
from drama_series_agent.setup.detectors import ScanContext, detect_item
from drama_series_agent.setup.manifest import Message, load_manifest
from drama_series_agent.setup.probe import RealProbe


def _texts(lang: str) -> dict[str, Any]:
    path = REPO_ROOT / "web" / "src" / "locales" / lang / "setup.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _render(texts: dict[str, Any], scope: str, m: Message | None) -> str:
    """``setup:<scope>.<code>`` with its params, as the page shows it."""
    if m is None:
        return "—"
    template = str(texts.get(scope, {}).get(m.code, m.code))
    return re.sub(r"\{\{(\w+)\}\}", lambda g: str(m.params.get(g.group(1), g.group(0))), template)


def _size(n: int | None) -> str:
    if n is None:
        return "?"
    value, units = float(n), ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while value >= 1024 and i < len(units) - 1:
        value, i = value / 1024, i + 1
    return f"{value:.1f} {units[i]}"


async def scan(lang: str) -> dict[str, Any]:
    texts = _texts(lang)
    probe = RealProbe()
    manifest = load_manifest()
    host = await probe.host()
    items = manifest.for_platform(host.os)
    ctx = await ScanContext.create(
        probe, items, mirrors=manifest.mirrors, envs=str(drama_home() / "envs")
    )
    rows: list[dict[str, Any]] = []
    for item in items:
        d = await detect_item(item, ctx)
        name = item.name.en if lang == "en" else item.name.zh
        rows.append(
            {
                "id": item.id,
                "name": name,
                "status": d.status,
                "found": _render(texts, "found", d.found),
                "fix": _render(texts, "fix", d.fix),
                "installable": d.installable,
                "version": d.version,
                "facts": d.facts,
            }
        )
    out: dict[str, Any] = {
        "host": {"os": host.os, "home": host.home},
        "gpu": None if ctx.gpu is None else vars(ctx.gpu),
        "items": rows,
        "counts": dict(Counter(r["status"] for r in rows)),
        "comfy": None,
    }
    inst = await ctx.comfy()
    if inst is not None:
        found = await identify(ctx.probe, ctx.host, inst, await ctx.object_info())
        out["comfy"] = {
            "scan": found.scan.model_dump(mode="json"),
            "env": found.env.model_dump(mode="json"),
        }
    return out


def print_report(r: dict[str, Any], lang: str) -> None:
    status = _texts(lang)["status"]
    print(f"== {r['host']['os']} · GPU: {r['gpu']['name'] if r['gpu'] else '—'}")
    for row in r["items"]:
        mark = "*" if row["installable"] else " "
        print(
            f"{status.get(row['status'], row['status']):<6}{mark} {row['name']:<36} "
            f"{row['found']:<34} {row['fix']}"
        )
    print("   (* = can be installed from the setup page)")
    print("== counts:", ", ".join(f"{status.get(k, k)} {v}" for k, v in r["counts"].items()))
    comfy = r["comfy"]
    if comfy is None:
        print("== ComfyUI: not found")
        return
    s, e = comfy["scan"], comfy["env"]
    manager = s["manager"]
    print(f"== ComfyUI: {s['root']} ({s['kind']}) · {s['url'] or 'not running'} · port {s['port']}")
    print(
        f"   ComfyUI {e['comfyui_version']} (commit {e['comfyui_commit'] or '?'}) · "
        f"Python {e['python']} ({s['python_path']}) · PyTorch {e['torch']}"
    )
    if manager:
        print(
            f"   ComfyUI-Manager {manager['version']} ({manager['source']}, enabled: "
            f"{manager['enabled']})"
        )
    else:
        print("   ComfyUI-Manager: not installed")
    print(f"   environment hash {s['env_hash'][:16]}…")
    print(f"== node packs ({len(e['node_packs'])})")
    for p in e["node_packs"]:
        ver = p["version"] or (p["commit"][:7] if p["commit"] else "—")
        print(f"   {p['name']:<44} {p['source']:<9} {ver:<12} {len(p['classes'])} classes")
    print(f"== model folders ({len(s['model_dirs'])})")
    for d in s["model_dirs"]:
        print(f"   {d['folder']:<20} {d['path']}")
    more = " (truncated)" if s["models_truncated"] else ""
    print(f"== model files ({len(s['models'])}{more})")
    for m in s["models"]:
        print(f"   {m['folder']:<20} {m['name']:<60} {_size(m['size_bytes'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lang", choices=["zh-CN", "en"], default="zh-CN")
    parser.add_argument("--out", type=Path, help="also write the full result as JSON here")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Chinese in the Windows console
    result = asyncio.run(scan(args.lang))
    print_report(result, args.lang)
    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"== written to {args.out}")


if __name__ == "__main__":
    main()
