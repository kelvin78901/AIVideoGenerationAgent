"""API errors carry a code + params; the front end translates them (SPEC 16.3)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, **params: Any) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "params": params})
        self.code = code
