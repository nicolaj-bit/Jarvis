"""Jarvis' værktøjer i fase 1.

Fem værktøjer: læs fil, skriv fil, list mappe, søg i filer, åbn fil/program.

Sikkerhedsregler, der håndhæves her og ikke overlades til modellen:
- Alle stier skal ligge inden for `allowed_dirs`. Stier opløses først
  (inkl. symbolske links og junctions), så man ikke kan snyde sig ud med
  `..` eller et link.
- Overskrivning af en eksisterende fil kræver brugerens bekræftelse.
- Programmer kan kun startes, hvis de står i `[programs]` i config.toml.
  Eksekverbare filer i de tilladte mapper åbnes aldrig.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .audit import audit

ConfirmFn = Callable[[str], bool]

MAX_LIST_ENTRIES = 300
MAX_SEARCH_HITS = 50
MAX_READ_CHARS = 60_000

# Filtyper der kører kode, når de "åbnes". De startes aldrig via open_path.
EXECUTABLE_SUFFIXES = {
    ".exe", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".vbs", ".vbe", ".js",
    ".jse", ".wsf", ".wsh", ".msi", ".msp", ".scr", ".pif", ".lnk", ".reg",
    ".hta", ".cpl", ".jar", ".url", ".appref-ms", ".py", ".pyw",
}


class ToolError(Exception):
    """Fejl der sendes tilbage til modellen som et fejlresultat."""


TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "read_file",
        "description": (
            "Læs indholdet af en tekstfil. Stien skal ligge i en af de "
            "tilladte mapper. Relative stier regnes fra den første tilladte mappe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Sti til filen."}},
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "write_file",
        "description": (
            "Skriv tekst til en fil i en tilladt mappe. Indholdet skal være på "
            "dansk. Findes filen i forvejen, bliver brugeren spurgt, før den "
            "overskrives. Mangler mapper, oprettes de."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Sti til filen."},
                "content": {"type": "string", "description": "Hele filens nye indhold, på dansk."},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "list_directory",
        "description": "List filer og undermapper i en tilladt mappe.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Mappen. Tom streng = den første tilladte mappe.",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "search_files",
        "description": (
            "Søg efter tekst (uden forskel på store og små bogstaver) i filer "
            "under en tilladt mappe. Returnerer filnavn, linjenummer og linjen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Teksten der søges efter."},
                "path": {
                    "type": "string",
                    "description": "Mappe at søge i. Tom streng = alle tilladte mapper.",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Filnavnsmønster, f.eks. '*.txt'. Tom streng = alle filer.",
                },
            },
            "required": ["query", "path", "file_pattern"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "open_path",
        "description": (
            "Åbn en fil i dens standardprogram (filen skal ligge i en tilladt "
            "mappe), eller start et program fra listen over tilladte programmer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Sti til en fil, eller navnet på et tilladt program.",
                }
            },
            "required": ["target"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


@dataclass
class Sandbox:
    """Afgør om en sti ligger inden for de tilladte mapper."""

    roots: list[Path]

    def __post_init__(self) -> None:
        self.roots = [Path(r).expanduser().resolve() for r in self.roots]

    def resolve(self, raw: str) -> Path:
        if not self.roots:
            raise ToolError("Ingen tilladte mapper er sat op i config.toml.")
        raw = (raw or "").strip().strip('"')
        candidate = Path(raw).expanduser() if raw else self.roots[0]
        if not candidate.is_absolute():
            candidate = self.roots[0] / candidate
        resolved = candidate.resolve()
        if not self.contains(resolved):
            raise ToolError(
                f"Afvist: {resolved} ligger uden for de tilladte mapper."
            )
        return resolved

    def contains(self, resolved: Path) -> bool:
        target = _norm(resolved)
        for root in self.roots:
            base = _norm(root)
            try:
                if os.path.commonpath([base, target]) == base:
                    return True
            except ValueError:  # forskellige drev på Windows
                continue
        return False


class Toolbox:
    def __init__(
        self,
        allowed_dirs: list[Path],
        programs: dict[str, str],
        confirm: ConfirmFn,
        max_file_kb: int = 512,
    ) -> None:
        self.sandbox = Sandbox(list(allowed_dirs))
        self.programs = {k.lower(): v for k, v in programs.items()}
        self.confirm = confirm
        self.max_bytes = max_file_kb * 1024

    @property
    def definitions(self) -> list[dict]:
        return TOOL_DEFINITIONS

    def run(self, name: str, args: dict) -> tuple[str, bool]:
        """Kør et værktøj. Returnerer (resultat, er_fejl)."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            audit("TOOL_UNKNOWN", name=name)
            return f"Ukendt værktøj: {name}", True
        audit("TOOL_CALL", name=name, args=_summarize_args(args))
        try:
            result = handler(**args)
        except ToolError as exc:
            audit("TOOL_REFUSED", name=name, reason=str(exc))
            return str(exc), True
        except TypeError as exc:
            audit("TOOL_BAD_INPUT", name=name, error=str(exc))
            return f"Forkerte argumenter: {exc}", True
        except OSError as exc:
            audit("TOOL_ERROR", name=name, error=str(exc))
            return f"Fejl: {exc}", True
        audit("TOOL_OK", name=name, result=result[:300])
        return result, False

    # --- værktøjer -------------------------------------------------------

    def _tool_read_file(self, path: str) -> str:
        file = self.sandbox.resolve(path)
        if not file.is_file():
            raise ToolError(f"Filen findes ikke: {file}")
        if file.stat().st_size > self.max_bytes:
            raise ToolError(
                f"Filen er større end {self.max_bytes // 1024} kB og læses ikke."
            )
        text = file.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_READ_CHARS:
            text = text[:MAX_READ_CHARS] + "\n[... afkortet]"
        return text

    def _tool_write_file(self, path: str, content: str) -> str:
        file = self.sandbox.resolve(path)
        if file.is_dir():
            raise ToolError(f"{file} er en mappe, ikke en fil.")
        if file.exists():
            # Talt spor: engelsk. Filnavnet gengives uændret.
            question = f"The file {file.name} already exists. Should I overwrite it?"
            if not self.confirm(question):
                raise ToolError(
                    "Brugeren sagde ikke ja. Filen blev IKKE overskrevet."
                )
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
        return f"Skrev {len(content)} tegn til {file}"

    def _tool_list_directory(self, path: str) -> str:
        folder = self.sandbox.resolve(path)
        if not folder.is_dir():
            raise ToolError(f"Mappen findes ikke: {folder}")
        entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = []
        for entry in entries[:MAX_LIST_ENTRIES]:
            if entry.is_dir():
                lines.append(f"[mappe] {entry.name}")
            else:
                lines.append(f"{entry.name}  ({entry.stat().st_size} bytes)")
        if len(entries) > MAX_LIST_ENTRIES:
            lines.append(f"... og {len(entries) - MAX_LIST_ENTRIES} mere")
        return f"{folder}\n" + ("\n".join(lines) if lines else "(tom mappe)")

    def _tool_search_files(self, query: str, path: str = "", file_pattern: str = "") -> str:
        if not query:
            raise ToolError("Søgeteksten er tom.")
        roots = [self.sandbox.resolve(path)] if path else list(self.sandbox.roots)
        needle = query.lower()
        hits: list[str] = []
        for root in roots:
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for name in filenames:
                    if file_pattern and not fnmatch.fnmatch(name.lower(), file_pattern.lower()):
                        continue
                    file = Path(dirpath, name)
                    try:
                        real = file.resolve()
                        if not self.sandbox.contains(real) or real.stat().st_size > self.max_bytes:
                            continue
                        with open(real, encoding="utf-8", errors="strict") as fh:
                            for lineno, line in enumerate(fh, 1):
                                if needle in line.lower():
                                    hits.append(f"{real}:{lineno}: {line.strip()[:200]}")
                                    if len(hits) >= MAX_SEARCH_HITS:
                                        return "\n".join(hits) + "\n[... flere resultater udeladt]"
                    except (UnicodeDecodeError, OSError):
                        continue  # binære eller utilgængelige filer springes over
        return "\n".join(hits) if hits else f"Ingen filer indeholder '{query}'."

    def _tool_open_path(self, target: str) -> str:
        key = (target or "").strip().lower()
        if key in self.programs:
            command = self.programs[key]
            _launch_program(command)
            return f"Startede {target} ({command})"
        file = self.sandbox.resolve(target)
        if not file.exists():
            known = ", ".join(sorted(self.programs)) or "ingen"
            raise ToolError(
                f"Hverken en fil i de tilladte mapper eller et tilladt program. "
                f"Tilladte programmer: {known}."
            )
        if file.is_file() and file.suffix.lower() in EXECUTABLE_SUFFIXES:
            raise ToolError(
                "Afvist: eksekverbare filer åbnes ikke. Programmer skal stå i "
                "[programs] i config.toml."
            )
        _open_with_default_app(file)
        return f"Åbnede {file}"


def _launch_program(command: str) -> None:
    if sys.platform == "win32":
        subprocess.Popen(command, shell=False)  # noqa: S603 - kommandoen kommer fra config
    else:
        subprocess.Popen(command.split())


def _open_with_default_app(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _summarize_args(args: dict) -> dict:
    """Logbogen får ikke hele filindholdet, kun længden."""
    out = {}
    for key, value in args.items():
        if key == "content" and isinstance(value, str):
            out[key] = f"<{len(value)} tegn>"
        else:
            out[key] = value
    return out
