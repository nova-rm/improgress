"""Punto de entrada del ETL.

Ejemplos de uso esperado:
    python main.py load-historico
    python main.py load-empadronados --fecha 2026-03-02
    python main.py load-empadronados --fecha 2026-03-03

Puedes cambiar la interfaz del CLI si lo justificas, pero debe permitir
ejecutar la carga histórica y una fecha específica del padrón (backfill).
"""
from __future__ import annotations

import argparse

from src.utils.logger import get_logger

logger = get_logger("main")


def cmd_load_historico(args: argparse.Namespace) -> None:
    from src.pipelines.historico_pipeline import run_historico

    for metrics in run_historico():
        logger.info("histórico %s", metrics)


def cmd_load_empadronados(args: argparse.Namespace) -> None:
    from src.pipelines.empadronados_pipeline import run_empadronados
    from src.utils.watermark import DuplicateLoadError

    try:
        metrics = run_empadronados(args.fecha, overwrite=args.overwrite)
    except DuplicateLoadError as exc:
        logger.error("%s Usa --overwrite si quieres sobreescribir.", exc.mensaje)
        raise SystemExit(2) from exc

    logger.info("empadronados %s", metrics)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ETL electoral")
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("load-historico", help="Carga única de data histórica")
    p1.set_defaults(func=cmd_load_historico)

    p2 = sub.add_parser("load-empadronados", help="Carga incremental del padrón")
    p2.add_argument("--fecha", required=True, help="Fecha de proceso YYYY-MM-DD")
    p2.add_argument(
        "--overwrite",
        action="store_true",
        help="Sobreescribe un periodo ya cargado o un watermark posterior",
    )
    p2.set_defaults(func=cmd_load_empadronados)

    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
