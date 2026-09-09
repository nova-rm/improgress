"""Loaders de PostgreSQL."""
from __future__ import annotations

from typing import Iterable

from psycopg2.extras import execute_values

from src.loaders.base import BaseLoader
from src.utils.db import get_connection, insert_many
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FullLoader(BaseLoader):
    """Carga histórica idempotente: TRUNCATE + INSERT en una transacción.

    El modelo no tiene UNIQUE, así que no hay ON CONFLICT. Reemplazar el
    contenido de la tabla garantiza que reejecutar no duplica filas.
    """

    def __init__(self, table: str, natural_key: list[str], columns: list[str]) -> None:
        super().__init__(table, natural_key)
        self.columns = columns

    def load(self, records: Iterable[dict]) -> int:
        rows = [
            tuple(record.get(col, "") if record.get(col, "") is not None else "" for col in self.columns)
            for record in records
        ]
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"TRUNCATE TABLE {self.table} RESTART IDENTITY")
            inserted = insert_many(conn, self.table, self.columns, rows)
        logger.info("FullLoader %s: %s filas", self.table, inserted)
        return inserted


BAJA_ESTADOS = {"suspendido", "fallecido"}


def classify_empadronados(
    incoming: list[dict], existing: dict[str, dict]
) -> dict[str, int]:
    """Clasifica altas, traslados, bajas por estado y ausentes respecto al snapshot actual."""
    incoming_ids = {str(row.get("id_empadronado") or "") for row in incoming}
    incoming_ids.discard("")
    altas = cambios = bajas = 0
    for row in incoming:
        ident = str(row.get("id_empadronado") or "")
        prev = existing.get(ident)
        nuevo_estado = str(row.get("estado_registro") or "").strip()
        if prev is None:
            altas += 1
            continue
        if (prev.get("codigo_centro_votacion"), prev.get("codigo_mesa")) != (
            row.get("codigo_centro_votacion"),
            row.get("codigo_mesa"),
        ):
            cambios += 1
        if nuevo_estado in BAJA_ESTADOS and prev.get("estado_registro") not in BAJA_ESTADOS:
            bajas += 1
    ausentes = len(set(existing) - incoming_ids)
    return {
        "altas": altas,
        "cambios": cambios,
        "bajas": bajas,
        "ausentes": ausentes,
    }


class IncrementalLoader(BaseLoader):
    """Upsert del padrón por id_empadronado. No duplica gracias a la PK.

    Detecta altas/cambios/bajas y borra ausentes (ids que ya no vienen en la foto del día).
    Reprocesar la misma fecha con overwrite vuelve a aplicar la misma foto.
    """

    def __init__(self, table: str, natural_key: list[str], columns: list[str]) -> None:
        super().__init__(table, natural_key)
        self.columns = columns
        self.last_stats: dict = {}

    def load(self, records: Iterable[dict]) -> int:
        rows_dict = list(records)
        incoming_ids = [str(r.get("id_empadronado") or "") for r in rows_dict if r.get("id_empadronado")]
        tuples = [
            tuple("" if r.get(col) is None else r.get(col, "") for col in self.columns)
            for r in rows_dict
        ]
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id_empadronado, codigo_centro_votacion, codigo_mesa, estado_registro
                    FROM electoral.empadronados
                    """
                )
                existing = {
                    str(ident): {
                        "codigo_centro_votacion": centro,
                        "codigo_mesa": mesa,
                        "estado_registro": estado,
                    }
                    for ident, centro, mesa, estado in cur.fetchall()
                }
                stats = classify_empadronados(rows_dict, existing)
                if not tuples:
                    # Todo en cuarentena o archivo vacío: no borro el padrón vigente.
                    stats["ausentes"] = 0
                    stats["omitido_vacio"] = True
                    logger.warning(
                        "IncrementalLoader %s: 0 filas válidas; no toco la tabla",
                        self.table,
                    )
                else:
                    cols = ", ".join(self.columns)
                    update_cols = [c for c in self.columns if c != "id_empadronado"]
                    set_sql = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
                    sql = (
                        f"INSERT INTO {self.table} ({cols}) VALUES %s "
                        f"ON CONFLICT (id_empadronado) DO UPDATE SET {set_sql}"
                    )
                    execute_values(cur, sql, tuples, page_size=1000)
                    cur.execute(
                        "DELETE FROM electoral.empadronados WHERE NOT (id_empadronado = ANY(%s))",
                        (incoming_ids,),
                    )
                    stats["ausentes"] = int(cur.rowcount or 0)
        self.last_stats = stats
        logger.info("IncrementalLoader %s: %s", self.table, stats)
        return len(tuples)
