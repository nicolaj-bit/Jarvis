"""Lokal oplæsning med Windows' indbyggede stemmer (SAPI5 via pyttsx3).

Kræver ingen konto. Jarvis taler engelsk, så standarden er en engelsk
stemme (Microsoft Zira). Stemmen vælges med `voice_id` i config.toml.
Mangler engelske stemmer: Indstillinger > Tid og sprog > Tale > Tilføj
stemmer > English (United States).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .base import TextToSpeech

log = logging.getLogger(__name__)


@dataclass
class VoiceInfo:
    id: str
    name: str
    languages: str


def _describe(voice) -> VoiceInfo:
    langs = " ".join(
        lang.decode(errors="ignore") if isinstance(lang, bytes) else str(lang)
        for lang in (getattr(voice, "languages", None) or [])
    )
    return VoiceInfo(id=str(voice.id), name=str(voice.name), languages=langs)


def _is_english(voice: VoiceInfo) -> bool:
    haystack = f"{voice.id} {voice.name} {voice.languages}".lower()
    return any(tag in haystack for tag in ("en-us", "en_us", "en-gb", "en_gb", "english", "409", "809"))


def choose_voice(voices: list[VoiceInfo], wanted_id: str) -> VoiceInfo | None:
    """Stemmen med det ønskede id — ellers den første engelske stemme."""
    wanted = wanted_id.strip().lower()
    if wanted:
        for voice in voices:
            if voice.id.lower() == wanted:
                return voice
        for voice in voices:
            if wanted in voice.id.lower() or wanted in voice.name.lower():
                return voice
    return next((v for v in voices if _is_english(v)), None)


def list_voices() -> list[VoiceInfo]:
    import pyttsx3

    engine = pyttsx3.init()
    try:
        return [_describe(v) for v in engine.getProperty("voices")]
    finally:
        engine.stop()


class LocalTTS(TextToSpeech):
    name = "local"

    def __init__(self, voice_id: str = "TTS_MS_EN-US_ZIRA_11.0", rate: int = 185) -> None:
        import pyttsx3

        self._pyttsx3 = pyttsx3
        self.rate = rate
        voice = choose_voice(list_voices(), voice_id)
        if voice is None:
            log.warning(
                "Fandt hverken stemmen %r eller en anden engelsk stemme. Bruger "
                "Windows' standardstemme. Installér en engelsk stemme under "
                "Indstillinger > Tid og sprog > Tale.",
                voice_id,
            )
            self.voice_id = None
        else:
            if voice_id.lower() not in voice.id.lower() and voice_id.lower() not in voice.name.lower():
                log.warning("Stemmen %r findes ikke. Bruger %s i stedet.", voice_id, voice.name)
            log.info("Bruger stemmen %s", voice.name)
            self.voice_id = voice.id

    def speak(self, text: str) -> None:
        if not text:
            return
        # En ny motor pr. oplæsning: pyttsx3 hænger ellers ofte på Windows,
        # når runAndWait kaldes flere gange fra en baggrundstråd.
        engine = self._pyttsx3.init()
        try:
            if self.voice_id:
                engine.setProperty("voice", self.voice_id)
            engine.setProperty("rate", self.rate)
            engine.say(text)
            engine.runAndWait()
        finally:
            engine.stop()
