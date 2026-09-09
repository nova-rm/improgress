-- Extensión de la prueba: periodo de la foto del padrón.
-- No modifica sql/01_ddl_electoral.sql (modelo entregado).
-- En un volumen ya inicializado el ETL también aplica ADD COLUMN IF NOT EXISTS.

ALTER TABLE electoral.empadronados
    ADD COLUMN IF NOT EXISTS periodo VARCHAR(50);

COMMENT ON COLUMN electoral.empadronados.periodo IS
    'Fecha de la foto diaria (YYYY-MM-DD) desde la que proviene el registro vigente.';
