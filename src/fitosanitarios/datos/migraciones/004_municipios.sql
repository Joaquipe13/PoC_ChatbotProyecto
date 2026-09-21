-- Municipios y comunas de cada provincia (catálogo de nombres, sin geometría ni
-- normativa): permite reconocer una localidad de Santa Fe aunque no tenga
-- ordenanzas cargadas y basarse entonces en la normativa provincial, sin
-- preguntar la provincia. Fuente: Georef (datos.gob.ar), ver
-- data/referencia/municipios-santa-fe.csv y insumos/loader_municipios.py.
--
-- `provincia` es el nombre de carpeta (igual a territorio.provincia.nombre) y
-- NO una FK: la carga de insumos borra y recrea territorio.provincia, y este
-- catálogo tiene que sobrevivir a eso.

CREATE TABLE IF NOT EXISTS territorio.municipio (
    id BIGSERIAL PRIMARY KEY,
    provincia TEXT NOT NULL,   -- ej. "santa-fe"
    nombre TEXT NOT NULL,      -- ej. "María Susana"
    categoria TEXT NOT NULL,   -- "Municipio" | "Comuna"
    UNIQUE (provincia, nombre)
);
