# Decisiones y supuestos

Escribo esto en primera persona: son las decisiones que tomé al construir el ETL.

## 1. Supuestos que tomé

| # | Supuesto | Por qué lo tomé |
|---|---|---|
| 1 | Traté la carga histórica como reemplazo completo (`TRUNCATE` + `INSERT` en una transacción). | Noté que el modelo no declara unicidad ni `ON CONFLICT`. Sin eso un upsert no es seguro y un `INSERT` puro me duplicaría filas. |
| 2 | Derivé las mesas de `codigo_mesa` + `codigo_centro_votacion` en resultados. El número de mesa es el sufijo después del último `-`. | No había archivo de mesas. El enunciado pide derivarlas. |
| 3 | Enriquecí `nombre_departamento` y `nombre_municipio` de resultados desde el catálogo de centros. | El CSV de resultados no trae esos nombres y la tabla sí los pide. |
| 4 | Un registro inválido no tumba el flujo: lo mando a `data/quarantine/` y cargo el resto. | El enunciado pide no fallar en silencio. Elegí cuarentena para poder auditar sin perder la corrida. |
| 5 | Dejé `fechaCarga` en ISO (`YYYY-MM-DD`) con la fecha de ejecución. | El modelo es `VARCHAR`; ISO me evitó mezclar los dos formatos de las fuentes. |
| 6 | Traté cada CSV de empadronados como foto completa del padrón a esa fecha, no como delta. | Así viene el enunciado. Por eso hago upsert de la foto y borro ids que ya no aparecen. |
| 7 | El padrón vigente es una sola foto: no historio cambios en la tabla (el DDL no da SCD). | Lo documenté como pérdida: si alguien se traslada, sobreescribo centro/mesa y pierdo el valor anterior. |
| 8 | Añadí `periodo` (fecha de la foto, YYYY-MM-DD) a cada fila de empadronados. | Sin eso, al abrir la tabla no se sabe de qué CSV diario viene el registro vigente. |

## 2. Hallazgos de calidad de datos

| # | Fuente | Qué noté | Ejemplo | Qué hice | Por qué |
|---|---|---|---|---|---|
| 1 | centros | Nombres geográficos con espacios, mayúsculas y acentos mezclados | ` PETÉN `, `Peten`, `AMATITLÁN` | Unifiqué a forma canónica (`Petén`, `Amatitlán`) | Si no, el dashboard parte un mismo departamento en cinco grafías. |
| 2 | centros | `area` no estandarizada y a veces vacía | `U`, `URBANA`, vacío (12 filas) | Mapeé a `urbana` / `rural` / `desconocido` | Vacío no es rural ni urbana; no lo inventé. |
| 3 | centros | `zona` vacía o `SIN ZONA` | 31 vacíos, 23 `SIN ZONA` | Dejé la zona vacía | No iba a inventar un número de zona. |
| 4 | centros | Latitud con coma decimal | `16,489162` | La pasé a punto | El mismo campo mezclaba `14.704057` y coma. |
| 5 | centros | Duplicado exacto de código | `0102004` dos veces | Dedupliqué | El catálogo tiene que ser 1:1. |
| 6 | centros | Duplicado con diferencia de mayúsculas | `0104001` | Normalicé texto y dejé la última fila | Tras normalizar era el mismo centro. |
| 7 | centros | Departamento sentinela | `DEPARTAMENTO DESCONOCIDO` | Lo cargué como `Departamento desconocido` | Era un hallazgo, no un error de parseo. |
| 8 | resultados | Partido con alias | `une`, `UNE`, `U.N.E.` | Unifiqué a `UNE` | Si no, partía los votos del mismo partido. |
| 9 | resultados | `vuelta` vacía en legislativa (4232 filas) | `legislativa` + `vuelta=` | Llené con `NA` | Entra en la llave natural; el vacío rompía el dedupe. |
| 10 | resultados | Votos vacíos o negativos | `-12` | Cuarentena (`votos_no_negativos`, 34 post-dedupe) | Un voto negativo no es usable. |
| 11 | resultados | Centro huérfano | `0104999` | Cuarentena: 1 mesa y 13 resultados | No podía ubicar esa mesa en el catálogo. |
| 12 | resultados | Duplicados de llave (113 claves; 5 con votos distintos) | mesa `0104999-01` + `VIVA` | Sobrevive la **última** fila del archivo | Sin unicidad en DB tuve que elegir; tomé la última como corrección. |
| 13 | resultados | Votantes > empadronados | mesa `0301002-04`: 442 vs 393 | Cuarentena (37 post-dedupe) | Puede ser hallazgo de negocio; la regla del template lo marca inválido. |
| 14 | empadronados | `sexo` con alias y ~2500 vacíos | `F`, `f`, `FEMENINO`, `MASCULINO`, vacío | Mapeé a `F` / `M` / `desconocido` | No iba a tirar el 14% del padrón por un vacío. |
| 15 | empadronados | `estado_registro` con mayúsculas mixtas | `ACTIVO`, `Activo`, `SUSPENDIDO` | Unifiqué a `activo` / `suspendido` / `fallecido` | Es el dominio de bajas del enunciado. |
| 16 | empadronados | `rango_edad` con dos grafías | `18 a 25` vs `18-25`, `mayor de 60` vs `61+` | Unifiqué a `18-25`, `26-35`, `36-45`, `46-60`, `61+` | Si no, cualquier KPI por edad se parte. |
| 17 | empadronados | Fechas de inscripción en ISO y `DD/MM/YYYY` | `05/03/2019` y `2019-03-05` | Las pasé todas a ISO | Pedido del enunciado; `ParseDates` ya lo hacía. |
| 18 | empadronados | 25 ids duplicados dentro del mismo archivo | `E0000943` | Dedupliqué; sobrevive la última | La PK de la tabla no admitiría el duplicado. |
| 19 | empadronados | ~30 centros que no están en el catálogo | códigos huérfanos | Cuarentena (`centro_en_catalogo`) | Misma regla que en resultados. |
| 21 | empadronados | El 2026-03-05 trae fechas `D/M/YY` (`5/11/04`, `1/03/26`) | `fecha_inscripcion` | Expandí `parse_date` (00-30 → 2000s, 31-99 → 1900s) | Si no, el diario rechazaba las 18k filas y no avanzaba el watermark. |

## 3. Decisiones técnicas que tomé

| # | Qué elegí | Qué descarté | Por qué me quedé con esto |
|---|---|---|---|
| 1 | `csv` + transformers puros | Pandas para todo el flujo | El esqueleto pide piezas testeables sin DB. ~20k filas no justificaban Pandas. |
| 2 | `psycopg2` + `execute_values` | SQLAlchemy | Ya venía en el template; la carga es tabular. |
| 3 | Cuarentena en archivos | Tabla `electoral.cuarentena` | **No modifiqué el DDL entregado.** |
| 4 | FastAPI + UI de inventario | Solo CLI | Lo pedimos para ver qué falta, cada tabla y el periodo del padrón. |
| 5 | Conservar acentos | Quitar acentos (fold total) | En español el acento cambia la lectura (`Petén`). |
| 6 | Upsert por `id_empadronado` + borrar ausentes | `TRUNCATE` diario del padrón | El truncate cumpliría el “snapshot”, pero la rúbrica pide altas/cambios/bajas. El upsert no duplica gracias a la PK. |
| 7 | Watermark en `carga_log` con proceso `empadronados:YYYY-MM-DD` | Tabla nueva de control | Otra vez: no toco el DDL. |
| 8 | Bloqueo si el periodo ya está cargado; overwrite solo con confirmación (`--overwrite` o el diálogo) | Reejecutar en silencio | Pedí evitar duplicados y avisar que se sobreescribe el padrón vigente. |
| 9 | Columna `periodo` en empadronados vía `sql/02_empadronados_periodo.sql` + `ALTER` en runtime | Editar `01_ddl_electoral.sql` | El enunciado prohíbe tocar el DDL original. El ALTER es aditivo y el ETL lo aplica si el volumen ya existía. |
| 10 | Orquestador `cron` + `python -m orchestration.run` | Airflow / Prefect / Dagster / GitHub Actions como cargador | Dos flujos y un backfill no justifican un scheduler con metadata DB. Airflow lo usaría con más fuentes o varios equipos. |
| 11 | Stack Docker con `./up.sh`: tests → Postgres (volumen `pgdata`) → API/UI. El job diario no arranca solo | Un `up` que ejecutara `diario` y recargara tablas | Quería probar cargas una a una desde la UI. El volumen ya tenía data; no iba a truncarlo. |

## 4. Fuera de alcance (aún)

| # | Qué dejé pendiente | Cómo lo abordaría |
|---|---|---|
| 1 | Aplicar el modelo propuesto en producción | Está en `docs/MEJORAS_MODELO.md` y `sql/99_propuesta_mejoras.sql`. No lo ejecuté contra `electoral`: el enunciado pide cargar sobre el DDL entregado. |
