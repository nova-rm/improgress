"""Orquestador de los dos flujos del ETL.

Uso:
    python -m orchestration.run historico
    python -m orchestration.run diario
    python -m orchestration.run padron --fecha 2026-03-03
    python -m orchestration.run backfill --desde 2026-03-02 --hasta 2026-03-04
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta

from src.config.settings import PROJECT_ROOT
from src.utils.logger import get_logger
from src.utils.watermark import DuplicateLoadError, historico_cargado

logger = get_logger("orquestacion")

MAX_ATTEMPTS = 3
BASE_SLEEP_SECONDS = 2
ALERTS_PATH = PROJECT_ROOT / "logs" / "alerts.log"
NO_REINTENTAR = (DuplicateLoadError, FileNotFoundError, ValueError)


def _emit_alert(proceso: str, mensaje: str) -> None:
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "proceso": proceso,
        "mensaje": mensaje,
    }
    logger.error("ALERTA %s | %s", proceso, mensaje)
    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    try:
        from src.utils.db import log_carga

        log_carga(f"alerta:{proceso}"[:255], mensaje[:255])
    except Exception:
        logger.warning("No pude escribir la alerta en carga_log")


def with_retries(label: str, fn):
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return fn()
        except NO_REINTENTAR:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "%s falló (intento %s/%s): %s",
                label,
                attempt,
                MAX_ATTEMPTS,
                exc,
            )
            if attempt == MAX_ATTEMPTS:
                break
            time.sleep(BASE_SLEEP_SECONDS * (2 ** (attempt - 1)))
    raise last_exc  # type: ignore[misc]


def _run_historico() -> list[dict]:
    from src.pipelines.historico_pipeline import run_historico

    return list(run_historico())


def _run_padron(fecha: str, overwrite: bool) -> dict:
    from src.pipelines.empadronados_pipeline import run_empadronados

    return run_empadronados(fecha, overwrite=overwrite)


def _periodos_pendientes() -> list[str]:
    from src.api.coverage import list_periodos_empadronados

    return [
        item["fecha"]
        for item in list_periodos_empadronados()["periodos"]
        if not item["cargada"]
    ]


def _fechas_con_archivo(desde: str, hasta: str) -> list[str]:
    from src.api.coverage import list_periodos_empadronados

    disponibles = {
        item["fecha"] for item in list_periodos_empadronados()["periodos"]
    }
    start = datetime.strptime(desde, "%Y-%m-%d").date()
    end = datetime.strptime(hasta, "%Y-%m-%d").date()
    if start > end:
        raise ValueError("--desde no puede ser posterior a --hasta.")
    fechas: list[str] = []
    cursor = start
    while cursor <= end:
        iso = cursor.isoformat()
        if iso in disponibles:
            fechas.append(iso)
        else:
            logger.info("Sin archivo para %s; lo salto", iso)
        cursor += timedelta(days=1)
    return fechas


def _carga_vacia(metrics: dict) -> bool:
    return int(metrics.get("cargados") or 0) == 0 and int(metrics.get("rechazados") or 0) > 0


def cmd_historico(_args: argparse.Namespace) -> int:
    try:
        metrics = with_retries("historico", _run_historico)
    except Exception as exc:
        _emit_alert("historico", str(exc))
        return 1
    for item in metrics:
        logger.info("histórico %s", item)
    return 0


def cmd_padron(args: argparse.Namespace) -> int:
    try:
        metrics = with_retries(
            f"padron:{args.fecha}",
            lambda: _run_padron(args.fecha, args.overwrite),
        )
    except DuplicateLoadError as exc:
        logger.info("%s Usa --overwrite para sobreescribir.", exc.mensaje)
        return 2
    except Exception as exc:
        _emit_alert(f"padron:{args.fecha}", str(exc))
        return 1
    logger.info("padrón %s", metrics)
    if _carga_vacia(metrics):
        _emit_alert(
            f"padron:{args.fecha}",
            f"Cargó 0 filas y rechazó {metrics.get('rechazados', 0)}; no actualicé el padrón.",
        )
        return 1
    return 0


def cmd_diario(args: argparse.Namespace) -> int:
    if not historico_cargado():
        logger.info("El catálogo histórico está vacío; lo cargo antes del padrón.")
        if cmd_historico(args) != 0:
            return 1

    try:
        pendientes = _periodos_pendientes()
    except Exception as exc:
        _emit_alert("diario", f"No pude listar periodos: {exc}")
        return 1

    if not pendientes:
        logger.info("Nada pendiente: el padrón ya está al día.")
        return 0

    failed = False
    for fecha in pendientes:
        logger.info("Diario: cargo periodo %s", fecha)
        try:
            metrics = with_retries(
                f"diario:{fecha}",
                lambda f=fecha: _run_padron(f, overwrite=False),
            )
        except DuplicateLoadError as exc:
            logger.info("Salto %s: %s", fecha, exc.mensaje)
            continue
        except Exception as exc:
            _emit_alert(f"diario:{fecha}", str(exc))
            failed = True
            break
        logger.info("padrón %s", metrics)
        if _carga_vacia(metrics):
            _emit_alert(
                f"diario:{fecha}",
                f"Cargó 0 filas y rechazó {metrics.get('rechazados', 0)}; no actualicé el padrón.",
            )
            failed = True
            break
    return 1 if failed else 0


def cmd_backfill(args: argparse.Namespace) -> int:
    if not historico_cargado():
        logger.info("El catálogo histórico está vacío; lo cargo antes del backfill.")
        if cmd_historico(args) != 0:
            return 1

    try:
        fechas = _fechas_con_archivo(args.desde, args.hasta)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    if not fechas:
        logger.info("No hay archivos de padrón entre %s y %s", args.desde, args.hasta)
        return 0

    failed = False
    for fecha in fechas:
        logger.info("Backfill: cargo periodo %s", fecha)
        try:
            metrics = with_retries(
                f"backfill:{fecha}",
                lambda f=fecha: _run_padron(f, overwrite=args.overwrite),
            )
        except DuplicateLoadError as exc:
            logger.info("Salto %s: %s", fecha, exc.mensaje)
            continue
        except Exception as exc:
            _emit_alert(f"backfill:{fecha}", str(exc))
            failed = True
            break
        logger.info("padrón %s", metrics)
        if _carga_vacia(metrics):
            _emit_alert(
                f"backfill:{fecha}",
                f"Cargó 0 filas y rechazó {metrics.get('rechazados', 0)}; no actualicé el padrón.",
            )
            failed = True
            break
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Orquestador del ETL electoral (histórico + padrón diario)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_hist = sub.add_parser("historico", help="Carga única de centros, mesas y resultados")
    p_hist.set_defaults(func=cmd_historico)

    p_padron = sub.add_parser("padron", help="Carga un periodo concreto del padrón")
    p_padron.add_argument("--fecha", required=True, help="YYYY-MM-DD")
    p_padron.add_argument(
        "--overwrite",
        action="store_true",
        help="Sobreescribe un periodo ya cargado",
    )
    p_padron.set_defaults(func=cmd_padron)

    p_diario = sub.add_parser(
        "diario",
        help="Carga el histórico si falta y luego todos los periodos de padrón pendientes",
    )
    p_diario.set_defaults(func=cmd_diario)

    p_back = sub.add_parser("backfill", help="Reprocesa un rango de fechas del padrón")
    p_back.add_argument("--desde", required=True, help="YYYY-MM-DD inclusive")
    p_back.add_argument("--hasta", required=True, help="YYYY-MM-DD inclusive")
    p_back.add_argument(
        "--overwrite",
        action="store_true",
        help="Reaplica fotos ya cargadas en el rango",
    )
    p_back.set_defaults(func=cmd_backfill)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
