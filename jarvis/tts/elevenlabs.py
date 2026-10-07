"""Oplæsning via ElevenLabs. Kræver ELEVENLABS_API_KEY i .env."""

from __future__ import annotations

import os

import httpx
import numpy as np

from .base import TextToSpeech

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
SAMPLE_RATE = 22050


class ElevenLabsTTS(TextToSpeech):
    name = "elevenlabs"

    def __init__(self, voice_id: str, model_id: str = "eleven_multilingual_v2") -> None:
        self.api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY mangler i .env")
        if not voice_id:
            raise RuntimeError("tts.elevenlabs.voice_id mangler i config.toml")
        self.voice_id = voice_id
        self.model_id = model_id
        self._http = httpx.Client(timeout=30)

    def speak(self, text: str) -> None:
        if not text:
            return
        import sounddevice as sd

        # Rå PCM i stedet for mp3, så vi ikke skal bruge en mp3-afkoder.
        response = self._http.post(
            API_URL.format(voice_id=self.voice_id),
            params={"output_format": f"pcm_{SAMPLE_RATE}"},
            headers={"xi-api-key": self.api_key},
            json={"text": text, "model_id": self.model_id},
        )
        response.raise_for_status()
        audio = np.frombuffer(response.content, dtype="<i2").astype(np.float32) / 32768.0
        sd.play(audio, SAMPLE_RATE)
        sd.wait()
