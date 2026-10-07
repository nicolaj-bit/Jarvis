"""Tryk-for-tale: global genvejstast, der optager, mens den holdes nede."""

from __future__ import annotations

from typing import Callable

MODIFIER_ALIASES = {
    "ctrl": "ctrl", "control": "ctrl", "ctl": "ctrl",
    "alt": "alt", "altgr": "alt",
    "shift": "shift",
    "win": "cmd", "cmd": "cmd", "super": "cmd",
}


def parse_combo(combo: str) -> tuple[frozenset[str], str]:
    """'ctrl+alt+j' -> ({'ctrl', 'alt'}, 'j')."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("Tom genvejstast")
    *mods, key = parts
    unknown = [m for m in mods if m not in MODIFIER_ALIASES]
    if unknown or key in MODIFIER_ALIASES:
        raise ValueError(f"Ugyldig genvejstast: {combo}")
    return frozenset(MODIFIER_ALIASES[m] for m in mods), key


class PushToTalk:
    """Ren tilstandsmaskine — kan testes uden tastatur.

    Tasterne gives som normaliserede navne ('ctrl', 'alt', 'shift', 'cmd'
    eller et enkelt tegn). Optagelsen starter, når hele kombinationen er
    nede, og stopper, så snart én af tasterne slippes.
    """

    def __init__(self, combo: str, on_start: Callable[[], None], on_stop: Callable[[], None]):
        self.modifiers, self.key = parse_combo(combo)
        self.on_start = on_start
        self.on_stop = on_stop
        self.pressed: set[str] = set()
        self.active = False

    def press(self, name: str | None) -> None:
        if name is None:
            return
        self.pressed.add(name)
        if not self.active and self.modifiers <= self.pressed and self.key in self.pressed:
            self.active = True
            self.on_start()

    def release(self, name: str | None) -> None:
        if name is None:
            return
        self.pressed.discard(name)
        if self.active and (name == self.key or name in self.modifiers):
            self.active = False
            self.on_stop()


def _key_name(key) -> str | None:
    """Oversæt en pynput-tast til et normaliseret navn."""
    from pynput import keyboard

    special = {
        keyboard.Key.ctrl: "ctrl", keyboard.Key.ctrl_l: "ctrl", keyboard.Key.ctrl_r: "ctrl",
        keyboard.Key.alt: "alt", keyboard.Key.alt_l: "alt", keyboard.Key.alt_r: "alt",
        keyboard.Key.alt_gr: "alt",
        keyboard.Key.shift: "shift", keyboard.Key.shift_l: "shift", keyboard.Key.shift_r: "shift",
        keyboard.Key.cmd: "cmd", keyboard.Key.cmd_l: "cmd", keyboard.Key.cmd_r: "cmd",
    }
    if key in special:
        return special[key]
    if isinstance(key, keyboard.KeyCode):
        # Med Ctrl nede giver Windows et kontroltegn i stedet for bogstavet,
        # så vi bruger den virtuelle tastkode, når den findes.
        vk = getattr(key, "vk", None)
        if vk is not None and (0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39):
            return chr(vk).lower()
        if key.char:
            return key.char.lower()
    return None


class HotkeyListener:
    """Lytter globalt efter genvejstasten i en baggrundstråd (pynput)."""

    def __init__(self, combo: str, on_start: Callable[[], None], on_stop: Callable[[], None]):
        self.machine = PushToTalk(combo, on_start, on_stop)
        self._listener = None

    def start(self) -> None:
        from pynput import keyboard

        self._listener = keyboard.Listener(
            on_press=lambda k: self.machine.press(_key_name(k)),
            on_release=lambda k: self.machine.release(_key_name(k)),
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
