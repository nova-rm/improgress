"""Reintentos del orquestador. No requieren base de datos."""
from src.utils.watermark import DuplicateLoadError

from orchestration.run import _carga_vacia, with_retries


def test_with_retries_no_reintenta_duplicate_load():
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise DuplicateLoadError("ya cargada", fecha="2026-03-02")

    try:
        with_retries("padron", boom)
    except DuplicateLoadError:
        pass
    else:
        raise AssertionError("debía propagar DuplicateLoadError")
    assert calls["n"] == 1


def test_carga_vacia_detecta_todo_en_cuarentena():
    assert _carga_vacia({"cargados": 0, "rechazados": 10}) is True
    assert _carga_vacia({"cargados": 3, "rechazados": 10}) is False
    assert _carga_vacia({"cargados": 0, "rechazados": 0}) is False

