"""Bekræftelse med stemmen: Jarvis siger, hvad den vil gøre, og du svarer ja.

Spørgsmålet stilles på engelsk (talt spor). Svaret må være dansk eller engelsk.

Alt andet end et klart ja — nej, tavshed, noget uforståeligt — er et nej.
"""

from __future__ import annotations

import re
from typing import Callable

from .audit import audit

YES_WORDS = {"ja", "jo", "jep", "javel", "jaja", "yes", "yeah", "yep", "sure"}
YES_PHRASES = ("gør det", "bare gør det", "det må du gerne", "kør på", "go ahead", "do it")
NO_WORDS = {"nej", "ikke", "nope", "no", "not", "don", "dont", "stop", "vent", "wait",
            "fortryd", "annuller", "cancel", "lad"}


def is_yes(answer: str) -> bool:
    text = re.sub(r"[^\wæøå ]+", " ", answer.lower())
    words = text.split()
    if not words or any(w in NO_WORDS for w in words):
        return False
    return words[0] in YES_WORDS or any(text.strip().startswith(p) for p in YES_PHRASES)


class VoiceConfirmer:
    """Spørger højt og venter på næste tryk-for-tale-svar."""

    def __init__(
        self,
        speak: Callable[[str], None],
        listen: Callable[[float], str | None],
        timeout: float = 30.0,
    ) -> None:
        self.speak = speak
        self.listen = listen
        self.timeout = timeout

    def __call__(self, question: str) -> bool:
        audit("CONFIRM_ASK", question=question)
        self.speak(f"{question} Hold the key and answer yes or no.")
        answer = self.listen(self.timeout)
        approved = bool(answer) and is_yes(answer)
        audit("CONFIRM_ANSWER", heard=answer, approved=approved)
        if not approved:
            self.speak("Okay, I won't.")
        return approved
