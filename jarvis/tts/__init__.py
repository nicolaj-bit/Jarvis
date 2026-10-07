"""Tekst til tale som et udskifteligt lag.

Vælg motor i config.toml under [tts] engine = "local" | "elevenlabs".
Alle motorer har samme metode: speak(tekst), som blokerer til oplæsningen
er færdig.
"""

from __future__ import annotations

from .base import TextToSpeech


def create_tts(config) -> TextToSpeech:
    engine = config.tts_engine.lower()
    if engine == "local":
        from .local import LocalTTS

        return LocalTTS(voice=config.tts_local_voice, rate=config.tts_local_rate)
    if engine == "elevenlabs":
        from .elevenlabs import ElevenLabsTTS

        return ElevenLabsTTS(voice_id=config.elevenlabs_voice_id, model_id=config.elevenlabs_model_id)
    raise ValueError(f"Ukendt tts.engine: {config.tts_engine!r} (brug 'local' eller 'elevenlabs')")


__all__ = ["TextToSpeech", "create_tts"]
