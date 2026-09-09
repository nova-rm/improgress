"""Inventario de fuentes CSV vs tablas en PostgreSQL."""
from __future__ import annotations

import re
from pathlib import Path

from psycopg2.extras import RealDictCursor

from src.config.settings import PROJECT_ROOT, load_config
from src.utils.db import get_connection
from src.utils.watermark import (
    list_fechas_empadronados_cargadas,
    watermark_empadronados,
)

TABLES = [
    "electoral.centros_votacion",
    "electoral.mesas_votacion",
    "electoral.resultados_elecciones",
    "electoral.empadronados",
    "electoral.carga_log",
]

_EMPADRONADOS_FILE = re.compile(r"empadronados_(\d{8})\.csv$", re.IGNORECASE)


def count_csv_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        header = next(fh, None)
        if header is None:
            return 0
        return sum(1 for line in fh if line.strip())


def _table_counts(cur) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in TABLES:
        cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
        counts[table] = int(cur.fetchone()["n"])
    return counts


def _carga_log_rows(cur) -> list[dict]:
    cur.execute(
        """
        SELECT id_log, proceso, observacion, fecha
        FROM electoral.carga_log
        ORDER BY id_log DESC
        """
    )
    return [dict(row) for row in cur.fetchall()]


def get_tablas() -> dict:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            counts = _table_counts(cur)
    return {
        "tablas": [
            {"nombre": nombre, "filas": filas} for nombre, filas in counts.items()
        ]
    }


def get_cargas() -> dict:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows = _carga_log_rows(cur)
    return {"cargas": rows, "total": len(rows)}


def list_periodos_empadronados() -> dict:
    cfg = load_config()
    emp_dir = PROJECT_ROOT / cfg["paths"]["empadronados"]
    cargadas = set(list_fechas_empadronados_cargadas())
    periodos: list[dict] = []
    if emp_dir.is_dir():
        for csv_path in sorted(emp_dir.glob("empadronados_*.csv")):
            match = _EMPADRONADOS_FILE.search(csv_path.name)
            if not match:
                continue
            raw = match.group(1)
            fecha = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
            periodos.append(
                {
                    "fecha": fecha,
                    "archivo": str(csv_path.relative_to(PROJECT_ROOT)),
                    "existe_archivo": True,
                    "filas_csv": count_csv_rows(csv_path),
                    "cargada": fecha in cargadas,
                }
            )
    return {
        "watermark": watermark_empadronados(),
        "periodos": periodos,
    }


def get_cobertura() -> dict:
    cfg = load_config()
    sources = cfg["sources"]
    paths = {name: PROJECT_ROOT / spec["path"] for name, spec in sources.items() if "path" in spec}

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            counts = _table_counts(cur)
            cargas = _carga_log_rows(cur)

    fuentes: list[dict] = []

    centros = sources["centros_votacion"]
    centros_path = paths["centros_votacion"]
    centros_db = counts["electoral.centros_votacion"]
    fuentes.append(
        {
            "id": "centros_votacion",
            "modo": centros["load_mode"],
            "archivo": centros["path"],
            "existe_archivo": centros_path.is_file(),
            "filas_csv": count_csv_rows(centros_path),
            "tabla": centros["target_table"],
            "filas_db": centros_db,
            "cargada": centros_db > 0,
        }
    )

    resultados = sources["resultados_historicos"]
    resultados_path = paths["resultados_historicos"]
    resultados_db = counts["electoral.resultados_elecciones"]
    fuentes.append(
        {
            "id": "resultados_historicos",
            "modo": resultados["load_mode"],
            "archivo": resultados["path"],
            "existe_archivo": resultados_path.is_file(),
            "filas_csv": count_csv_rows(resultados_path),
            "tabla": resultados["target_table"],
            "filas_db": resultados_db,
            "cargada": resultados_db > 0,
        }
    )

    mesas_db = counts["electoral.mesas_votacion"]
    fuentes.append(
        {
            "id": "mesas_votacion",
            "modo": "derived",
            "archivo": None,
            "existe_archivo": False,
            "filas_csv": None,
            "tabla": "electoral.mesas_votacion",
            "filas_db": mesas_db,
            "cargada": mesas_db > 0,
            "nota": "No hay CSV: las mesas se derivan de las fuentes históricas.",
        }
    )

    emp = sources["empadronados"]
    periodos = list_periodos_empadronados()
    fechas = periodos["periodos"]
    emp_db = counts["electoral.empadronados"]
    fuentes.append(
        {
            "id": "empadronados",
            "modo": emp["load_mode"],
            "archivo": emp["path_pattern"],
            "tabla": emp["target_table"],
            "filas_db": emp_db,
            "snapshot_en_db": emp_db > 0,
            "watermark": periodos["watermark"],
            "fechas": fechas,
            "pendientes": [item["fecha"] for item in fechas if not item["cargada"]],
        }
    )

    pendientes = []
    for fuente in fuentes:
        if fuente["id"] == "empadronados":
            pendientes.extend(f"empadronados:{fecha}" for fecha in fuente["pendientes"])
        elif not fuente["cargada"]:
            pendientes.append(fuente["id"])

    return {
        "fuentes": fuentes,
        "pendientes": pendientes,
        "bitacora": {"total": len(cargas)},
    }


def postgres_ok() -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True
    except Exception:
        return False
