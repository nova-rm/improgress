"""Validaciones de calidad de datos.

Un registro inválido no detiene el flujo: se separa, se envía a cuarentena
(archivo CSV) y se registra en carga_log. Criterio documentado en DECISIONES.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from src.transformers.common import parse_date, parse_number


@dataclass
class ValidationResult:
    valid: list[dict] = field(default_factory=list)
    rejected: list[tuple[dict, str]] = field(default_factory=list)

    @property
    def summary(self) -> dict:
        reasons: dict[str, int] = {}
        for _, reason in self.rejected:
            reasons[reason] = reasons.get(reason, 0) + 1
        return {
            "validos": len(self.valid),
            "rechazados": len(self.rejected),
            "motivos": reasons,
        }


class Validator:
    """Aplica una lista de reglas y separa válidos de rechazados."""

    def __init__(self, rules: list[tuple[str, Callable[[dict], bool]]]) -> None:
        self.rules = rules

    def run(self, records: Iterable[dict]) -> ValidationResult:
        result = ValidationResult()
        for r in records:
            for name, rule in self.rules:
                if not rule(r):
                    result.rejected.append((r, name))
                    break
            else:
                result.valid.append(r)
        return result


def rule_natural_key(fields: list[str]):
    def _check(row: dict) -> bool:
        return all(str(row.get(f) or "").strip() for f in fields)

    return _check


def rule_non_negative(fields: list[str]):
    def _check(row: dict) -> bool:
        for f in fields:
            parsed = parse_number(row.get(f))
            if parsed is None or parsed < 0:
                return False
        return True

    return _check


def rule_voters_le_registered(
    voters_field: str = "total_votantes_mesa",
    registered_field: str = "total_empadronados_mesa",
):
    def _check(row: dict) -> bool:
        voters = parse_number(row.get(voters_field))
        registered = parse_number(row.get(registered_field))
        if voters is None or registered is None:
            return False
        return voters <= registered

    return _check


def rule_in_catalog(field: str, catalog: set[str]):
    def _check(row: dict) -> bool:
        return str(row.get(field) or "").strip() in catalog

    return _check


def rule_in_domain(field: str, allowed: set[str], allow_empty: bool = False):
    def _check(row: dict) -> bool:
        value = str(row.get(field) or "").strip()
        if not value:
            return allow_empty
        return value in allowed

    return _check


def rule_dates_parseable(fields: list[str], min_year: int = 1900, max_year: int = 2030):
    def _check(row: dict) -> bool:
        for f in fields:
            raw = str(row.get(f) or "").strip()
            if not raw:
                continue
            try:
                iso = parse_date(raw)
            except ValueError:
                return False
            year = int(iso[:4])
            if year < min_year or year > max_year:
                return False
        return True

    return _check
