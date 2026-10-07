"""Hjernen: Claude med værktøjer i en løkke.

Modellen kan kalde flere værktøjer efter hinanden, indtil den har et svar.
Systemprompten fastlægger sprogsporene: talte svar på engelsk, alt der
skrives ned på dansk, og navne gengives uændret.

Samtalen holdes "append-only": tidligere beskeder ændres aldrig, de sendes
tilbage præcis som de kom. Det kræver API'et, for at modellens
tankeblokke forbliver gyldige, og det gør også prompt-cachen effektiv.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable

import anthropic

from .audit import audit
from .memory import Memory
from .tools import Toolbox

FALLBACK_BETA = "server-side-fallback-2026-07-01"

WEEKDAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]

SYSTEM_TEMPLATE = """Du er Jarvis, en personlig stemmeassistent for Nicolaj. Du kører på hans Windows-PC.

# Sprogregel (fast, gælder altid)
Nicolaj taler dansk til dig. Forstå det direkte på dansk — oversæt det ikke til engelsk først.

Der er to adskilte spor, og de har hvert sit sprog:
1. TALT SVAR = ENGELSK. Den tekst, du skriver i dit svar til Nicolaj, bliver læst højt med en engelsk stemme. Den skal altid være på engelsk, også når han taler dansk til dig.
2. SKRIFTLIGT OUTPUT = DANSK. Alt, hvad du skriver ned gennem et værktøj, skal være på dansk: filer, noter, dokumenter, opsummeringer, commit-beskeder og logfiler.

Når en opgave både giver et talt svar og en fil, holder du sporene adskilt: filen skrives på dansk, og det talte svar om den er på engelsk. Aldrig en engelsk fil, og aldrig et dansk talt svar.
Eksempel: "Skriv en note om at jeg skal ringe til Peter i morgen" → write_file med indholdet "Ring til Peter i morgen." og det talte svar "Done, I've saved a note to call Peter tomorrow."

# Navne oversættes aldrig
Egennavne, filnavne, mappenavne og danske produktnavne gengives præcis som de er — i tale og på skrift. Oversæt, forkort eller omskriv dem aldrig, heller ikke midt i en engelsk sætning.
Eksempel: "I've opened Indkøbsliste.txt in the folder Opskrifter." — ikke "Shopping list.txt" eller "the recipes folder". Det samme gælder for f.eks. Club No Sleep og LALATOTO.

# Talte svar
- Kort og naturligt, som i en samtale. Typisk en til tre sætninger.
- Ingen markdown, punktopstillinger, tabeller, emojis eller kodeblokke.
- Læs ikke lange filstier eller filindhold op, medmindre du bliver bedt om det. Opsummér på engelsk.
- Nicolajs tekst kommer fra talegenkendelse og kan indeholde fejlhørte ord. Gæt fornuftigt, og spørg kort (på engelsk), hvis det er uklart.

# Værktøjer
- Du kan læse, skrive, liste og søge i filer, men kun i disse mapper:
{allowed_dirs}
- Du kan åbne filer i de mapper og starte disse programmer: {programs}.
- Overskrivning af en eksisterende fil kræver Nicolajs ja. Værktøjet spørger ham selv, så du skal ikke spørge først. Siger han nej, så fortæl det kort.
- Du kan ikke slette filer, sende beskeder eller gå på nettet. Sig det ærligt, hvis du bliver bedt om det.

I dag er {weekday} den {today}. Samtalen nedenfor er fra i dag."""


def _dump_block(block: object) -> dict:
    return block.model_dump(mode="json", by_alias=True, exclude_none=True)  # type: ignore[attr-defined]


def _text_of(content: list[dict]) -> str:
    return " ".join(b.get("text", "") for b in content if b.get("type") == "text").strip()


def clean_for_speech(text: str) -> str:
    """Fjern rester af markdown, så oplæsningen ikke siger 'stjerne stjerne'."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_#`>|]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()


class Brain:
    def __init__(
        self,
        client: anthropic.Anthropic,
        toolbox: Toolbox,
        memory: Memory,
        *,
        model: str,
        effort: str = "medium",
        max_tokens: int = 16000,
        max_tool_rounds: int = 15,
        programs: list[str] | None = None,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.client = client
        self.toolbox = toolbox
        self.memory = memory
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.max_tool_rounds = max_tool_rounds
        self.programs = programs or []
        self._today = today
        self.day = today()
        self.history: list[dict] = memory.load_day(self.day)
        audit("MEMORY_LOADED", day=self.day.isoformat(), messages=len(self.history))

    def _system(self) -> str:
        dirs = "\n".join(f"  {d}" for d in self.toolbox.sandbox.roots) or "  (ingen)"
        return SYSTEM_TEMPLATE.format(
            allowed_dirs=dirs,
            programs=", ".join(self.programs) or "ingen",
            weekday=WEEKDAYS[self.day.weekday()],
            today=self.day.strftime("%d.%m.%Y"),
        )

    def _roll_day(self) -> None:
        today = self._today()
        if today != self.day:
            # Ny dag = ny samtale. Den gamle ligger stadig i databasen.
            self.day = today
            self.history = self.memory.load_day(today)
            audit("NEW_DAY", day=today.isoformat())

    def _create(self, messages: list[dict], **extra: object):
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._system(),
            tools=self.toolbox.definitions,
            messages=messages,
            output_config={"effort": self.effort},
            cache_control={"type": "ephemeral"},
            # Afviser modellens sikkerhedsfilter en harmløs forespørgsel,
            # prøver API'et selv igen på en anden model.
            betas=[FALLBACK_BETA],
            fallbacks="default",
            **extra,
        )

    def ask(self, user_text: str) -> str:
        """Behandl én ytring og returnér teksten, der skal læses op."""
        self._roll_day()
        audit("USER", text=user_text)
        new: list[dict] = [{"role": "user", "content": user_text}]

        try:
            reply = self._run_loop(new)
        except anthropic.AuthenticationError:
            audit("API_ERROR", error="authentication")
            return "My API key isn't working. Please check ANTHROPIC_API_KEY in the .env file."
        except anthropic.RateLimitError:
            audit("API_ERROR", error="rate_limit")
            return "Anthropic is rate limiting me right now. Please try again in a moment."
        except anthropic.APIConnectionError:
            audit("API_ERROR", error="connection")
            return "I can't reach Anthropic. Are we online?"
        except anthropic.APIStatusError as exc:
            audit("API_ERROR", status=exc.status_code, error=str(exc.message))
            return "Something went wrong on Anthropic's side. The details are in the log file."

        if reply is None:
            # Afvisning: turen gemmes ikke, så historikken forbliver gyldig.
            return "Sorry, I can't help with that."

        self.memory.save_turn(new, self.day)
        self.history.extend(new)
        spoken = clean_for_speech(reply)
        audit("JARVIS", text=spoken)
        return spoken

    def _run_loop(self, new: list[dict]) -> str | None:
        rounds = 0
        while True:
            response = self._create(self.history + new)
            content = [_dump_block(b) for b in response.content]
            audit("MODEL", stop_reason=response.stop_reason, model=response.model)

            if response.stop_reason == "refusal":
                audit("REFUSAL", details=str(getattr(response, "stop_details", "")))
                return None

            if not content:
                content = [{"type": "text", "text": "I don't have an answer."}]
            new.append({"role": "assistant", "content": content})

            if response.stop_reason != "tool_use":
                return _text_of(content) or "Done."

            results = []
            for block in content:
                if block.get("type") != "tool_use":
                    continue
                output, is_error = self.toolbox.run(block["name"], block.get("input") or {})
                result = {"type": "tool_result", "tool_use_id": block["id"], "content": output}
                if is_error:
                    result["is_error"] = True
                results.append(result)

            rounds += 1
            if rounds >= self.max_tool_rounds:
                audit("TOOL_LIMIT", rounds=rounds)
                results.append({
                    "type": "text",
                    "text": "Grænsen for værktøjskald er nået. Svar Nicolaj nu på engelsk med det, du ved.",
                })
                new.append({"role": "user", "content": results})
                final = self._create(self.history + new, tool_choice={"type": "none"})
                final_content = [_dump_block(b) for b in final.content]
                if final.stop_reason == "refusal" or not final_content:
                    return None
                new.append({"role": "assistant", "content": final_content})
                return _text_of(final_content) or "I didn't manage to finish."

            new.append({"role": "user", "content": results})
