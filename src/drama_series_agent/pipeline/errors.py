"""Errors raised by pipeline services. The API turns them into ``{detail: {code, params}}``."""

from __future__ import annotations

from typing import Any


class PipelineError(Exception):
    def __init__(self, status: int, code: str, **params: Any) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.params = params
