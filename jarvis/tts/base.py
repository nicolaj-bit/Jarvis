from __future__ import annotations

from abc import ABC, abstractmethod


class TextToSpeech(ABC):
    name = "base"

    @abstractmethod
    def speak(self, text: str) -> None:
        """Læs teksten højt. Blokerer, til oplæsningen er færdig."""
