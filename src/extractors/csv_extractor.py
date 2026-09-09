"""Extractor de archivos CSV.  [TEMPLATE — completar]"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from src.extractors.base import BaseExtractor
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CSVExtractor(BaseExtractor):
    def __init__(self, path: str | Path, **options) -> None:
        super().__init__(path=str(path), **options)
        self.path = Path(path)

    def extract(self) -> Iterable[dict]:
        if not self.path.exists():
            raise FileNotFoundError(f"No existe el archivo de origen: {self.path}")
        logger.info("Leyendo %s", self.path)
        with open(self.path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if not any(str(v or "").strip() for v in row.values()):
                    continue
                yield row
