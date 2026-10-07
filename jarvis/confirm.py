"""Bekræftelse med stemmen: Jarvis siger, hvad den vil gøre, og du svarer ja.

Alt andet end et klart ja — nej, tavshed, noget uforståeligt — er et nej.
"""

from __future__ import annotations

import re
from typing import Callable

from .audit import audit

YES_WORDS = {"ja", "jo", "jep", "javel", "jaja", "yes"}
YES_PHRASES = ("gør det", "bare gør det", "det må du gerne", "kør på")
NO_WORDS = {"nej", "ikke", "nope", "no", "stop", "vent", "fortryd", "annuller", "lad"}


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
        self.speak(f"{question} Hold tasten nede og svar ja eller nej.")
        answer = self.listen(self.timeout)
        approved = bool(answer) and is_yes(answer)
        audit("CONFIRM_ANSWER", heard=answer, approved=approved)
        if not approved:
            self.speak("Okay, jeg lader være.")
        return approved
