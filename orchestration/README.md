# Orquestación

Implementación: **cron + `python -m orchestration.run`**.

La justificación, el diagrama y la política de fallos están en [`docs/ORQUESTACION.md`](../docs/ORQUESTACION.md).

| Comando | Qué hace |
|---|---|
| `python -m orchestration.run historico` | Carga única (centros → mesas → resultados) |
| `python -m orchestration.run diario` | Si falta el histórico lo carga; luego cada CSV de padrón pendiente |
| `python -m orchestration.run padron --fecha YYYY-MM-DD` | Un periodo |
| `python -m orchestration.run backfill --desde A --hasta B` | Rango, con `--overwrite` opcional |

Programación de ejemplo: [`crontab`](crontab).

El stack diario no se lanza con `./up.sh`. Para correrlo a mano: `docker compose --profile etl run --rm etl -m orchestration.run diario`.
