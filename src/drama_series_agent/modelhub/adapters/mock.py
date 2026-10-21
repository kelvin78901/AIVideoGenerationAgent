"""Deterministic mock adapters for every model kind (``DRAMA_MOCK=1``, always on in tests).

Outputs: fixed JSON / text for LLMs, soft two-colour gradient PNGs for images, sine-wave WAVs
for audio and solid-colour MP4s (FFmpeg) for video. A mock keeps the real model's key and
prices, so cost accounting in mock mode matches what the real call would have cost.

A picture asked to show text (``params["text"]``, M3 画面文字) carries it in an ``iTXt`` chunk
(``MOCK_TEXT_KEY``), so Mock OCR can read back what the "model drew".
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import random
import struct
import wave
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from drama_series_agent.modelhub.adapters.base import (
    CallContext,
    Estimate,
    Health,
    ModelError,
    ModelRequest,
    ModelResult,
    ModelSpec,
    OutputFile,
    Usage,
)
from drama_series_agent.modelhub.pricing import cost_usd

LLM_KINDS = {"llm", "llm_aux", "vlm"}
IMAGE_KINDS = {"image"}
AUDIO_KINDS = {"tts", "voice_design", "music"}
VIDEO_KINDS = {"video", "upscale", "lipsync"}

# Answers a writing request in Mock mode: JSON-able data for ``json_mode``, else text.
Responder = Callable[[ModelRequest], Any]
MOCK_TEXT_KEY = "drama:text"


@dataclass
class MockSettings:
    delay_s: float = 0.0
    fail_rate: float = 0.0
    # Keys that always fail with ``mock_failure`` (used to exercise fallback).
    fail_keys: set[str] = field(default_factory=set)
    # Keys that hang until the router's timeout fires.
    hang_keys: set[str] = field(default_factory=set)
    seed: int = 0
    # (component, task) → responder; pipeline components register theirs through the registry.
    responders: dict[tuple[str, str], Responder] = field(default_factory=dict)
    # The next N JSON answers are broken (exercises a component's retry-once path).
    bad_json: int = 0


def estimate_tokens(text: str) -> int:
    """Rough token count: ~1 token per CJK char, ~4 chars per token otherwise."""
    cjk = sum(1 for ch in text if "㐀" <= ch <= "鿿")
    return max(1, cjk + (len(text) - cjk) // 4)


def _digest(*parts: object) -> bytes:
    return hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def gradient_png(
    width: int,
    height: int,
    top: tuple[int, int, int],
    bottom: tuple[int, int, int] | None = None,
    texts: dict[str, str] | None = None,
) -> bytes:
    """A top-to-bottom gradient (solid when ``bottom`` is None); ``texts`` become UTF-8
    ``iTXt`` chunks."""
    bottom = bottom or top
    rows = []
    for y in range(height):
        f = y / max(height - 1, 1)
        rgb = bytes(round(a + (b - a) * f) for a, b in zip(top, bottom, strict=True))
        rows.append(b"\x00" + rgb * width)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    extra = b"".join(
        _png_chunk(b"iTXt", key.encode("latin-1") + b"\x00\x00\x00\x00\x00" + value.encode())
        for key, value in (texts or {}).items()
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + extra
        + _png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + _png_chunk(b"IEND", b"")
    )


def mock_picture(
    width: int, height: int, *parts: object, texts: dict[str, str] | None = None
) -> bytes:
    """The Mock picture for ``parts`` (model, prompt, seed, index …): soft colours (each channel
    96–223), a lighter tone at the bottom."""
    d = _digest(*parts)
    top = (96 + d[0] % 128, 96 + d[1] % 128, 96 + d[2] % 128)
    bottom = (min(top[0] + 32, 255), min(top[1] + 32, 255), min(top[2] + 32, 255))
    return gradient_png(width, height, top, bottom, texts)


def solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    return gradient_png(width, height, rgb)


def png_texts(data: bytes) -> dict[str, str]:
    """The ``iTXt`` chunks of a PNG (uncompressed ones, as ``gradient_png`` writes)."""
    out: dict[str, str] = {}
    pos = 8
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        tag = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        if tag == b"iTXt":
            key, _, rest = body.partition(b"\x00")
            if rest[:1] == b"\x00":  # not compressed
                _, _, rest = rest[2:].partition(b"\x00")  # language tag
                _, _, text = rest.partition(b"\x00")  # translated keyword
                out[key.decode("latin-1")] = text.decode("utf-8", errors="replace")
        if tag == b"IEND":
            break
        pos += 12 + length
    return out


def sine_wav(duration_s: float, freq_hz: float = 440.0, rate: int = 48000) -> bytes:
    frames = int(duration_s * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq_hz * i / rate)))
                for i in range(frames)
            )
        )
    return buf.getvalue()


async def solid_mp4(width: int, height: int, duration_s: float, fps: int, rgb_hex: str) -> bytes:
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with TemporaryDirectory() as tmp:
        out = Path(tmp) / "mock.mp4"
        proc = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x{rgb_hex}:s={width}x{height}:d={duration_s}:r={fps}",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(out),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise ModelError("mock_ffmpeg_failed", err.decode(errors="replace")[:300])
        return out.read_bytes()


class MockAdapter:
    def __init__(self, spec: ModelSpec, settings: MockSettings | None = None) -> None:
        self.spec = spec
        self.settings = settings or MockSettings()

    @property
    def key(self) -> str:
        return self.spec.key

    def estimate(self, req: ModelRequest) -> Estimate:
        usage = self._planned_usage(req)
        return Estimate(
            cost_usd=cost_usd(self.spec.pricing, usage, resolution=req.params.get("resolution")),
            seconds=self._delay(req),
            priced=self.spec.pricing.known,
        )

    async def health(self) -> Health:
        return Health(ok=True, detail="mock", models=[self.spec.model_id or self.spec.key])

    async def run(self, req: ModelRequest, ctx: CallContext) -> ModelResult:
        s = self.settings
        if self.key in s.hang_keys:
            await asyncio.Event().wait()
        await asyncio.sleep(self._delay(req))
        rng = random.Random(_digest(self.key, req.text(), req.seed, s.seed))
        if self.key in s.fail_keys or (s.fail_rate and rng.random() < s.fail_rate):
            raise ModelError("mock_failure", f"mock failure for {self.key}")
        kind = self.spec.kind
        if kind in LLM_KINDS or kind == "asr":
            return self._llm(req)
        if kind in IMAGE_KINDS:
            return self._image(req)
        if kind in AUDIO_KINDS:
            return self._audio(req)
        if kind in VIDEO_KINDS:
            return await self._video(req)
        return ModelResult(json={"mock": True, "kind": kind}, raw={"mock": True})

    # ------------------------------------------------------------------ helpers

    def _delay(self, req: ModelRequest) -> float:
        return float(req.params.get("mock_delay_s", self.settings.delay_s))

    def _planned_usage(self, req: ModelRequest) -> Usage:
        kind = self.spec.kind
        if kind in LLM_KINDS:
            return Usage(tokens_in=estimate_tokens(req.text()), tokens_out=req.max_tokens or 800)
        if kind in IMAGE_KINDS:
            return Usage(images=int(req.params.get("n", 1)))
        if kind in AUDIO_KINDS:
            return Usage(chars=len(req.text()))
        if kind in VIDEO_KINDS:
            return Usage(output_seconds=float(req.params.get("duration_s", 2.0)))
        return Usage()

    def _llm(self, req: ModelRequest) -> ModelResult:
        prompt = req.text()
        tag = _digest(self.key, prompt, req.seed).hex()[:8]
        meta = req.meta
        responder = self.settings.responders.get(
            (str(meta.get("component")), str(meta.get("task", "run")))
        )
        payload: Any
        if req.json_mode and self.settings.bad_json > 0:
            self.settings.bad_json -= 1
            payload, text = None, '{"mock": broken'
        elif responder is not None:
            answer = responder(req)
            payload = answer if req.json_mode else None
            text = json.dumps(answer, ensure_ascii=False) if req.json_mode else str(answer)
        elif req.json_mode:
            payload = {"mock": True, "model": self.key, "echo": prompt[:40], "tag": tag}
            text = json.dumps(payload, ensure_ascii=False)
        else:
            payload = None
            text = f"【Mock {self.key}】{prompt[:60]}（{tag}）"
        usage = Usage(tokens_in=estimate_tokens(prompt), tokens_out=estimate_tokens(text))
        return ModelResult(text=text, json=payload, usage=usage, raw={"mock": True})

    def _image(self, req: ModelRequest) -> ModelResult:
        w = int(req.params.get("width", 108))
        h = int(req.params.get("height", 192))
        n = int(req.params.get("n", 1))
        text = req.params.get("text")
        texts = {MOCK_TEXT_KEY: str(text)} if text else None
        files = [
            OutputFile(
                role="image",
                mime="image/png",
                data=mock_picture(w, h, self.key, req.text(), req.seed, i, texts=texts),
                w=w,
                h=h,
            )
            for i in range(n)
        ]
        return ModelResult(files=files, usage=Usage(images=n), raw={"mock": True})

    def _audio(self, req: ModelRequest) -> ModelResult:
        text = req.text()
        duration = float(req.params.get("duration_s", max(0.5, len(text) * 0.25)))
        freq = 220 + _digest(self.key, text)[0]
        data = sine_wav(duration, freq_hz=freq)
        return ModelResult(
            files=[OutputFile(role="audio", mime="audio/wav", data=data, duration_s=duration)],
            usage=Usage(chars=len(text), output_seconds=duration),
            raw={"mock": True},
        )

    async def _video(self, req: ModelRequest) -> ModelResult:
        w = int(req.params.get("width", 108))
        h = int(req.params.get("height", 192))
        fps = int(req.params.get("fps", 24))
        duration = float(req.params.get("duration_s", 2.0))
        colour = _digest(self.key, req.text(), req.seed).hex()[:6]
        data = await solid_mp4(w, h, duration, fps, colour)
        return ModelResult(
            files=[
                OutputFile(role="video", mime="video/mp4", data=data, w=w, h=h, duration_s=duration)
            ],
            usage=Usage(output_seconds=duration),
            raw={"mock": True},
        )
