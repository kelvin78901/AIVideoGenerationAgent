from __future__ import annotations

import importlib

import pytest

from drama_series_agent.studio_cli import build_parser

UPSTREAM_MODULES = [
    "drama_series_agent.cli",
    "drama_series_agent.api.routers.series",
    "drama_series_agent.adapters.r2v.runner",
    "drama_series_agent.drama.event_bus",
    "drama_series_agent.utils.llm_client",
]


@pytest.mark.parametrize("name", UPSTREAM_MODULES)
def test_upstream_modules_import(name: str) -> None:
    importlib.import_module(name)


def test_cli_parses_dev() -> None:
    args = build_parser().parse_args(["dev", "--port", "8123"])
    assert args.command == "dev"
    assert args.port == 8123
