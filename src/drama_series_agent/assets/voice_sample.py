"""声音克隆的样本 (M5.5 step 19): what ``POST /assets/{id}/voice/sample`` keeps.

The upload is checked the way MiniMax checks it (``config/voice.yaml`` ``clone``: 10 s to 5 min,
at most 20 MB, WAV / MP3 / M4A) and stored twice: as uploaded (what MiniMax clones) and as a
reference (levelled, its first ``ref_max_s`` seconds: what IndexTTS reads with, and the final's
anchor). Both go into the voice product's ``settings.voice.sample``; a new sample clears the
本人授权 box (``settings.voice.consent``), which belongs to the person in the old one.
"""

from __future__ import annotations

from typing import Any

from drama_series_agent.core.config import get_config
from drama_series_agent.core.storage import BlobStore
from drama_series_agent.media.audio import AudioError, joined_sample, measured, prepare_clip
from drama_series_agent.pipeline.errors import PipelineError

MAX_SAMPLE_BYTES = 20 * 1024 * 1024


def is_sample_format(head: bytes) -> bool:
    """WAV, MP3 or M4A (what MiniMax takes), by the first bytes."""
    return (
        (head[:4] == b"RIFF" and head[8:12] == b"WAVE")
        or head[:3] == b"ID3"
        or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
        or head[4:8] == b"ftyp"
    )


async def store_sample(store: BlobStore, filename: str, data: bytes) -> dict[str, Any]:
    """The checked sample as ``settings.voice.sample``: ``{sha256, name, duration_s, ref}``,
    ``ref`` the clip a player and IndexTTS use (``{sha256, duration_s, waveform}``)."""
    if len(data) > MAX_SAMPLE_BYTES:
        raise PipelineError(413, "file_too_large", limit=MAX_SAMPLE_BYTES)
    if not is_sample_format(data[:16]):
        raise PipelineError(422, "not_audio", filename=filename[:200])
    cfg = get_config().voice.clone
    try:
        whole = await prepare_clip(data)
    except AudioError as exc:
        raise PipelineError(422, "audio_unreadable", filename=filename[:200]) from exc
    if whole.duration_s < cfg.min_s:
        raise PipelineError(422, "voice_sample_too_short", seconds=whole.duration_s, min=cfg.min_s)
    if whole.duration_s > cfg.max_s:
        raise PipelineError(422, "voice_sample_too_long", seconds=whole.duration_s, max=cfg.max_s)
    cut = joined_sample([whole.data], 0.0, cfg.ref_max_s)
    assert cut is not None  # one clip is always long enough for a floor of 0
    ref = measured(cut)  # already levelled: only cut
    return {
        "sha256": store.put_bytes(data),
        "name": filename[:200],
        "duration_s": whole.duration_s,
        "ref": {
            "sha256": store.put_bytes(ref.data),
            "duration_s": ref.duration_s,
            "waveform": ref.waveform,
        },
    }
