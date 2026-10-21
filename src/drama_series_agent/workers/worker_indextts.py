"""IndexTTS-2.5 (local dubbing and voice variants): a line in the voice of a sample, with the
emotion of a reference clip or described in words.

``indextts.infer_v2_5.IndexTTS2``, checked against index-tts d9e41aa on 2026-10-21; first run on
the real machine in M3 step 13. Text emotion needs ``use_qwen_emo=True``; ``infer`` needs
``lang``; the fused BigVGAN kernel stays off (``use_cuda_kernel=False``: it would compile at
start, which needs the CUDA toolkit). Its helper models are read from ``<model_dir>/hf_cache/``
(the installer put them there), so nothing is downloaded.
args: ``model_dir`` (the IndexTTS-2.5 checkpoint folder), ``cwd`` (the index-tts source, which
reads some paths relative to it), ``bf16``, ``lang`` (default ``zh``).
"""

from __future__ import annotations

import os
from typing import Any

import soundfile as sf
from indextts.infer_v2_5 import IndexTTS2
from worker_protocol import WorkerError, out_path, serve


def init(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("cwd"):
        os.chdir(args["cwd"])
    model_dir = str(args["model_dir"])
    tts = IndexTTS2(
        cfg_path=os.path.join(model_dir, "config.yaml"),
        model_dir=model_dir,
        use_bf16=bool(args.get("bf16", True)),
        use_cuda_kernel=False,
        use_qwen_emo=True,
    )
    return {"tts": tts, "lang": str(args.get("lang") or "zh")}


def speak(state: dict[str, Any], msg: dict[str, Any]) -> dict[str, Any]:
    params = msg.get("params") or {}
    speaker = params.get("speaker_path")
    if not speaker:
        raise WorkerError("speaker_missing", "IndexTTS speaks in the voice of a sample clip")
    path = out_path(msg, ".wav")
    kwargs: dict[str, Any] = {
        "spk_audio_prompt": speaker,
        "text": msg.get("text") or "",
        "output_path": path,
        "lang": state["lang"],
        "verbose": False,
    }
    if params.get("emotion_ref_path"):
        kwargs["emo_audio_prompt"] = params["emotion_ref_path"]
    elif params.get("emotion_text"):
        kwargs.update(use_emo_text=True, emo_text=params["emotion_text"])
    state["tts"].infer(**kwargs)
    duration = float(sf.info(path).duration)
    return {"files": [{"path": path, "mime": "audio/wav", "duration_s": duration}]}


if __name__ == "__main__":
    serve({"tts": speak}, init)
