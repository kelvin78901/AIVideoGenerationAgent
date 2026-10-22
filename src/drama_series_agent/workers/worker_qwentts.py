"""Qwen3-TTS VoiceDesign (free local auditions): a voice from words, reading a line.

``qwen-tts`` (Qwen3TTSModel.generate_voice_design), checked against the QwenLM/Qwen3-TTS README on
2026-10-21; first run on the real machine in M3 step 13.
args: ``model`` (the local folder the installer downloaded it to: offline, transformers 4.57.3
asks the Hub about a repo id even with everything cached), ``device``, ``language``, ``attn``
(optional). Output is 24 kHz.

**Length limit**: the model sometimes never says it is done and talks on to its default limit
(8192 steps, about 11 minutes; one 9-character line once came back 78 s long). Each line gets
``max_new_tokens`` from its length (3 s + 0.8 s a character at 12 steps a second, far above
normal speech); a clip that runs into it is made again once, and twice is ``tts_runaway``.
"""

from __future__ import annotations

import sys
from typing import Any

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel
from worker_protocol import WorkerError, out_path, serve

STEPS_PER_S = 12  # the 12Hz speech tokenizer: one generation step per 1/12 s
MIN_S = 3.0
S_PER_CHAR = 0.8
TRIES = 2


def step_limit(text: str) -> int:
    return int(STEPS_PER_S * (MIN_S + S_PER_CHAR * len(text)))


def init(args: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"device_map": args.get("device", "cuda:0"), "dtype": torch.bfloat16}
    if args.get("attn"):
        kwargs["attn_implementation"] = args["attn"]
    model_id = args.get("model", "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
    model = Qwen3TTSModel.from_pretrained(model_id, **kwargs)
    return {"model": model, "language": args.get("language", "Chinese")}


def speak(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    params = msg.get("params") or {}
    instruct = str(params.get("design") or params.get("emotion_text") or "")
    if params.get("tone"):
        instruct = f"{instruct}；{params['tone']}" if instruct else str(params["tone"])
    text = msg.get("text") or ""
    limit = step_limit(text)
    for attempt in range(TRIES):
        wavs, rate = state["model"].generate_voice_design(
            text=text, language=state["language"], instruct=instruct, max_new_tokens=limit
        )
        seconds = len(wavs[0]) / rate
        if seconds < 0.95 * limit / STEPS_PER_S:
            break
        print(f"qwentts: {seconds:.1f} s reached the limit (try {attempt + 1})", file=sys.stderr)
    else:
        raise WorkerError(
            "tts_runaway", f"{len(text)} characters kept talking past {seconds:.0f} s"
        )
    path = out_path(msg, ".wav")
    sf.write(path, wavs[0], rate)
    return {"files": [{"path": path, "mime": "audio/wav", "duration_s": len(wavs[0]) / rate}]}


if __name__ == "__main__":
    serve({"tts": speak, "voice_design": speak}, init)
