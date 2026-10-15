#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Modified for AI Drama Studio: serves api.app:create_app (upstream /api + studio /api/v1).
"""Run Drama Series Agent HTTP API (FastAPI)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("DRAMA_SERIES_ROOT", str(ROOT))


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()

    uvicorn.run(
        "drama_series_agent.api.app:create_app", factory=True, host=args.host, port=args.port
    )


if __name__ == "__main__":
    main()
