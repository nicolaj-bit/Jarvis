from datetime import date

import pytest

from jarvis.confirm import VoiceConfirmer, is_yes
from jarvis.hotkey import PushToTalk, parse_combo
from jarvis.memory import Memory


@pytest.mark.parametrize("answer", ["Ja", "ja.", "Ja tak!", "jep", "Ja, gør det", "gør det"])
def test_yes(answer):
    assert is_yes(answer)


@pytest.mark.parametrize("answer", ["", "nej", "Ja, nej vent", "måske", "ja hvorfor ikke",
                                    "Tak fordi du så med", "lad være"])
def test_not_yes(answer):
    assert not is_yes(answer)


def test_voice_confirmer_timeout_is_no():
    spoken = []
    confirmer = VoiceConfirmer(spoken.append, lambda timeout: None)
    assert confirmer("Skal jeg overskrive?") is False
    assert "Skal jeg overskrive?" in spoken[0]


def test_voice_confirmer_yes():
    confirmer = VoiceConfirmer(lambda s: None, lambda timeout: "Ja.")
    assert confirmer("Skal jeg?") is True


def test_parse_combo():
    assert parse_combo("Ctrl + Alt + J") == (frozenset({"ctrl", "alt"}), "j")
    with pytest.raises(ValueError):
        parse_combo("ctrl+alt")


def test_push_to_talk():
    events = []
    ptt = PushToTalk("ctrl+alt+j", lambda: events.append("start"), lambda: events.append("stop"))
    ptt.press("ctrl"); ptt.press("j")
    assert events == []
    ptt.press("alt")
    assert events == ["start"]
    ptt.press("j")  # tastaturgentagelse må ikke starte igen
    assert events == ["start"]
    ptt.release("ctrl")
    assert events == ["start", "stop"]
    ptt.release("j"); ptt.release("alt")
    assert events == ["start", "stop"]


def test_memory_roundtrip(tmp_path):
    mem = Memory(tmp_path / "db.sqlite")
    today, yesterday = date(2026, 10, 7), date(2026, 10, 6)
    mem.save_turn([{"role": "user", "content": "gammel"}], yesterday)
    turn = [
        {"role": "user", "content": "Hej"},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "abc"},
                                          {"type": "text", "text": "Hej Nicolaj"}]},
    ]
    mem.save_turn(turn, today)
    assert mem.load_day(today) == turn
    assert mem.load_day(yesterday) == [{"role": "user", "content": "gammel"}]
