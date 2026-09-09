"""API mínima de inventario para saber qué data falta cargar."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg2 import OperationalError
from pydantic import BaseModel, Field

from src.api.coverage import (
    get_cargas,
    get_cobertura,
    get_tablas,
    list_periodos_empadronados,
    postgres_ok,
)
from src.api.tables import TABLES, get_table_page, list_tables
from src.config.settings import DBSettings, PROJECT_ROOT
from src.utils.watermark import DuplicateLoadError, historico_cargado

UI_DIR = PROJECT_ROOT / "ui"

app = FastAPI(
    title="ETL electoral — inventario",
    description="Cobertura de fuentes CSV vs tablas PostgreSQL.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _db_or_503() -> None:
    if not postgres_ok():
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL no está disponible. Revisa Docker y el .env.",
        )


class HistoricoLoadIn(BaseModel):
    overwrite: bool = False


class EmpadronadosLoadIn(BaseModel):
    fecha: str = Field(..., examples=["2026-03-02"])
    overwrite: bool = False


def _raise_load_error(exc: Exception) -> None:
    if isinstance(exc, DuplicateLoadError):
        raise HTTPException(status_code=409, detail=exc.as_detail()) from exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/", include_in_schema=False)
def ui_index() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    db = postgres_ok()
    settings = DBSettings.from_env()
    return {
        "status": "ok" if db else "degraded",
        "postgres": db,
        "database": settings.database,
        "host": settings.host,
        "port": settings.port,
    }


@app.get("/api/cobertura")
def cobertura() -> dict:
    _db_or_503()
    try:
        return get_cobertura()
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/tablas")
def tablas() -> dict:
    _db_or_503()
    try:
        payload = get_tablas()
        payload["catalogo"] = list_tables()
        return payload
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/tablas/{tabla}")
def tabla_detalle(
    tabla: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=120),
    periodo: str = Query("", max_length=10, description="Filtro YYYY-MM-DD (solo empadronados)"),
) -> dict:
    _db_or_503()
    if tabla not in TABLES:
        raise HTTPException(status_code=404, detail=f"Tabla no permitida: {tabla}")
    try:
        return get_table_page(tabla, limit=limit, offset=offset, q=q, periodo=periodo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/cargas/historico")
def cargar_historico(payload: HistoricoLoadIn | None = None) -> dict:
    _db_or_503()
    overwrite = bool(payload.overwrite) if payload else False
    if not overwrite and historico_cargado():
        raise HTTPException(
            status_code=409,
            detail=DuplicateLoadError(
                "El histórico ya está cargado. Si continúas se truncarán centros, "
                "mesas y resultados y se volverán a escribir (no se duplican filas).",
            ).as_detail(),
        )
    from src.pipelines.historico_pipeline import run_historico

    try:
        metricas = run_historico()
    except Exception as exc:
        _raise_load_error(exc)
    return {"ok": True, "metricas": metricas}


@app.get("/api/empadronados/periodos")
def periodos_empadronados() -> dict:
    _db_or_503()
    try:
        payload = list_periodos_empadronados()
        payload["historico_cargado"] = historico_cargado()
        return payload
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/cargas/empadronados")
def cargar_empadronados(payload: EmpadronadosLoadIn) -> dict:
    _db_or_503()
    from src.pipelines.empadronados_pipeline import run_empadronados

    try:
        metricas = run_empadronados(payload.fecha, overwrite=payload.overwrite)
    except Exception as exc:
        _raise_load_error(exc)
    return {"ok": True, "metricas": metricas}


@app.get("/api/cargas")
def cargas() -> dict:
    _db_or_503()
    try:
        return get_cargas()
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


app.mount("/assets", StaticFiles(directory=UI_DIR), name="assets")
