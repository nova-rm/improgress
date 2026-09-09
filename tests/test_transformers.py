"""Pruebas de las transformaciones. No requieren base de datos."""
from src.transformers.common import (
    AssignField,
    CastNumeric,
    Deduplicate,
    NormalizeText,
    ParseDates,
    StandardizeCategories,
    TrimStrings,
    parse_date,
    parse_number,
)


def test_trim_strings():
    records = [{"nombre": "  Sololá  ", "codigo": "07"}]
    out = list(TrimStrings().transform(records))
    assert out[0]["nombre"] == "Sololá"


def test_normalize_text():
    records = [
        {"nombre_departamento": " PETÉN ", "nombre_municipio": "AMATITLÁN"},
        {"nombre_departamento": "Peten", "nombre_municipio": "Amatitlan"},
        {"nombre_departamento": "guatemala", "nombre_municipio": " San Miguel Petapa "},
    ]
    out = list(
        NormalizeText(["nombre_departamento", "nombre_municipio"]).transform(records)
    )
    assert {r["nombre_departamento"] for r in out} == {"Petén", "Guatemala"}
    assert out[0]["nombre_municipio"] == "Amatitlán"
    assert out[1]["nombre_municipio"] == "Amatitlán"
    assert out[2]["nombre_municipio"] == "San Miguel Petapa"


def test_cast_numeric_con_separador_de_miles():
    records = [
        {"votos": "1,234", "lat": "16,489162", "vacio": ""},
    ]
    out = list(CastNumeric(["votos", "lat", "vacio"]).transform(records))
    assert out[0]["votos"] == "1234"
    assert out[0]["lat"] == "16.489162"
    assert out[0]["vacio"] == ""
    assert parse_number("1.234,50") == 1234.5


def test_parse_dates_formato_mixto():
    records = [{"a": "05/03/2019", "b": "2019-03-05", "c": "", "d": "5/11/04", "e": "1/03/26"}]
    out = list(ParseDates(["a", "b", "c", "d", "e"]).transform(records))
    assert out[0]["a"] == "2019-03-05"
    assert out[0]["b"] == "2019-03-05"
    assert out[0]["c"] == ""
    assert out[0]["d"] == "2004-11-05"
    assert out[0]["e"] == "2026-03-01"


def test_standardize_categories():
    mapping = {
        "area": {"": "desconocido", "u": "urbana", "urbana": "urbana", "r": "rural"},
        "partido": {"une": "UNE", "u.n.e.": "UNE"},
    }
    records = [
        {"area": "U", "partido": "une"},
        {"area": "RURAL", "partido": "U.N.E."},
        {"area": "", "partido": "VIVA"},
    ]
    out = list(StandardizeCategories(mapping).transform(records))
    assert [r["area"] for r in out] == ["urbana", "rural", "desconocido"]
    assert [r["partido"] for r in out] == ["UNE", "UNE", "VIVA"]


def test_deduplicate_last_wins():
    records = [
        {"codigo": "01", "nombre": "A"},
        {"codigo": "01", "nombre": "B"},
        {"codigo": "02", "nombre": "C"},
    ]
    out = list(Deduplicate(["codigo"]).transform(records))
    by_code = {r["codigo"]: r["nombre"] for r in out}
    assert by_code == {"01": "B", "02": "C"}


def test_assign_field_periodo():
    records = [{"id_empadronado": "E1"}]
    out = list(AssignField("periodo", "2026-03-04").transform(records))
    assert out[0]["periodo"] == "2026-03-04"
    assert out[0]["id_empadronado"] == "E1"


def test_classify_empadronados_altas_cambios_bajas():
    from src.loaders.postgres_loader import classify_empadronados

    existing = {
        "E1": {
            "codigo_centro_votacion": "A",
            "codigo_mesa": "A-1",
            "estado_registro": "activo",
        },
        "E2": {
            "codigo_centro_votacion": "B",
            "codigo_mesa": "B-1",
            "estado_registro": "activo",
        },
        "E3": {
            "codigo_centro_votacion": "C",
            "codigo_mesa": "C-1",
            "estado_registro": "activo",
        },
    }
    incoming = [
        {
            "id_empadronado": "E1",
            "codigo_centro_votacion": "A",
            "codigo_mesa": "A-1",
            "estado_registro": "activo",
        },
        {
            "id_empadronado": "E2",
            "codigo_centro_votacion": "Z",
            "codigo_mesa": "Z-9",
            "estado_registro": "suspendido",
        },
        {
            "id_empadronado": "E4",
            "codigo_centro_votacion": "N",
            "codigo_mesa": "N-1",
            "estado_registro": "activo",
        },
    ]
    stats = classify_empadronados(incoming, existing)
    assert stats["altas"] == 1
    assert stats["cambios"] == 1
    assert stats["bajas"] == 1
    assert stats["ausentes"] == 1
