"""Samler delene: genvejstast -> optagelse -> tale til tekst -> Claude -> oplæsning."""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time

import numpy as np
from dotenv import load_dotenv

from .audit import audit, setup_audit_log
from .config import PROJECT_ROOT, Config, load_config

log = logging.getLogger("jarvis")


def _bootstrap() -> Config:
    load_dotenv(PROJECT_ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config()
    setup_audit_log(config.log_file)
    return config


def _build_brain(config: Config, confirm):
    import anthropic

    from .brain import Brain
    from .memory import Memory
    from .tools import Toolbox

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY mangler. Kopiér .env.example til .env og indsæt nøglen.")
    if not config.allowed_dirs:
        log.warning("Ingen tilladte mapper i config.toml — filværktøjerne vil afvise alt.")
    for folder in config.allowed_dirs:
        if not folder.is_dir():
            log.warning("Tilladt mappe findes ikke: %s", folder)

    toolbox = Toolbox(config.allowed_dirs, config.programs, confirm, config.max_file_kb)
    return Brain(
        anthropic.Anthropic(),
        toolbox,
        Memory(config.database),
        model=config.brain_model,
        effort=config.brain_effort,
        max_tokens=config.brain_max_tokens,
        max_tool_rounds=config.max_tool_rounds,
        programs=sorted(config.programs),
    )


class VoiceApp:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.recordings: queue.Queue[np.ndarray] = queue.Queue()
        self.stopping = threading.Event()
        self.tray = None
        self.state = "loading"
        self._recording = False

    # --- tilstand ------------------------------------------------------

    def set_state(self, state: str) -> None:
        self.state = state
        if self.tray is not None:
            self.tray.set_state(state)

    # --- genvejstast ---------------------------------------------------

    def _on_hotkey_down(self) -> None:
        if self.state == "loading":
            return
        self._recording = True
        self._state_before_recording = self.state
        self.set_state("recording")
        audit("PTT_DOWN")
        self.recorder.start()

    def _on_hotkey_up(self) -> None:
        if not self._recording:
            return
        self._recording = False
        audio = self.recorder.stop()
        seconds = len(audio) / self.config.sample_rate
        audit("PTT_UP", seconds=round(seconds, 2))
        self.set_state(self._state_before_recording)
        if seconds >= self.config.min_seconds:
            self.recordings.put(audio)

    # --- tale ------------------------------------------------------------

    def speak(self, text: str) -> None:
        previous = self.state
        self.set_state("speaking")
        try:
            self.tts.speak(text)
        except Exception as exc:  # noqa: BLE001 - oplæsning må ikke stoppe Jarvis
            log.exception("Oplæsning fejlede")
            audit("TTS_ERROR", error=str(exc))
        finally:
            self.set_state(previous)

    def listen(self, timeout: float) -> str | None:
        """Vent på næste optagelse og returnér teksten (bruges til bekræftelse)."""
        while not self.recordings.empty():  # gamle optagelser tæller ikke som svar
            self.recordings.get_nowait()
        self.set_state("confirm")
        try:
            audio = self.recordings.get(timeout=timeout)
        except queue.Empty:
            return None
        finally:
            self.set_state("thinking")
        text, seconds = self.stt.transcribe(audio)
        audit("HEARD", text=text, stt_seconds=round(seconds, 2))
        return text

    # --- hovedløkke ------------------------------------------------------

    def _worker(self) -> None:
        while not self.stopping.is_set():
            try:
                audio = self.recordings.get(timeout=0.5)
            except queue.Empty:
                continue
            self.set_state("thinking")
            try:
                text, seconds = self.stt.transcribe(audio)
                audit("HEARD", text=text, stt_seconds=round(seconds, 2))
                log.info("Hørte (%.1fs): %s", seconds, text)
                if not text:
                    continue
                started = time.perf_counter()
                reply = self.brain.ask(text)
                log.info("Svar (%.1fs): %s", time.perf_counter() - started, reply)
                self.speak(reply)
            except Exception as exc:  # noqa: BLE001 - én fejl må ikke lukke Jarvis
                log.exception("Fejl under behandling")
                audit("ERROR", error=repr(exc))
                self.speak("Der skete en fejl. Detaljerne står i logfilen.")
            finally:
                self.set_state("idle")

    def _load(self) -> None:
        from .audio import Recorder
        from .confirm import VoiceConfirmer
        from .hotkey import HotkeyListener
        from .stt import SpeechToText
        from .tts import create_tts

        c = self.config
        self.recorder = Recorder(c.sample_rate, c.input_device)
        self.tts = create_tts(c)
        log.info("Indlæser talemodellen %s (første gang hentes den — det kan tage et par minutter) …", c.stt_model)
        self.stt = SpeechToText(c.stt_model, c.stt_language, c.stt_device, c.stt_compute_type, c.stt_beam_size)
        self.brain = _build_brain(c, VoiceConfirmer(self.speak, self.listen))
        self.hotkeys = HotkeyListener(c.push_to_talk, self._on_hotkey_down, self._on_hotkey_up)
        self.hotkeys.start()
        threading.Thread(target=self._worker, name="jarvis-worker", daemon=True).start()
        audit("STARTED", hotkey=c.push_to_talk, stt=c.stt_model, tts=self.tts.name, model=c.brain_model)
        self.set_state("idle")
        log.info("Jarvis er klar. Hold %s nede for at tale.", c.push_to_talk)

    def stop(self) -> None:
        self.stopping.set()
        if hasattr(self, "hotkeys"):
            self.hotkeys.stop()
        audit("STOPPED")

    def run(self) -> None:
        from .tray import Tray

        self.tray = Tray(self.config.log_file, self.config.push_to_talk, self.stop)

        def setup() -> None:
            try:
                self._load()
            except SystemExit as exc:
                log.error("%s", exc)
                self.tray.icon.stop()
            except Exception:
                log.exception("Jarvis kunne ikke starte")
                self.tray.icon.stop()

        self.tray.run(setup)


def run_voice() -> None:
    VoiceApp(_bootstrap()).run()


def run_console() -> None:
    """Skriv i stedet for at tale. Godt til at teste hjernen og værktøjerne."""
    config = _bootstrap()

    def confirm(question: str) -> bool:
        from .confirm import is_yes

        audit("CONFIRM_ASK", question=question)
        answer = input(f"Jarvis: {question} (ja/nej) > ")
        approved = is_yes(answer)
        audit("CONFIRM_ANSWER", heard=answer, approved=approved)
        return approved

    brain = _build_brain(config, confirm)
    audit("STARTED", mode="console", model=config.brain_model)
    print("Skriv til Jarvis. Tom linje afslutter.")
    while True:
        try:
            text = input("Du: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            break
        print(f"Jarvis: {brain.ask(text)}")
    audit("STOPPED", mode="console")


def run_stt_test(seconds: float = 5.0) -> None:
    """Optag et par sekunder og mål, hvor hurtigt talemodellen svarer."""
    from .audio import Recorder
    from .stt import SpeechToText

    config = _bootstrap()
    print(f"Indlæser {config.stt_model} …")
    started = time.perf_counter()
    stt = SpeechToText(config.stt_model, config.stt_language, config.stt_device,
                       config.stt_compute_type, config.stt_beam_size)
    print(f"Modellen er indlæst på {time.perf_counter() - started:.1f} s")

    recorder = Recorder(config.sample_rate, config.input_device)
    for round_no in (1, 2):
        input(f"\nTryk Enter og tal dansk i {seconds:.0f} sekunder (runde {round_no} af 2) …")
        recorder.start()
        time.sleep(seconds)
        audio = recorder.stop()
        text, used = stt.transcribe(audio)
        print(f"Hørte: {text!r}")
        print(f"Tale til tekst tog {used:.2f} s for {len(audio) / config.sample_rate:.1f} s lyd")
    print("\n(Runde 2 er det realistiske tal — første kørsel er altid lidt langsommere.)")


def run_tts_test() -> None:
    from .tts import create_tts

    config = _bootstrap()
    tts = create_tts(config)
    print(f"Tester oplæsning med '{tts.name}' …")
    tts.speak("Hej Nicolaj. Det her er Jarvis. Kan du høre mig tydeligt?")
