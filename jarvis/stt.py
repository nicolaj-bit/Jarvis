"""Tale til tekst med faster-whisper, lokalt."""

from __future__ import annotations

import time

import numpy as np

from .audit import audit

DEFAULT_LANGUAGE = "da"


class SpeechToText:
    def __init__(
        self,
        model: str = "large-v3-turbo",
        language: str = "da",
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 5,
    ) -> None:
        from faster_whisper import WhisperModel

        started = time.perf_counter()
        if compute_type == "auto":
            compute_type = "default"  # int8 på processor, float16 på grafikkort
        self.model = WhisperModel(model, device=device, compute_type=compute_type)
        self.model_name = model
        # Sproget sættes altid eksplicit. Uden det gætter Whisper selv og
        # falder ofte over i engelsk på korte danske sætninger.
        self.language = (language or "").strip() or DEFAULT_LANGUAGE
        self.beam_size = beam_size
        audit("STT_LOADED", model=model, seconds=round(time.perf_counter() - started, 2))

    def transcribe(self, audio: np.ndarray) -> tuple[str, float]:
        """Returnerer (tekst, sekunder brugt)."""
        started = time.perf_counter()
        segments, _info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=True,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text, time.perf_counter() - started
