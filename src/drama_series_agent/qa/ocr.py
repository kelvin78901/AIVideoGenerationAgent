"""OCR of on-screen text (SPEC 5 ``qa/ocr.py``; M3 画面文字).

Every candidate of an on-screen text asset is read back and compared with what it must say:

- **模型直接出字** (``method: model``): character for character, punctuation included, after
  NFKC on both sides (full-width digits and colons read the same as half-width ones) and
  without whitespace (OCR splits lines and words as it likes). The punctuation ending the text
  may go unread (Kelvin 2026-10-21: RapidOCR missed a final 。 that GPT Image 2 had drawn).
- **后期贴字** (``composite``): the picture is a base for the text to go on in post, so OCR must
  read nothing on it.

OCR is the component ``ocr``, a call through the router like any other (hard rule 1): the local
RapidOCR on the CPU, free, with no API fallback. Where it is not installed or fails, a candidate
is 「未检查」 (``ocr_ok: None``), which never blocks locking.
"""

from __future__ import annotations

import unicodedata
from dataclasses import replace
from typing import Any, Literal

from loguru import logger

from drama_series_agent.core.storage import BlobStore
from drama_series_agent.modelhub.adapters.base import CallContext, ModelError, ModelRequest
from drama_series_agent.modelhub.router import Router

OCR_COMPONENT = "ocr"
# ``missing``: characters or punctuation left out; ``wrong``: some read as others;
# ``has_text``: a base for compositing shows text.
OcrIssue = Literal["missing", "wrong", "has_text"]


def normalize(text: str) -> str:
    """NFKC, then every kind of whitespace taken out."""
    return "".join(unicodedata.normalize("NFKC", text).split())


def check(exact: str, read: str | None, method: str) -> dict[str, Any]:
    """A candidate's OCR entry (``payload.candidates[i]``): ``ocr`` what was read (None: not
    checked), ``ocr_ok`` and ``ocr_issue``."""
    if read is None:
        return {"ocr": None, "ocr_ok": None, "ocr_issue": None}
    got = normalize(read)
    issue: OcrIssue | None
    if method == "composite":
        issue = "has_text" if got else None
    else:
        want = normalize(exact)
        issue = None if _matches(got, want) else "missing" if _left_out(got, want) else "wrong"
    return {"ocr": read, "ocr_ok": issue is None, "ocr_issue": issue}


def _matches(got: str, want: str) -> bool:
    """``got`` is ``want``, or ``want`` without the punctuation it ends with."""
    if got == want:
        return True
    end = len(want)
    while end and unicodedata.category(want[end - 1]).startswith("P"):
        end -= 1
    return 0 < end < len(want) and got == want[:end]


def _left_out(got: str, want: str) -> bool:
    """``got`` is ``want`` with some characters left out (none read differently)."""
    if len(got) >= len(want):
        return False
    rest = iter(want)
    return all(ch in rest for ch in got)


async def read(router: Router, store: BlobStore, sha256: str, ctx: CallContext) -> str | None:
    """What OCR reads on a stored picture; None where this machine has no OCR (「未检查」)."""
    req = ModelRequest(
        kind="ocr",
        params={"image": sha256, "path": str(store.path_for(sha256))},
        meta={"component": OCR_COMPONENT, "task": "read"},
    )
    try:
        routed = await router.call(OCR_COMPONENT, req, replace(ctx, component_id=OCR_COMPONENT))
    except ModelError as exc:
        logger.info("OCR of {} not done: {}", sha256[:12], exc.code)
        return None
    return routed.text or ""
