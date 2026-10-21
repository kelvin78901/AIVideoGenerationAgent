"""Qwen3-TTS VoiceDesign (free local auditions): a voice from words, reading a line.

``qwen-tts`` (Qwen3TTSModel.generate_voice_design), checked against the QwenLM/Qwen3-TTS README on
2026-10-21; first run on the real machine in M3 step 13.
args: ``model`` (HF id or local folder), ``device``, ``language``, ``attn`` (optional).
"""

from __future__ import annotations

from typing import Any

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel
from worker_protocol import out_path, serve


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
    wavs, rate = state["model"].generate_voice_design(
        text=msg.get("text") or "", language=state["language"], instruct=instruct
    )
    path = out_path(msg, ".wav")
    sf.write(path, wavs[0], rate)
    return {"files": [{"path": path, "mime": "audio/wav", "duration_s": len(wavs[0]) / rate}]}


if __name__ == "__main__":
    serve({"tts": speak, "voice_design": speak}, init)
