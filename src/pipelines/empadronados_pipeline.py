"""Flujo incremental: padrón electoral (fuente viva)."""
from __future__ import annotations

import re

from src.config.settings import PROJECT_ROOT, load_config, source_config
from src.extractors.csv_extractor import CSVExtractor
from src.loaders.postgres_loader import IncrementalLoader
from src.pipelines.base_pipeline import Pipeline
from src.quality.validations import (
    Validator,
    rule_dates_parseable,
    rule_in_catalog,
    rule_in_domain,
    rule_natural_key,
)
from src.transformers.base import TransformerPipeline
from src.transformers.common import (
    AssignField,
    Deduplicate,
    ParseDates,
    StandardizeCategories,
    TrimStrings,
)
from src.utils.db import ensure_empadronados_periodo_column, get_connection
from src.utils.watermark import (
    DuplicateLoadError,
    fecha_empadronados_cargada,
    historico_cargado,
    watermark_empadronados,
)

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

EMPADRONADOS_COLUMNS = [
    "id_empadronado",
    "codigo_centro_votacion",
    "codigo_mesa",
    "rango_edad",
    "sexo",
    "codigo_departamento_residencia",
    "codigo_municipio_residencia",
    "estado_registro",
    "fecha_inscripcion",
    "fecha_ultima_actualizacion",
    "periodo",
]


def _categories() -> dict:
    return load_config().get("categories", {})


def _codigos_centro() -> set[str]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT codigo_centro_votacion FROM electoral.centros_votacion")
            return {row[0] for row in cur.fetchall() if row[0]}


def path_empadronados(fecha: str):
    compact = fecha.replace("-", "")
    pattern = source_config("empadronados")["path_pattern"]
    return PROJECT_ROOT / pattern.format(fecha=compact)


def build_empadronados_pipeline(fecha: str) -> Pipeline:
    src = source_config("empadronados")
    path = path_empadronados(fecha)
    catalog = _codigos_centro()
    return Pipeline(
        name=f"empadronados:{fecha}",
        extractor=CSVExtractor(path),
        transformer=TransformerPipeline(
            TrimStrings(),
            StandardizeCategories(_categories()),
            ParseDates(["fecha_inscripcion", "fecha_ultima_actualizacion"]),
            Deduplicate(src["natural_key"]),
            AssignField("periodo", fecha),
        ),
        validator=Validator(
            [
                ("llave_natural", rule_natural_key(src["natural_key"])),
                (
                    "estado_dominio",
                    rule_in_domain("estado_registro", {"activo", "suspendido", "fallecido"}),
                ),
                (
                    "sexo_dominio",
                    rule_in_domain("sexo", {"F", "M", "desconocido"}),
                ),
                ("fechas_parseables", rule_dates_parseable(
                    ["fecha_inscripcion", "fecha_ultima_actualizacion"]
                )),
                ("centro_en_catalogo", rule_in_catalog("codigo_centro_votacion", catalog)),
            ]
        ),
        loader=IncrementalLoader(src["target_table"], src["natural_key"], EMPADRONADOS_COLUMNS),
    )


def run_empadronados(fecha: str, overwrite: bool = False) -> dict:
    if not _FECHA.match(fecha or ""):
        raise ValueError("La fecha debe ir en formato YYYY-MM-DD.")
    path = path_empadronados(fecha)
    if not path.is_file():
        raise FileNotFoundError(f"No encontré el archivo del periodo {fecha}: {path}")
    if not historico_cargado():
        raise ValueError("Primero carga el histórico: el catálogo de centros está vacío.")

    watermark = watermark_empadronados()
    ensure_empadronados_periodo_column(default_periodo=watermark)
    if not overwrite:
        if fecha_empadronados_cargada(fecha):
            raise DuplicateLoadError(
                f"El periodo {fecha} ya fue cargado. Si continúas se sobreescribirá "
                "el padrón vigente con esa misma foto (sin duplicar ids).",
                fecha=fecha,
                watermark=watermark,
            )
        if watermark and fecha < watermark:
            raise DuplicateLoadError(
                f"El watermark actual es {watermark}. Cargar {fecha} sobreescribirá "
                "el padrón vigente con una foto anterior.",
                fecha=fecha,
                watermark=watermark,
            )

    metrics = build_empadronados_pipeline(fecha).run()
    metrics["fecha"] = fecha
    metrics["overwrite"] = overwrite
    metrics["watermark"] = fecha
    return metrics
