"""Transformaciones reutilizables de estandarización."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Iterable

from src.transformers.base import BaseTransformer

_WS = re.compile(r"\s+")
_THOUSANDS_US = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")
_THOUSANDS_EU = re.compile(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$")
_DECIMAL_COMMA = re.compile(r"^-?\d+,\d+$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DMY_SHORT = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2})$")
# 00-30 → 2000-2030; 31-99 → 1931-1999 (inscripciones electorales).
_YY_PIVOT = 30
_SMALL = {"de", "del", "la", "las", "los", "y"}

# Forma canónica cuando hay variantes (espacios, mayúsculas, acentos).
# Solo se restauran acentos si alguna variante de la fuente ya los traía.
CANONICAL_GEO = {
    "alta verapaz": "Alta Verapaz",
    "departamento desconocido": "Departamento desconocido",
    "escuintla": "Escuintla",
    "guatemala": "Guatemala",
    "peten": "Petén",
    "quetzaltenango": "Quetzaltenango",
    "sacatepequez": "Sacatepéquez",
    "san marcos": "San Marcos",
    "solola": "Sololá",
    "amatitlan": "Amatitlán",
    "antigua guatemala": "Antigua Guatemala",
    "chisec": "Chisec",
    "coatepeque": "Coatepeque",
    "coban": "Cobán",
    "flores": "Flores",
    "jocotenango": "Jocotenango",
    "la libertad": "La Libertad",
    "malacatan": "Malacatán",
    "mixco": "Mixco",
    "panajachel": "Panajachel",
    "salcaja": "Salcajá",
    "san benito": "San Benito",
    "san miguel petapa": "San Miguel Petapa",
    "san pedro carcha": "San Pedro Carchá",
    "santa lucia cotzumalguapa": "Santa Lucía Cotzumalguapa",
    "santiago atitlan": "Santiago Atitlan",
    "sumpango": "Sumpango",
    "tacana": "Tacaná",
    "tiquisate": "Tiquisate",
    "villa nueva": "Villa Nueva",
}


def fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", text.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return _WS.sub(" ", s)


def collapse_ws(value: str) -> str:
    return _WS.sub(" ", value.strip())


def title_es(value: str) -> str:
    parts = collapse_ws(value).split(" ")
    out: list[str] = []
    for i, part in enumerate(parts):
        low = part.lower()
        if i > 0 and low in _SMALL:
            out.append(low)
        else:
            out.append(low[:1].upper() + low[1:] if low else low)
    return " ".join(out)


def normalize_geo(value: str) -> str:
    cleaned = collapse_ws(value)
    if not cleaned:
        return ""
    return CANONICAL_GEO.get(fold(cleaned), title_es(cleaned))


def parse_number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = collapse_ws(str(value)).replace(" ", "")
    if not s:
        return None
    if _THOUSANDS_EU.match(s):
        s = s.replace(".", "").replace(",", ".")
    elif _THOUSANDS_US.match(s):
        s = s.replace(",", "")
    elif _DECIMAL_COMMA.match(s):
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def number_to_str(value: float | None) -> str:
    if value is None:
        return ""
    if value.is_integer():
        return str(int(value))
    return format(value, ".10g")


def _expand_year(year: int) -> int:
    if year >= 100:
        return year
    return 2000 + year if year <= _YY_PIVOT else 1900 + year


def parse_date(value: str) -> str:
    s = collapse_ws(value)
    if not s:
        return ""
    if _ISO_DATE.match(s):
        datetime.strptime(s, "%Y-%m-%d")
        return s
    m = _DMY_DATE.match(s) or _DMY_SHORT.match(s)
    if m:
        day, month, year = m.groups()
        dt = datetime(_expand_year(int(year)), int(month), int(day))
        return dt.strftime("%Y-%m-%d")
    raise ValueError(f"fecha no reconocida: {value}")


class TrimStrings(BaseTransformer):
    """Recorta espacios en todos los campos de texto."""

    def transform(self, records: Iterable[dict]) -> Iterable[dict]:
        for r in records:
            yield {k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()}


class NormalizeText(BaseTransformer):
    """Estandariza nombres geográficos y de centros: espacios, mayúsculas y acentos."""

    def __init__(self, fields: list[str]) -> None:
        self.fields = fields

    def transform(self, records: Iterable[dict]) -> Iterable[dict]:
        for r in records:
            out = dict(r)
            for field in self.fields:
                raw = out.get(field)
                if isinstance(raw, str):
                    if field in {
                        "nombre_departamento",
                        "nombre_municipio",
                    }:
                        out[field] = normalize_geo(raw)
                    else:
                        cleaned = collapse_ws(raw)
                        out[field] = (
                            title_es(cleaned)
                            if cleaned.isupper() or cleaned.islower()
                            else cleaned
                        )
            yield out


class CastNumeric(BaseTransformer):
    """Convierte números con coma decimal, miles y vacíos a forma canónica."""

    def __init__(self, fields: list[str]) -> None:
        self.fields = fields

    def transform(self, records: Iterable[dict]) -> Iterable[dict]:
        for r in records:
            out = dict(r)
            for field in self.fields:
                if field not in out:
                    continue
                raw = out[field]
                if str(raw or "").strip() == "":
                    out[field] = ""
                    continue
                parsed = parse_number(raw)
                out[field] = number_to_str(parsed) if parsed is not None else raw
            yield out


class ParseDates(BaseTransformer):
    """Convierte fechas YYYY-MM-DD, DD/MM/YYYY y DD/MM/YY a ISO. Vacío se deja vacío."""

    def __init__(self, fields: list[str]) -> None:
        self.fields = fields

    def transform(self, records: Iterable[dict]) -> Iterable[dict]:
        for r in records:
            out = dict(r)
            for field in self.fields:
                raw = out.get(field)
                if not isinstance(raw, str) or not raw.strip():
                    out[field] = ""
                    continue
                try:
                    out[field] = parse_date(raw)
                except ValueError:
                    out[field] = raw.strip()
            yield out


class StandardizeCategories(BaseTransformer):
    """Estandariza categorías con un mapa {campo: {origen: canónico}}."""

    def __init__(self, mapping: dict[str, dict[str, str]]) -> None:
        self.mapping: dict[str, dict[str, str]] = {}
        for field, aliases in mapping.items():
            folded = {fold(str(src)): dst for src, dst in aliases.items()}
            for dst in list(folded.values()):
                folded.setdefault(fold(str(dst)), dst)
            self.mapping[field] = folded

    def transform(self, records: Iterable[dict]) -> Iterable[dict]:
        for r in records:
            out = dict(r)
            for field, aliases in self.mapping.items():
                raw = out.get(field)
                if raw is None:
                    continue
                key = fold(str(raw))
                if key in aliases:
                    out[field] = aliases[key]
                elif field == "partido":
                    out[field] = collapse_ws(str(raw)).upper()
            yield out


class Deduplicate(BaseTransformer):
    """Elimina duplicados por llave natural. Si hay diferencias, sobrevive la última fila."""

    def __init__(self, key: list[str]) -> None:
        self.key = key

    def transform(self, records: Iterable[dict]) -> Iterable[dict]:
        seen: dict[tuple, dict] = {}
        for r in records:
            k = tuple(r.get(f) for f in self.key)
            seen[k] = r
        yield from seen.values()


class AssignField(BaseTransformer):
    def __init__(self, field: str, value: str) -> None:
        self.field = field
        self.value = value

    def transform(self, records: Iterable[dict]) -> Iterable[dict]:
        for r in records:
            out = dict(r)
            out[self.field] = self.value
            yield out


class EnrichFromCatalog(BaseTransformer):
    def __init__(self, key: str, catalog: dict[str, dict]) -> None:
        self.key = key
        self.catalog = catalog

    def transform(self, records: Iterable[dict]) -> Iterable[dict]:
        for r in records:
            extra = self.catalog.get(str(r.get(self.key) or ""), {})
            yield {**r, **extra}


class FillEmpty(BaseTransformer):
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def transform(self, records: Iterable[dict]) -> Iterable[dict]:
        for r in records:
            out = dict(r)
            for field, fallback in self.values.items():
                if not str(out.get(field) or "").strip():
                    out[field] = fallback
            yield out
