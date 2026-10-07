import os
import sys

import pytest

from jarvis.tools import Toolbox


@pytest.fixture
def setup(tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (allowed / "noter.txt").write_text("Indkøb: mælk\nRing til Peter", encoding="utf-8")
    (outside / "hemmelig.txt").write_text("hemmeligt", encoding="utf-8")
    answers = []
    toolbox = Toolbox([allowed], {"notesblok": "notepad.exe"}, lambda q: answers.pop(0), 512)
    return toolbox, allowed, outside, answers


def test_read_inside(setup):
    toolbox, allowed, _, _ = setup
    out, err = toolbox.run("read_file", {"path": "noter.txt"})
    assert not err and "mælk" in out


def test_read_outside_refused(setup):
    toolbox, _, outside, _ = setup
    out, err = toolbox.run("read_file", {"path": str(outside / "hemmelig.txt")})
    assert err and "uden for" in out


def test_dotdot_escape_refused(setup):
    toolbox, _, _, _ = setup
    out, err = toolbox.run("read_file", {"path": "../outside/hemmelig.txt"})
    assert err and "uden for" in out


def test_prefix_trick_refused(setup, tmp_path):
    toolbox, _, _, _ = setup
    sibling = tmp_path / "allowed_evil"
    sibling.mkdir()
    (sibling / "x.txt").write_text("x")
    out, err = toolbox.run("read_file", {"path": str(sibling / "x.txt")})
    assert err


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks kræver rettigheder på Windows")
def test_symlink_escape_refused(setup):
    toolbox, allowed, outside, _ = setup
    os.symlink(outside, allowed / "link")
    out, err = toolbox.run("read_file", {"path": "link/hemmelig.txt"})
    assert err
    out, _ = toolbox.run("search_files", {"query": "hemmeligt", "path": "", "file_pattern": ""})
    assert "hemmelig.txt" not in out


def test_write_new_file_needs_no_confirm(setup):
    toolbox, allowed, _, answers = setup
    out, err = toolbox.run("write_file", {"path": "ny/fil.txt", "content": "hej"})
    assert not err
    assert (allowed / "ny" / "fil.txt").read_text(encoding="utf-8") == "hej"


def test_overwrite_declined(setup):
    toolbox, allowed, _, answers = setup
    answers.append(False)
    out, err = toolbox.run("write_file", {"path": "noter.txt", "content": "slettet"})
    assert err and "IKKE" in out
    assert "mælk" in (allowed / "noter.txt").read_text(encoding="utf-8")


def test_overwrite_confirmed(setup):
    toolbox, allowed, _, answers = setup
    answers.append(True)
    out, err = toolbox.run("write_file", {"path": "noter.txt", "content": "nyt"})
    assert not err
    assert (allowed / "noter.txt").read_text(encoding="utf-8") == "nyt"


def test_write_outside_refused(setup):
    toolbox, _, outside, _ = setup
    out, err = toolbox.run("write_file", {"path": str(outside / "x.txt"), "content": "x"})
    assert err and not (outside / "x.txt").exists()


def test_list_and_search(setup):
    toolbox, _, _, _ = setup
    out, err = toolbox.run("list_directory", {"path": ""})
    assert not err and "noter.txt" in out
    out, err = toolbox.run("search_files", {"query": "PETER", "path": "", "file_pattern": "*.txt"})
    assert not err and "noter.txt:2" in out


def test_open_executable_refused(setup):
    toolbox, allowed, _, _ = setup
    (allowed / "virus.exe").write_bytes(b"MZ")
    out, err = toolbox.run("open_path", {"target": "virus.exe"})
    assert err and "eksekverbare" in out


def test_open_unknown_program_refused(setup):
    toolbox, _, _, _ = setup
    out, err = toolbox.run("open_path", {"target": "cmd.exe"})
    assert err


def test_open_allowed_program(setup, monkeypatch):
    toolbox, _, _, _ = setup
    launched = []
    monkeypatch.setattr("jarvis.tools._launch_program", launched.append)
    out, err = toolbox.run("open_path", {"target": "Notesblok"})
    assert not err and launched == ["notepad.exe"]


def test_unknown_tool(setup):
    toolbox, _, _, _ = setup
    _, err = toolbox.run("delete_file", {"path": "noter.txt"})
    assert err
