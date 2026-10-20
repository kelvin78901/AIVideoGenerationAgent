"""Studio code must not reach upstream modules that call models directly (bypassing
``router.call()``): those stay reachable only through the upstream ``drama-series-render`` CLI
(the upstream ``/api/series`` routes and the ``/legacy`` UI were removed in M2)."""

from __future__ import annotations

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "src" / "drama_series_agent"

STUDIO_FILES = [
    *sorted((PKG / "core").rglob("*.py")),
    *sorted((PKG / "modelhub").rglob("*.py")),
    *sorted((PKG / "api" / "routes").rglob("*.py")),
    *(
        PKG / "api" / name
        for name in ("app.py", "security.py", "state.py", "handlers.py", "sse.py", "errors.py")
    ),
    PKG / "studio_cli.py",
]

UPSTREAM = ("agent", "drama", "intake", "adapters", "utils", "llm_presets", "cli")
# The only upstream things studio code may touch, and why:
ALLOWED = {
    ("drama_series_agent.utils.llm_client", "normalize_base_url"),  # pure URL helper, no calls
}


def _imports(path: Path) -> list[tuple[str, str | None]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(alias.name, None) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            found += [(node.module, alias.name) for alias in node.names]
    return found


def test_studio_code_does_not_import_direct_model_callers() -> None:
    offending = []
    for path in STUDIO_FILES:
        for module, name in _imports(path):
            if module == "openai" or module.startswith("openai."):
                offending.append(f"{path.name}: {module}")
                continue
            parts = module.split(".")
            if parts[0] != "drama_series_agent" or len(parts) < 2:
                continue
            is_upstream = parts[1] in UPSTREAM or module.startswith(
                ("drama_series_agent.api.routers", "drama_series_agent.api.schemas")
            )
            if is_upstream and (module, name) not in ALLOWED:
                offending.append(f"{path.relative_to(PKG)}: from {module} import {name}")
    assert offending == []


def test_file_list_is_complete() -> None:
    for path in STUDIO_FILES:
        assert path.is_file(), path
