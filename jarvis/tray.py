"""Lille ikon i proceslinjen, der viser Jarvis' tilstand."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

STATES = {
    "loading": ("Starter op …", (120, 120, 120)),
    "idle": ("Klar — hold genvejstasten nede for at tale", (40, 110, 220)),
    "recording": ("Lytter …", (220, 40, 40)),
    "thinking": ("Tænker …", (230, 170, 20)),
    "speaking": ("Taler …", (40, 170, 80)),
    "confirm": ("Venter på dit ja eller nej", (170, 60, 200)),
}


def _icon_image(color: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=color + (255,))
    draw.text((25, 22), "J", fill=(255, 255, 255, 255))
    return img


class Tray:
    def __init__(self, log_file: Path, hotkey: str, on_quit: Callable[[], None]):
        import pystray

        self._pystray = pystray
        self.log_file = log_file
        self.hotkey = hotkey
        self.on_quit = on_quit
        self.state = "loading"
        self.icon = pystray.Icon(
            "jarvis",
            _icon_image(STATES["loading"][1]),
            "Jarvis",
            menu=pystray.Menu(
                pystray.MenuItem(lambda _: STATES[self.state][0], None, enabled=False),
                pystray.MenuItem(f"Genvejstast: {hotkey}", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Åbn logfil", self._open_log),
                pystray.MenuItem("Afslut", self._quit),
            ),
        )

    def set_state(self, state: str) -> None:
        self.state = state
        label, color = STATES[state]
        self.icon.icon = _icon_image(color)
        self.icon.title = f"Jarvis — {label}"
        try:
            self.icon.update_menu()
        except Exception:  # noqa: BLE001 - menuen opdateres bare næste gang
            pass

    def _open_log(self, *_args) -> None:
        if sys.platform == "win32":
            os.startfile(self.log_file)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(self.log_file)])

    def _quit(self, *_args) -> None:
        self.on_quit()
        self.icon.stop()

    def run(self, setup: Callable[[], None]) -> None:
        """Blokerer på hovedtråden. `setup` kører i en baggrundstråd."""
        def _setup(icon):
            icon.visible = True
            setup()

        self.icon.run(setup=_setup)
