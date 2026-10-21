"""Comparing what OCR read with the text a picture must show (``qa/ocr.py``), and Mock OCR."""

from __future__ import annotations

import asyncio
from pathlib import Path

from drama_series_agent.modelhub.adapters.base import CallContext, ModelRequest, ModelSpec
from drama_series_agent.modelhub.adapters.mock import (
    MOCK_TEXT_KEY,
    MockAdapter,
    MockSettings,
    gradient_png,
)
from drama_series_agent.qa.ocr import check, normalize

NOTE = "楼下便利店，等你到十二点。"


def test_normalize_is_nfkc_without_whitespace() -> None:
    assert normalize("２３：５２") == "23:52"
    # The full-width comma becomes a comma; 。 has no half-width form.
    assert normalize(" 楼下便利店，\n等你　到十二点。 ") == "楼下便利店,等你到十二点。"


def test_drawn_text_matches_character_for_character() -> None:
    assert check(NOTE, NOTE, "model") == {"ocr": NOTE, "ocr_ok": True, "ocr_issue": None}
    # OCR breaks lines and writes full-width digits as it likes.
    assert check("23:52", "２３ : ５２", "model")["ocr_ok"] is True
    # Punctuation counts.
    assert check(NOTE, NOTE[:-1], "model")["ocr_issue"] == "missing"
    assert check(NOTE, "楼下便利店等你到十二点。", "model")["ocr_issue"] == "missing"
    assert check(NOTE, NOTE.replace("点", "占"), "model")["ocr_issue"] == "wrong"
    # Shorter, and a character read as another: wrong, not just missing.
    assert check(NOTE, "楼下便利店，等你到十二占", "model")["ocr_issue"] == "wrong"
    assert check(NOTE, NOTE + "啊", "model")["ocr_issue"] == "wrong"
    assert check(NOTE, "", "model")["ocr_issue"] == "missing"


def test_a_base_for_compositing_must_be_blank() -> None:
    assert check("23:52", " \n", "composite") == {"ocr": " \n", "ocr_ok": True, "ocr_issue": None}
    has_text = {"ocr": "23", "ocr_ok": False, "ocr_issue": "has_text"}
    assert check("23:52", "23", "composite") == has_text


def test_not_checked() -> None:
    assert check(NOTE, None, "model") == {"ocr": None, "ocr_ok": None, "ocr_issue": None}


def test_mock_ocr_reads_what_the_mock_drew(tmp_path: Path) -> None:
    drawn = tmp_path / "drawn.png"
    drawn.write_bytes(gradient_png(4, 4, (0, 0, 0), texts={MOCK_TEXT_KEY: NOTE}))
    blank = tmp_path / "blank.png"
    blank.write_bytes(gradient_png(4, 4, (0, 0, 0)))
    spec = ModelSpec(key="local/rapidocr", kind="ocr", where="local", display="RapidOCR")
    settings = MockSettings()
    adapter = MockAdapter(spec, settings)

    def read(path: Path) -> str | None:
        req = ModelRequest(kind="ocr", params={"path": str(path)})
        return asyncio.run(adapter.run(req, CallContext())).text

    assert read(drawn) == NOTE
    assert read(blank) == ""
    settings.ocr_mismatch = True
    assert read(drawn) == NOTE[:-1]
