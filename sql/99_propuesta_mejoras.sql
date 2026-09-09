-- Propuesta de modelo (NO es el de producción).
-- Docker Compose solo monta 01_ddl y 02_empadronados_periodo en initdb.
-- Este script crea un esquema paralelo; no toca electoral.

CREATE SCHEMA IF NOT EXISTS electoral_propuesto;
SET search_path TO electoral_propuesto, public;

CREATE TABLE departamento (
    codigo_departamento SMALLINT PRIMARY KEY,
    nombre              VARCHAR(255) NOT NULL
);

CREATE TABLE municipio (
    codigo_municipio     INTEGER PRIMARY KEY,
    codigo_departamento  SMALLINT NOT NULL REFERENCES departamento (codigo_departamento),
    nombre               VARCHAR(255) NOT NULL
);

CREATE TABLE centro_votacion (
    codigo_centro        VARCHAR(50) PRIMARY KEY,
    codigo_municipio     INTEGER NOT NULL REFERENCES municipio (codigo_municipio),
    nombre_centro        VARCHAR(255) NOT NULL,
    direccion            VARCHAR(255),
    zona                 VARCHAR(50),
    area                 VARCHAR(20) CHECK (area IN ('urbana', 'rural', 'desconocido')),
    latitud              NUMERIC(9, 6),
    longitud             NUMERIC(9, 6),
    capacidad_maxima     INTEGER
);

CREATE TABLE centro_vigencia (
    codigo_centro        VARCHAR(50) NOT NULL REFERENCES centro_votacion (codigo_centro),
    valid_from           DATE NOT NULL,
    valid_to             DATE,
    cantidad_mesas       INTEGER,
    anio_eleccion        SMALLINT,
    PRIMARY KEY (codigo_centro, valid_from)
);

CREATE TABLE mesa_votacion (
    codigo_mesa          VARCHAR(50) PRIMARY KEY,
    codigo_centro        VARCHAR(50) NOT NULL REFERENCES centro_votacion (codigo_centro),
    numero_mesa          SMALLINT NOT NULL,
    UNIQUE (codigo_centro, numero_mesa)
);

CREATE TABLE eleccion (
    id_eleccion          SERIAL PRIMARY KEY,
    anio                 SMALLINT NOT NULL,
    tipo                 VARCHAR(50) NOT NULL,
    vuelta               VARCHAR(10) NOT NULL DEFAULT 'NA',
    UNIQUE (anio, tipo, vuelta)
);

CREATE TABLE partido (
    codigo_partido       VARCHAR(50) PRIMARY KEY,
    nombre               VARCHAR(255) NOT NULL
);

CREATE TABLE candidatura (
    id_candidatura       SERIAL PRIMARY KEY,
    id_eleccion          INTEGER NOT NULL REFERENCES eleccion (id_eleccion),
    codigo_partido       VARCHAR(50) NOT NULL REFERENCES partido (codigo_partido),
    candidato            VARCHAR(255),
    UNIQUE (id_eleccion, codigo_partido)
);

CREATE TABLE etl_run (
    id_run               BIGSERIAL PRIMARY KEY,
    proceso              VARCHAR(100) NOT NULL,
    fuente               VARCHAR(255),
    started_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at          TIMESTAMPTZ,
    estado               VARCHAR(20) NOT NULL CHECK (estado IN ('ok', 'fallido', 'parcial')),
    leidos               INTEGER,
    cargados             INTEGER,
    rechazados           INTEGER
);

CREATE TABLE fact_resultado_mesa (
    id_fact_mesa         BIGSERIAL PRIMARY KEY,
    id_eleccion          INTEGER NOT NULL REFERENCES eleccion (id_eleccion),
    codigo_mesa          VARCHAR(50) NOT NULL REFERENCES mesa_votacion (codigo_mesa),
    empadronados         INTEGER NOT NULL CHECK (empadronados >= 0),
    votantes             INTEGER NOT NULL CHECK (votantes >= 0),
    votos_nulos          INTEGER NOT NULL CHECK (votos_nulos >= 0),
    votos_blanco         INTEGER NOT NULL CHECK (votos_blanco >= 0),
    id_run               BIGINT REFERENCES etl_run (id_run),
    UNIQUE (id_eleccion, codigo_mesa),
    CHECK (votantes <= empadronados)
);

CREATE TABLE fact_voto_partido (
    id_fact_voto         BIGSERIAL PRIMARY KEY,
    id_fact_mesa         BIGINT NOT NULL REFERENCES fact_resultado_mesa (id_fact_mesa),
    id_candidatura       INTEGER NOT NULL REFERENCES candidatura (id_candidatura),
    votos_validos        INTEGER NOT NULL CHECK (votos_validos >= 0),
    UNIQUE (id_fact_mesa, id_candidatura)
);

CREATE TABLE persona (
    id_empadronado       VARCHAR(50) PRIMARY KEY,
    sexo                 VARCHAR(20),
    rango_edad           VARCHAR(20),
    fecha_inscripcion    DATE
);

CREATE TABLE asignacion_padron (
    id_asignacion        BIGSERIAL PRIMARY KEY,
    id_empadronado       VARCHAR(50) NOT NULL REFERENCES persona (id_empadronado),
    codigo_mesa          VARCHAR(50) NOT NULL REFERENCES mesa_votacion (codigo_mesa),
    codigo_municipio_residencia INTEGER REFERENCES municipio (codigo_municipio),
    estado_registro      VARCHAR(20) NOT NULL CHECK (estado_registro IN ('activo', 'suspendido', 'fallecido')),
    valid_from           DATE NOT NULL,
    valid_to             DATE,
    is_current           BOOLEAN NOT NULL DEFAULT TRUE,
    id_run               BIGINT REFERENCES etl_run (id_run)
);

CREATE UNIQUE INDEX uq_asignacion_current
    ON asignacion_padron (id_empadronado)
    WHERE is_current;

CREATE INDEX ix_asignacion_periodo ON asignacion_padron (valid_from, valid_to);
CREATE INDEX ix_fact_mesa_eleccion ON fact_resultado_mesa (id_eleccion);
CREATE INDEX ix_centro_municipio ON centro_votacion (codigo_municipio);
