"""Lectura paginada de tablas del esquema electoral."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal

from psycopg2.extras import RealDictCursor

from src.utils.db import ensure_empadronados_periodo_column, get_connection
from src.utils.watermark import watermark_empadronados

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TABLES = {
    "centros_votacion": {
        "qualified": "electoral.centros_votacion",
        "order": "id_centro",
        "label": "Centros de votación",
    },
    "mesas_votacion": {
        "qualified": "electoral.mesas_votacion",
        "order": "id_mesa",
        "label": "Mesas de votación",
    },
    "resultados_elecciones": {
        "qualified": "electoral.resultados_elecciones",
        "order": "id_resultado",
        "label": "Resultados de elecciones",
    },
    "empadronados": {
        "qualified": "electoral.empadronados",
        "order": "id_empadronado",
        "label": "Empadronados",
    },
    "carga_log": {
        "qualified": "electoral.carga_log",
        "order": "id_log",
        "label": "Bitácora de cargas",
    },
}


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def list_tables() -> list[dict]:
    return [
        {"id": key, "nombre": spec["qualified"], "label": spec["label"]}
        for key, spec in TABLES.items()
    ]


def _periodos_en_db(cur) -> list[str]:
    cur.execute(
        """
        SELECT DISTINCT periodo
        FROM electoral.empadronados
        WHERE periodo IS NOT NULL AND BTRIM(periodo) <> ''
        ORDER BY periodo
        """
    )
    return [row["periodo"] for row in cur.fetchall()]


def get_table_page(
    tabla: str,
    limit: int = 50,
    offset: int = 0,
    q: str = "",
    periodo: str = "",
) -> dict:
    if tabla not in TABLES:
        raise KeyError(tabla)
    spec = TABLES[tabla]
    qualified = spec["qualified"]
    order = spec["order"]
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    needle = f"%{q.strip()}%" if q and q.strip() else None
    periodo = (periodo or "").strip()
    if periodo and not _FECHA.match(periodo):
        raise ValueError("El periodo debe ir en formato YYYY-MM-DD.")
    if periodo and tabla != "empadronados":
        raise ValueError("El filtro de periodo solo aplica a empadronados.")

    if tabla == "empadronados":
        ensure_empadronados_periodo_column(watermark_empadronados())

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM {qualified} LIMIT 0")
            columns = [col.name for col in cur.description]
            if tabla == "empadronados" and "periodo" in columns:
                columns = ["id_empadronado", "periodo"] + [
                    col for col in columns if col not in {"id_empadronado", "periodo"}
                ]
            select_sql = ", ".join(columns)

            filters: list[str] = []
            params: list = []
            if periodo:
                filters.append("periodo = %s")
                params.append(periodo)
            if needle:
                filters.append(
                    "(" + " OR ".join(f"CAST({col} AS TEXT) ILIKE %s" for col in columns) + ")"
                )
                params.extend([needle] * len(columns))
            where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

            cur.execute(f"SELECT COUNT(*) AS n FROM {qualified} {where_sql}", tuple(params))
            total = int(cur.fetchone()["n"])
            cur.execute(
                f"""
                SELECT {select_sql} FROM {qualified}
                {where_sql}
                ORDER BY {order}
                LIMIT %s OFFSET %s
                """,
                tuple(params) + (limit, offset),
            )
            rows = [
                {k: _jsonable(v) for k, v in dict(row).items()} for row in cur.fetchall()
            ]
            periodos = _periodos_en_db(cur) if tabla == "empadronados" else []

    return {
        "id": tabla,
        "nombre": qualified,
        "label": spec["label"],
        "columnas": columns,
        "filas": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "periodo": periodo or None,
        "periodos": periodos,
    }
