from datetime import date
from types import SimpleNamespace

from jarvis.brain import Brain, clean_for_speech
from jarvis.memory import Memory
from jarvis.tools import Toolbox


class Block(SimpleNamespace):
    def model_dump(self, **_):
        return {k: v for k, v in vars(self).items() if v is not None}


def resp(stop, *blocks):
    return SimpleNamespace(stop_reason=stop, content=list(blocks), model="claude-opus-5-5")


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": [dict(m) for m in kwargs["messages"]]})
        return self.responses.pop(0)


def make_brain(tmp_path, responses, today=date(2026, 10, 7)):
    folder = tmp_path / "docs"
    folder.mkdir(exist_ok=True)
    (folder / "a.txt").write_text("hemmelig kode 42", encoding="utf-8")
    client = FakeClient(responses)
    memory = Memory(tmp_path / "db.sqlite")
    toolbox = Toolbox([folder], {}, lambda q: False)
    brain = Brain(client, toolbox, memory, model="claude-opus-5-5", today=lambda: today)
    return brain, client, memory


def test_multi_step_tool_loop(tmp_path):
    brain, client, memory = make_brain(tmp_path, [
        resp("tool_use", Block(type="tool_use", id="t1", name="list_directory", input={"path": ""})),
        resp("tool_use", Block(type="tool_use", id="t2", name="read_file", input={"path": "a.txt"})),
        resp("end_turn", Block(type="text", text="Koden er **42**.")),
    ])
    assert brain.ask("Hvad er koden?") == "Koden er 42."
    assert len(client.calls) == 3
    last = client.calls[2]["messages"]
    assert [m["role"] for m in last] == ["user", "assistant", "user", "assistant", "user"]
    assert "42" in last[4]["content"][0]["content"]
    assert client.calls[0]["fallbacks"] == "default"
    # Hele turen er gemt og genindlæses uændret
    assert memory.load_day(date(2026, 10, 7)) == brain.history
    assert len(brain.history) == 6


def test_history_is_append_only_across_turns(tmp_path):
    brain, client, _ = make_brain(tmp_path, [
        resp("end_turn", Block(type="text", text="Hej")),
        resp("end_turn", Block(type="text", text="Du hedder Nicolaj")),
    ])
    brain.ask("Jeg hedder Nicolaj")
    first = client.calls[0]["messages"]
    brain.ask("Hvad hedder jeg?")
    second = client.calls[1]["messages"]
    assert second[: len(first)] == first


def test_memory_survives_restart(tmp_path):
    brain, _, _ = make_brain(tmp_path, [resp("end_turn", Block(type="text", text="Noteret"))])
    brain.ask("Husk at jeg skal til tandlæge")
    brain2, client2, _ = make_brain(tmp_path, [resp("end_turn", Block(type="text", text="Tandlæge"))])
    brain2.ask("Hvad skulle jeg?")
    assert client2.calls[0]["messages"][0]["content"] == "Husk at jeg skal til tandlæge"


def test_new_day_starts_fresh(tmp_path):
    brain, _, _ = make_brain(tmp_path, [resp("end_turn", Block(type="text", text="ok"))])
    brain.ask("i går")
    brain2, client2, _ = make_brain(tmp_path, [resp("end_turn", Block(type="text", text="ok"))],
                                    today=date(2026, 10, 8))
    brain2.ask("i dag")
    assert len(client2.calls[0]["messages"]) == 1


def test_refusal_not_saved(tmp_path):
    brain, _, memory = make_brain(tmp_path, [resp("refusal")])
    assert "ikke hjælpe" in brain.ask("noget")
    assert brain.history == [] and memory.load_day(date(2026, 10, 7)) == []


def test_tool_round_limit(tmp_path):
    loop = [resp("tool_use", Block(type="tool_use", id=f"t{i}", name="list_directory", input={"path": ""}))
            for i in range(15)]
    brain, client, _ = make_brain(tmp_path, loop + [resp("end_turn", Block(type="text", text="Stoppede"))])
    assert brain.ask("bliv ved") == "Stoppede"
    assert client.calls[-1]["tool_choice"] == {"type": "none"}


def test_clean_for_speech():
    assert clean_for_speech("# Overskrift\n- **punkt** et\n- to") == "Overskrift punkt et to"
