"""WhisperX large-v3 wrapper with VAD — anti-hallucination transcription."""

from __future__ import annotations

from pipeline.runtime import detect_device


def run_whisperx(vocals_path: str, lang_code: str) -> str:
    import whisperx
    device = detect_device()
    compute = "float16" if device == "cuda" else "int8"
    model = whisperx.load_model(
        "large-v3", device, compute_type=compute,
        language=lang_code if lang_code != "auto" else None,
    )
    audio = whisperx.load_audio(vocals_path)
    result = model.transcribe(audio, batch_size=16)
    try:
        lc = result.get("language", lang_code)
        am, meta = whisperx.load_align_model(language_code=lc, device=device)
        result = whisperx.align(result["segments"], am, meta, audio, device)
    except Exception:
        pass
    return " ".join(s["text"].strip() for s in result["segments"])
