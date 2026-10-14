from __future__ import annotations

import io

import pytest
from loguru import logger

from drama_series_agent.core import secrets


def test_keyring_first_then_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert secrets.lookup("DEMO_API_KEY") == (None, "none")
    monkeypatch.setenv("DEMO_API_KEY", "env-value-123")
    assert secrets.lookup("DEMO_API_KEY") == ("env-value-123", "env")
    secrets.set_secret("DEMO_API_KEY", "  ring-value-456  ")
    assert secrets.lookup("DEMO_API_KEY") == ("ring-value-456", "keyring")
    secrets.delete_secret("DEMO_API_KEY")
    secrets.delete_secret("DEMO_API_KEY")  # idempotent
    assert secrets.has_secret("DEMO_API_KEY") == "env"


def test_empty_key_rejected() -> None:
    with pytest.raises(ValueError):
        secrets.set_secret("DEMO_API_KEY", "   ")


def test_redact_patterns_and_known_values() -> None:
    secrets.set_secret("DEMO_API_KEY", "plain-secret-value")
    text = (
        "Authorization: Bearer abc.def.ghi api_key=xyz123 "
        '{"api_key": "q-w-e"} sk-ABCDEFGHIJKLMNOP and plain-secret-value'
    )
    out = secrets.redact(text)
    for leaked in ("abc.def.ghi", "xyz123", "q-w-e", "ABCDEFGHIJKLMNOP", "plain-secret-value"):
        assert leaked not in out
    assert "Authorization: Bearer ***" in out


def test_log_redaction_patches_loguru() -> None:
    secrets.install_log_redaction()
    sink = io.StringIO()
    handler = logger.add(sink, format="{message}")
    try:
        logger.info("calling with Authorization: Bearer sk-livekey1234567890")
    finally:
        logger.remove(handler)
    assert "sk-livekey1234567890" not in sink.getvalue()
    assert "***" in sink.getvalue()


def test_dotenv_fallback(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    env_file = Path(str(tmp_path)) / "x.env"
    env_file.write_text('# comment\nDOTENV_KEY="from-dotenv-file"\n', encoding="utf-8")
    monkeypatch.setenv("DRAMA_ENV_FILE", str(env_file))
    assert secrets.lookup("DOTENV_KEY") == ("from-dotenv-file", "env")
