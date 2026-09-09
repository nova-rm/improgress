"""Orquestación interna de un flujo: extract -> transform -> validate -> load.

El pipeline no sabe de CSV ni de PostgreSQL: recibe los componentes ya
construidos. Eso es lo que permite cambiar una fuente o un destino sin
tocar esta clase.
"""
from __future__ import annotations

from datetime import datetime

from src.config.settings import load_config
from src.extractors.base import BaseExtractor
from src.loaders.base import BaseLoader
from src.quality.quarantine import write_quarantine
from src.quality.validations import Validator
from src.transformers.base import BaseTransformer
from src.utils.db import log_carga
from src.utils.logger import get_logger

logger = get_logger(__name__)


class Pipeline:
    name: str = "pipeline"

    def __init__(
        self,
        extractor: BaseExtractor,
        transformer: BaseTransformer,
        loader: BaseLoader,
        validator: Validator | None = None,
        name: str = "pipeline",
    ) -> None:
        self.extractor = extractor
        self.transformer = transformer
        self.loader = loader
        self.validator = validator
        self.name = name

    def run(self) -> dict:
        started = datetime.now()
        logger.info("[%s] inicio", self.name)

        records = self.transformer.transform(self.extractor.extract())

        rejected = 0
        reject_summary: dict = {}
        on_reject = load_config().get("quality", {}).get("on_reject", "quarantine")
        if self.validator:
            result = self.validator.run(records)
            records = result.valid
            rejected = len(result.rejected)
            reject_summary = result.summary
            logger.info("[%s] calidad: %s", self.name, result.summary)
            if rejected and on_reject == "fail":
                raise ValueError(f"[{self.name}] {rejected} registros rechazados")
            if rejected and on_reject == "quarantine":
                write_quarantine(self.name, result.rejected)

        loaded = self.loader.load(records)
        elapsed = (datetime.now() - started).total_seconds()
        extra = getattr(self.loader, "last_stats", None) or {}

        metrics = {
            "pipeline": self.name,
            "cargados": loaded,
            "rechazados": rejected,
            "segundos": round(elapsed, 2),
            "calidad": reject_summary,
            **extra,
        }
        bits = [f"cargados={loaded}", f"rechazados={rejected}", f"segs={metrics['segundos']}"]
        for key in ("altas", "cambios", "bajas", "ausentes"):
            if key in extra:
                bits.append(f"{key}={extra[key]}")
        log_carga(self.name, "; ".join(bits))
        logger.info("[%s] fin %s", self.name, metrics)
        return metrics
