"""Indlæsning af config.toml.

Relative stier i indstillingsfilen (database, log) regnes fra projektmappen,
så Jarvis opfører sig ens, uanset hvorfra den startes.
"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config.toml"
EXAMPLE_CONFIG = PROJECT_ROOT / "config.example.toml"


@dataclass
class Config:
    push_to_talk: str = "ctrl+alt+j"

    sample_rate: int = 16000
    min_seconds: float = 0.4
    input_device: str | int | None = None

    stt_model: str = "large-v3-turbo"
    stt_language: str = "da"
    stt_device: str = "auto"
    stt_compute_type: str = "auto"
    stt_beam_size: int = 5

    brain_model: str = "claude-opus-5-5"
    brain_effort: str = "medium"
    brain_max_tokens: int = 16000
    max_tool_rounds: int = 15

    tts_engine: str = "local"
    tts_local_voice: str = "da"
    tts_local_rate: int = 185
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_multilingual_v2"

    allowed_dirs: list[Path] = field(default_factory=list)
    max_file_kb: int = 512
    programs: dict[str, str] = field(default_factory=dict)

    database: Path = PROJECT_ROOT / "data" / "jarvis.db"
    log_file: Path = PROJECT_ROOT / "logs" / "jarvis.log"


def _project_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _device(value: object) -> str | int | None:
    if value in ("", None):
        return None
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text) if text.isdigit() else text


def load_config(path: Path | None = None) -> Config:
    path = path or DEFAULT_CONFIG
    if not path.exists() and path == DEFAULT_CONFIG and EXAMPLE_CONFIG.exists():
        shutil.copyfile(EXAMPLE_CONFIG, path)
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)

    hotkey = raw.get("hotkey", {})
    audio = raw.get("audio", {})
    stt = raw.get("stt", {})
    brain = raw.get("brain", {})
    tts = raw.get("tts", {})
    tts_local = tts.get("local", {})
    tts_eleven = tts.get("elevenlabs", {})
    files = raw.get("files", {})
    memory = raw.get("memory", {})
    log = raw.get("log", {})

    d = Config()
    return Config(
        push_to_talk=hotkey.get("push_to_talk", d.push_to_talk),
        sample_rate=int(audio.get("sample_rate", d.sample_rate)),
        min_seconds=float(audio.get("min_seconds", d.min_seconds)),
        input_device=_device(audio.get("input_device")),
        stt_model=stt.get("model", d.stt_model),
        stt_language=stt.get("language", d.stt_language),
        stt_device=stt.get("device", d.stt_device),
        stt_compute_type=stt.get("compute_type", d.stt_compute_type),
        stt_beam_size=int(stt.get("beam_size", d.stt_beam_size)),
        brain_model=brain.get("model", d.brain_model),
        brain_effort=brain.get("effort", d.brain_effort),
        brain_max_tokens=int(brain.get("max_tokens", d.brain_max_tokens)),
        max_tool_rounds=int(brain.get("max_tool_rounds", d.max_tool_rounds)),
        tts_engine=tts.get("engine", d.tts_engine),
        tts_local_voice=tts_local.get("voice", d.tts_local_voice),
        tts_local_rate=int(tts_local.get("rate", d.tts_local_rate)),
        elevenlabs_voice_id=tts_eleven.get("voice_id", d.elevenlabs_voice_id),
        elevenlabs_model_id=tts_eleven.get("model_id", d.elevenlabs_model_id),
        allowed_dirs=[Path(p).expanduser() for p in files.get("allowed_dirs", [])],
        max_file_kb=int(files.get("max_file_kb", d.max_file_kb)),
        programs={str(k).lower(): str(v) for k, v in raw.get("programs", {}).items()},
        database=_project_path(memory.get("database", "data/jarvis.db")),
        log_file=_project_path(log.get("file", "logs/jarvis.log")),
    )
