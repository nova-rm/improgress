"""Flujo de carga única: centros, mesas derivadas y resultados históricos."""
from __future__ import annotations

from datetime import date
from typing import Iterable

from src.config.settings import PROJECT_ROOT, load_config, source_config
from src.extractors.base import BaseExtractor
from src.extractors.csv_extractor import CSVExtractor
from src.loaders.postgres_loader import FullLoader
from src.pipelines.base_pipeline import Pipeline
from src.quality.validations import (
    Validator,
    rule_in_catalog,
    rule_in_domain,
    rule_natural_key,
    rule_non_negative,
    rule_voters_le_registered,
)
from src.transformers.base import TransformerPipeline
from src.transformers.common import (
    AssignField,
    CastNumeric,
    Deduplicate,
    EnrichFromCatalog,
    FillEmpty,
    NormalizeText,
    StandardizeCategories,
    TrimStrings,
)
from src.utils.db import get_connection

CENTROS_COLUMNS = [
    "codigo_centro_votacion",
    "nombre_centro",
    "direccion",
    "codigo_departamento",
    "nombre_departamento",
    "codigo_municipio",
    "nombre_municipio",
    "zona",
    "area",
    "latitud",
    "longitud",
    "cantidad_mesas",
    "capacidad_maxima",
    "anio_vigencia",
    "fechaCarga",
]

MESAS_COLUMNS = [
    "codigo_mesa",
    "codigo_centro_votacion",
    "numero_mesa",
    "fechaCarga",
]

RESULTADOS_COLUMNS = [
    "anio_eleccion",
    "tipo_eleccion",
    "vuelta",
    "codigo_departamento",
    "nombre_departamento",
    "codigo_municipio",
    "nombre_municipio",
    "codigo_centro_votacion",
    "codigo_mesa",
    "partido",
    "candidato",
    "votos_validos",
    "votos_nulos",
    "votos_en_blanco",
    "total_empadronados_mesa",
    "total_votantes_mesa",
    "fechaCarga",
]


def _categories() -> dict:
    return load_config().get("categories", {})


def _fecha_carga() -> str:
    return date.today().isoformat()


def _centros_catalog() -> dict[str, dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT codigo_centro_votacion, nombre_departamento, nombre_municipio
                FROM electoral.centros_votacion
                """
            )
            return {
                codigo: {
                    "nombre_departamento": depto,
                    "nombre_municipio": muni,
                }
                for codigo, depto, muni in cur.fetchall()
            }


def _codigos_centro() -> set[str]:
    return set(_centros_catalog())


class DerivedMesasExtractor(BaseExtractor):
    """Las mesas no vienen en un archivo: se derivan de resultados históricos."""

    def __init__(self, path: str) -> None:
        super().__init__(path=path)
        self.path = path

    def extract(self) -> Iterable[dict]:
        seen: dict[str, dict] = {}
        for row in CSVExtractor(self.path).extract():
            mesa = (row.get("codigo_mesa") or "").strip()
            centro = (row.get("codigo_centro_votacion") or "").strip()
            if not mesa or not centro:
                continue
            numero = mesa.rsplit("-", 1)[-1] if "-" in mesa else mesa
            seen[mesa] = {
                "codigo_mesa": mesa,
                "codigo_centro_votacion": centro,
                "numero_mesa": numero,
            }
        yield from seen.values()


def build_centros_pipeline() -> Pipeline:
    src = source_config("centros_votacion")
    fecha = _fecha_carga()
    return Pipeline(
        name="centros_votacion",
        extractor=CSVExtractor(PROJECT_ROOT / src["path"]),
        transformer=TransformerPipeline(
            TrimStrings(),
            NormalizeText(
                [
                    "nombre_centro",
                    "direccion",
                    "nombre_departamento",
                    "nombre_municipio",
                ]
            ),
            StandardizeCategories(_categories()),
            CastNumeric(
                ["latitud", "longitud", "cantidad_mesas", "capacidad_maxima", "anio_vigencia"]
            ),
            Deduplicate(src["natural_key"]),
            AssignField("fechaCarga", fecha),
        ),
        validator=Validator(
            [
                ("llave_natural", rule_natural_key(src["natural_key"])),
                (
                    "capacidad_no_negativa",
                    rule_non_negative(["cantidad_mesas", "capacidad_maxima"]),
                ),
                (
                    "area_dominio",
                    rule_in_domain("area", {"urbana", "rural", "desconocido"}),
                ),
            ]
        ),
        loader=FullLoader(src["target_table"], src["natural_key"], CENTROS_COLUMNS),
    )


def build_mesas_pipeline() -> Pipeline:
    resultados = source_config("resultados_historicos")
    catalog = _codigos_centro()
    fecha = _fecha_carga()
    return Pipeline(
        name="mesas_votacion",
        extractor=DerivedMesasExtractor(str(PROJECT_ROOT / resultados["path"])),
        transformer=TransformerPipeline(
            TrimStrings(),
            Deduplicate(["codigo_mesa"]),
            AssignField("fechaCarga", fecha),
        ),
        validator=Validator(
            [
                ("llave_natural", rule_natural_key(["codigo_mesa", "codigo_centro_votacion"])),
                ("centro_en_catalogo", rule_in_catalog("codigo_centro_votacion", catalog)),
            ]
        ),
        loader=FullLoader("electoral.mesas_votacion", ["codigo_mesa"], MESAS_COLUMNS),
    )


def build_resultados_pipeline() -> Pipeline:
    src = source_config("resultados_historicos")
    catalog = _centros_catalog()
    fecha = _fecha_carga()
    return Pipeline(
        name="resultados_historicos",
        extractor=CSVExtractor(PROJECT_ROOT / src["path"]),
        transformer=TransformerPipeline(
            TrimStrings(),
            FillEmpty({"vuelta": "NA"}),
            StandardizeCategories(_categories()),
            CastNumeric(
                [
                    "anio_eleccion",
                    "votos_validos",
                    "votos_nulos",
                    "votos_en_blanco",
                    "total_empadronados_mesa",
                    "total_votantes_mesa",
                ]
            ),
            NormalizeText(["candidato"]),
            EnrichFromCatalog("codigo_centro_votacion", catalog),
            Deduplicate(src["natural_key"]),
            AssignField("fechaCarga", fecha),
        ),
        validator=Validator(
            [
                ("llave_natural", rule_natural_key(src["natural_key"])),
                (
                    "votos_no_negativos",
                    rule_non_negative(
                        ["votos_validos", "votos_nulos", "votos_en_blanco"]
                    ),
                ),
                ("votantes_vs_empadronados", rule_voters_le_registered()),
                (
                    "centro_en_catalogo",
                    rule_in_catalog("codigo_centro_votacion", set(catalog)),
                ),
                (
                    "tipo_eleccion",
                    rule_in_domain(
                        "tipo_eleccion", {"presidencial", "municipal", "legislativa"}
                    ),
                ),
            ]
        ),
        loader=FullLoader(src["target_table"], src["natural_key"], RESULTADOS_COLUMNS),
    )


def run_historico() -> list[dict]:
    return [
        build_centros_pipeline().run(),
        build_mesas_pipeline().run(),
        build_resultados_pipeline().run(),
    ]
