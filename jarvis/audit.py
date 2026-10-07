"""Logbog: alt, hvad Jarvis hører, siger og gør, med tidsstempel."""

from __future__ import annotations

import json
import logging
from pathlib import Path

_logger = logging.getLogger("jarvis.audit")


def setup_audit_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s.%(msecs)03d  %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    _logger.handlers.clear()
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def audit(event: str, **details: object) -> None:
    """Skriv én linje: hændelse efterfulgt af detaljer som JSON."""
    if details:
        payload = json.dumps(details, ensure_ascii=False, default=str)
        _logger.info("%-18s %s", event, payload)
    else:
        _logger.info("%s", event)
