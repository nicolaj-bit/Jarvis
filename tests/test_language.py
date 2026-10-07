"""Sprogreglerne fra fase 1, punkt 11-15."""

from datetime import date

import numpy as np
import pytest

from jarvis.brain import SYSTEM_TEMPLATE, Brain
from jarvis.config import load_config
from jarvis.confirm import VoiceConfirmer, is_yes
from jarvis.memory import Memory
from jarvis.tools import TOOL_DEFINITIONS, Toolbox
from jarvis.tts.local import VoiceInfo, choose_voice


# --- 11: tale til tekst låst til dansk --------------------------------------

class FakeWhisper:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        return iter([]), None


@pytest.fixture
def fake_whisper(monkeypatch):
    import faster_whisper

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeWhisper)


@pytest.mark.parametrize("configured, expected", [("da", "da"), ("", "da"), (None, "da"), ("sv", "sv")])
def test_stt_always_passes_language(fake_whisper, configured, expected):
    from jarvis.stt import SpeechToText

    stt = SpeechToText(model="tiny", language=configured)
    stt.transcribe(np.zeros(16000, dtype=np.float32))
    assert stt.model.calls[0]["language"] == expected


def write_config(tmp_path, body):
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return load_config(path)


def test_config_language_defaults_to_danish(tmp_path):
    assert write_config(tmp_path, "").stt_language == "da"
    assert write_config(tmp_path, '[stt]\nlanguage = ""\n').stt_language == "da"
    assert write_config(tmp_path, '[stt]\nlanguage = "en"\n').stt_language == "en"


# --- 13: engelsk stemme som standard, id i indstillingsfilen ---------------

def test_config_voice_defaults_are_english(tmp_path):
    config = write_config(tmp_path, "")
    assert "EN-US" in config.tts_local_voice_id
    assert config.elevenlabs_voice_id
    config = write_config(tmp_path, '[tts.local]\nvoice_id = "DAVID"\n[tts.elevenlabs]\nvoice_id = "abc"\n')
    assert config.tts_local_voice_id == "DAVID" and config.elevenlabs_voice_id == "abc"


def test_example_config_parses(tmp_path):
    from jarvis.config import EXAMPLE_CONFIG

    config = load_config(EXAMPLE_CONFIG)
    assert config.stt_language == "da"
    assert "EN-US" in config.tts_local_voice_id


VOICES = [
    VoiceInfo(r"HKLM\...\Tokens\TTS_MS_DA-DK_HELLE_11.0", "Microsoft Helle Desktop - Danish", ""),
    VoiceInfo(r"HKLM\...\Tokens\TTS_MS_EN-US_DAVID_11.0", "Microsoft David Desktop - English (United States)", ""),
    VoiceInfo(r"HKLM\...\Tokens\TTS_MS_EN-US_ZIRA_11.0", "Microsoft Zira Desktop - English (United States)", ""),
]


def test_choose_voice_by_id():
    assert "ZIRA" in choose_voice(VOICES, "TTS_MS_EN-US_ZIRA_11.0").id
    assert "DAVID" in choose_voice(VOICES, "david").id


def test_choose_voice_falls_back_to_english_not_danish():
    assert "EN-US" in choose_voice(VOICES, "findes-ikke").id
    assert choose_voice(VOICES[:1], "findes-ikke") is None


# --- 12, 14, 15: systemprompten -------------------------------------------

def test_system_prompt_language_rules():
    prompt = SYSTEM_TEMPLATE.lower()
    assert "talt svar = engelsk" in prompt
    assert "skriftligt output = dansk" in prompt
    for kind in ("filer", "noter", "dokumenter", "opsummeringer", "commit-beskeder", "logfiler"):
        assert kind in prompt
    assert "oversæt det ikke" in prompt
    assert "navne oversættes aldrig" in prompt
    assert "aldrig en engelsk fil" in prompt


def test_system_prompt_is_sent(tmp_path):
    sent = {}

    class Client:
        class beta:
            class messages:
                @staticmethod
                def create(**kwargs):
                    sent.update(kwargs)
                    from types import SimpleNamespace
                    block = SimpleNamespace(model_dump=lambda **_: {"type": "text", "text": "Done."})
                    return SimpleNamespace(stop_reason="end_turn", content=[block], model="m")

    brain = Brain(Client, Toolbox([tmp_path], {}, lambda q: False), Memory(tmp_path / "m.db"),
                  model="claude-opus-5-5", today=lambda: date(2026, 10, 7))
    brain.ask("hej")
    assert "TALT SVAR = ENGELSK" in sent["system"]
    assert str(tmp_path.resolve()) in sent["system"]


def test_write_file_tool_asks_for_danish():
    write = next(t for t in TOOL_DEFINITIONS if t["name"] == "write_file")
    assert "dansk" in write["description"]


# --- bekræftelse: spørgsmål på engelsk, svar på dansk eller engelsk --------

@pytest.mark.parametrize("answer", ["Yes", "yes please", "go ahead", "Ja"])
def test_yes_in_both_languages(answer):
    assert is_yes(answer)


@pytest.mark.parametrize("answer", ["No", "don't", "wait", "yes, no, cancel"])
def test_no_in_english(answer):
    assert not is_yes(answer)


def test_confirm_question_is_english_and_keeps_filename(tmp_path):
    (tmp_path / "Indkøbsliste.txt").write_text("mælk", encoding="utf-8")
    asked = []
    toolbox = Toolbox([tmp_path], {}, lambda q: asked.append(q) or False)
    toolbox.run("write_file", {"path": "Indkøbsliste.txt", "content": "brød"})
    assert asked == ["The file Indkøbsliste.txt already exists. Should I overwrite it?"]


def test_voice_confirmer_speaks_english():
    spoken = []
    VoiceConfirmer(spoken.append, lambda t: "nej")("Should I?")
    assert spoken == ["Should I? Hold the key and answer yes or no.", "Okay, I won't."]
