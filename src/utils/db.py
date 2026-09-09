"""Acceso a PostgreSQL.

El template expone lo mínimo. Si prefieres SQLAlchemy, Polars u otro cliente,
cámbialo y justifícalo en DECISIONES.md.
"""
from __future__ import annotations

from contextlib import contextmanager

import psycopg2
from psycopg2.extras import execute_values

from src.config.settings import DBSettings


@contextmanager
def get_connection():
    s = DBSettings.from_env()
    conn = psycopg2.connect(
        host=s.host, port=s.port, dbname=s.database, user=s.user, password=s.password
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_empadronados_periodo_column(default_periodo: str | None = None) -> None:
    """Añade electoral.empadronados.periodo si no existe, sin tocar 01_ddl."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                ALTER TABLE electoral.empadronados
                ADD COLUMN IF NOT EXISTS periodo VARCHAR(50)
                """
            )
            if default_periodo:
                cur.execute(
                    """
                    UPDATE electoral.empadronados
                    SET periodo = %s
                    WHERE periodo IS NULL OR periodo = ''
                    """,
                    (default_periodo,),
                )


def log_carga(proceso: str, observacion: str) -> None:
    from datetime import date

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO electoral.carga_log (proceso, observacion, fecha)
                VALUES (%s, %s, %s)
                """,
                (proceso[:255], observacion[:255], date.today().isoformat()),
            )


def insert_many(conn, table: str, columns: list[str], rows: list[tuple]) -> int:
    """Inserción masiva simple. TODO: evaluar si necesitas UPSERT aquí."""
    if not rows:
        return 0
    cols = ", ".join(columns)
    sql = f"INSERT INTO {table} ({cols}) VALUES %s"
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=1000)
    return len(rows)
