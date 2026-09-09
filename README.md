# ETL electoral

Prueba técnica Junior Data Engineer: carga sobre el esquema `electoral` que ya está en producción. El enunciado está en [`ENUNCIADO.md`](ENUNCIADO.md).

Este repo deja el histórico y el padrón diario en PostgreSQL, con calidad de datos, orquestación y un inventario para disparar las cargas tabla a tabla. **No toqué** `sql/01_ddl_electoral.sql`.

## Qué hay aquí

| Ruta | Para qué |
|---|---|
| `src/` | ETL: extractores, transformers, loaders, pipelines |
| `main.py` | CLI: `load-historico` y `load-empadronados --fecha` |
| `orchestration/` | Cron + `python -m orchestration.run` (histórico y padrón diario) |
| `ui/` + `src/api/` | Inventario, cargas y exploración (no lo pide el enunciado) |
| `data/historico/` | Centros y resultados (carga única) |
| `data/empadronados/` | Fotos diarias del padrón |
| `docs/MEJORAS_MODELO.md` | Crítica al modelo + DER propuesto |
| `docs/ORQUESTACION.md` | Por qué cron y no Airflow |
| `DECISIONES.md` | Supuestos, basura en las fuentes, qué no hice |
| `sql/01_ddl_electoral.sql` | Modelo de producción — no modificar |
| `sql/02_empadronados_periodo.sql` | Columna aditiva `periodo` |
| `sql/99_propuesta_mejoras.sql` | Esquema paralelo; no corre en el `docker compose up` |

## Requisitos

- Docker y Docker Compose, **o** Python 3.10+ y PostgreSQL 14+
- Copiar `.env.example` a `.env` (no se versiona `.env`)

## Arranque con Docker (un comando)

Los tests unitarios corren **antes** de levantar la API. Si fallan, el stack no arranca. Postgres reutiliza el volumen `pgdata`: **no recarga tablas** y **no ejecuta el job diario**. Las cargas las disparas tú, una a una.

```bash
git clone https://github.com/nova-rm/improgress.git
cd improgress
git checkout prueba
cp .env.example .env
./up.sh
```

- UI: http://localhost:8000
- Health: http://localhost:8000/health
- API: http://localhost:8000/docs

Otro puerto en el host (si 8000 está ocupado):

```bash
API_PORT=8080 ./up.sh
```

UI en http://localhost:8080. Postgres sigue en `localhost:5432` (contenedor `electoral_pg`).

**No uses** `docker compose down -v`: borra `pgdata`. Para parar: `docker compose stop`.

### Probar el flujo en la UI

1. Abre la UI.
2. **Cargar histórico** (centros → mesas derivadas → resultados).
3. Carga el padrón **una fecha a la vez** (2026-03-02, luego 03, luego 04).
4. **Explorar → Empadronados** y filtra por `periodo`.

## Arranque sin Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

createdb electoral_db
psql -d electoral_db -f sql/01_ddl_electoral.sql
psql -d electoral_db -f sql/02_empadronados_periodo.sql

PYTHONPATH=. pytest -q
python main.py load-historico
python main.py load-empadronados --fecha 2026-03-02
python main.py load-empadronados --fecha 2026-03-03
python main.py load-empadronados --fecha 2026-03-04
```

Si el volumen de Docker ya existía, el `ALTER` de `periodo` lo aplica el ETL al cargar o al explorar empadronados.

API local:

```bash
uvicorn src.api.app:app --reload --port 8000
```

## Orquestación

Detalle en [`docs/ORQUESTACION.md`](docs/ORQUESTACION.md). Cron de ejemplo: `orchestration/crontab`.

```bash
python -m orchestration.run historico
python -m orchestration.run diario
python -m orchestration.run padron --fecha 2026-03-03
python -m orchestration.run backfill --desde 2026-03-02 --hasta 2026-03-04
```

En Docker (el host de Postgres dentro de la red es `postgres`):

```bash
docker compose --profile etl run --rm etl -m orchestration.run historico
docker compose --profile etl run --rm etl -m orchestration.run diario
```

Reprocesar un periodo ya cargado: `--overwrite` (CLI) o el diálogo de la UI.

## Flujos

| Flujo | Modo | Cómo |
|---|---|---|
| Centros, mesas, resultados | Carga única, idempotente (`TRUNCATE` + `INSERT`) | UI, `main.py load-historico` o `orchestration.run historico` |
| Padrón | Incremental diaria (upsert + bajas por ausencia) | UI, `load-empadronados --fecha` o `orchestration.run diario` |

Cada fila de `electoral.empadronados` tiene `periodo` (`YYYY-MM-DD`): de qué foto diaria sale el registro vigente. Eso no historiza traslados; ver `docs/MEJORAS_MODELO.md`.
