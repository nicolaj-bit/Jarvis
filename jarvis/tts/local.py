"""Lokal oplæsning med Windows' indbyggede stemmer (SAPI5 via pyttsx3).

Kræver ingen konto. Dansk kræver, at en dansk stemme er installeret i
Windows: Indstillinger > Tid og sprog > Tale > Tilføj stemmer > Dansk.
"""

from __future__ import annotations

import logging

from .base import TextToSpeech

log = logging.getLogger(__name__)


class LocalTTS(TextToSpeech):
    name = "local"

    def __init__(self, voice: str = "da", rate: int = 185) -> None:
        import pyttsx3

        self._pyttsx3 = pyttsx3
        self.voice_query = voice.lower()
        self.rate = rate
        self.voice_id = self._find_voice()

    def _find_voice(self) -> str | None:
        engine = self._pyttsx3.init()
        try:
            for voice in engine.getProperty("voices"):
                langs = " ".join(
                    lang.decode(errors="ignore") if isinstance(lang, bytes) else str(lang)
                    for lang in (getattr(voice, "languages", None) or [])
                )
                haystack = f"{voice.id} {voice.name} {langs}".lower()
                if self.voice_query in haystack or (
                    self.voice_query == "da" and ("danish" in haystack or "dansk" in haystack)
                ):
                    log.info("Bruger stemmen %s", voice.name)
                    return voice.id
        finally:
            engine.stop()
        log.warning(
            "Fandt ingen stemme der matcher %r. Bruger Windows' standardstemme. "
            "Installér en dansk stemme under Indstillinger > Tid og sprog > Tale.",
            self.voice_query,
        )
        return None

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
