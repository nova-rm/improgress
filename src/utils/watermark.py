"""Marca de agua y detección de cargas duplicadas sin tocar el DDL."""
from __future__ import annotations

import re

from src.utils.db import get_connection

_EMP_PROCESO = re.compile(r"^empadronados:(\d{4}-\d{2}-\d{2})$")


class DuplicateLoadError(Exception):
    """La fecha ya se procesó o el watermark quedaría hacia atrás."""

    def __init__(self, mensaje: str, **extra) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.extra = extra

    def as_detail(self) -> dict:
        return {
            "code": "ya_cargada",
            "mensaje": self.mensaje,
            "requiere_overwrite": True,
            **self.extra,
        }


def list_fechas_empadronados_cargadas() -> list[str]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT proceso, observacion FROM electoral.carga_log WHERE proceso LIKE %s",
                ("empadronados:%",),
            )
            fechas: list[str] = []
            for proceso, observacion in cur.fetchall():
                match = _EMP_PROCESO.match(proceso or "")
                if not match:
                    continue
                obs = observacion or ""
                if re.search(r"cargados=0(?:;|$)", obs):
                    continue
                fechas.append(match.group(1))
    return sorted(set(fechas))


def watermark_empadronados() -> str | None:
    fechas = list_fechas_empadronados_cargadas()
    return max(fechas) if fechas else None


def fecha_empadronados_cargada(fecha: str) -> bool:
    return fecha in set(list_fechas_empadronados_cargadas())


def historico_cargado() -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM electoral.centros_votacion")
            return int(cur.fetchone()[0]) > 0
