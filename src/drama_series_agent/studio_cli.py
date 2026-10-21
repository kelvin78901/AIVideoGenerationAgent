"""`drama-studio` command line entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _cmd_dev(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "drama_series_agent.api.app:create_app",
        factory=True,
        host=DEFAULT_HOST,
        port=args.port,
        reload=args.reload,
    )
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    import asyncio

    from drama_series_agent.studio.demo import build_demo

    asyncio.run(build_demo(reset=args.reset))
    print("Demo series ready: http://127.0.0.1:5173/s/demo/e/1/novel (reload the page)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drama-studio", description="AI Drama Studio")
    sub = parser.add_subparsers(dest="command", required=True)

    dev = sub.add_parser("dev", help="Run the backend on 127.0.0.1")
    dev.add_argument("--port", type=int, default=DEFAULT_PORT)
    dev.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    dev.set_defaults(func=_cmd_dev)

    demo = sub.add_parser("demo", help="Add the demo series 《雨停之前》 (only what is missing)")
    demo.add_argument("--reset", action="store_true", help="Delete the demo series and rebuild it")
    demo.set_defaults(func=_cmd_demo)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
