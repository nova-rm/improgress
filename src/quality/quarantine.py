"""Cuarentena de registros rechazados (archivos, sin cambiar el DDL)."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from src.config.settings import PROJECT_ROOT, load_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


def quarantine_dir() -> Path:
    cfg = load_config()
    relative = cfg.get("quality", {}).get("quarantine_dir", "data/quarantine")
    path = PROJECT_ROOT / relative
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_quarantine(pipeline: str, rejected: list[tuple[dict, str]]) -> Path | None:
    if not rejected:
        return None
    path = quarantine_dir() / f"{pipeline.replace(':', '_')}.csv"
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row, _reason in rejected:
        for key in list(row.keys()) + ["_motivo"]:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row, reason in rejected:
            writer.writerow({**row, "_motivo": reason})
    counts = Counter(reason for _, reason in rejected)
    logger.info("[%s] cuarentena %s (%s)", pipeline, path, dict(counts))
    return path
