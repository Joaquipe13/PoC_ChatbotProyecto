#!/usr/bin/env bash
# Prepara una máquina de Google Colab (o cualquier Debian/Ubuntu con root) para correr el
# bot sin Docker: Postgres 16 + pgvector, la base restaurada desde el dump publicado en el
# Release de GitHub y las dependencias de Python. Se corre desde la raíz del repo.
#
# Es idempotente: si Postgres ya está instalado o la base ya está cargada, lo saltea
# (volver a correr la celda de preparación en la misma sesión de Colab tarda segundos).
#
# Variables opcionales:
#   DUMP_URL   de dónde bajar el dump (default: el Release `datos-v1` del repo).
#   DUMP_FILE  un dump ya descargado; si existe, no se baja nada.
set -euo pipefail

PG=16
DB=fitosanitarios
DUMP_URL="${DUMP_URL:-https://github.com/Joaquipe13/PoC_ChatbotProyecto/releases/download/datos-v1/fitosanitarios.dump}"
DUMP_FILE="${DUMP_FILE:-/tmp/fitosanitarios.dump}"
export DEBIAN_FRONTEND=noninteractive

paso() { echo; echo "==> $* ($(date +%T))"; }

como_postgres() { su postgres -c "$*"; }

if [ ! -x "/usr/lib/postgresql/$PG/bin/postgres" ]; then
  paso "Instalando Postgres $PG + pgvector"
  apt-get -qq update
  apt-get -qq install -y curl ca-certificates gnupg lsb-release >/dev/null
  install -d /usr/share/postgresql-common/pgdg
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc]" \
    "https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
  apt-get -qq update
  apt-get -qq install -y "postgresql-$PG" "postgresql-$PG-pgvector" >/dev/null
fi

paso "Levantando Postgres"
pg_ctlcluster "$PG" main start 2>/dev/null || true
PUERTO=$(pg_lsclusters -h | awk -v v="$PG" '$1==v && $2=="main" {print $3}')
como_postgres "psql -q -p $PUERTO -c \"ALTER USER postgres PASSWORD 'postgres'\""

# La marca se escribe solo si el restore terminó entero: uno cortado a la mitad se rehace.
MARCA=/var/lib/postgresql/.fitosanitarios_restaurada
if [ ! -f "$MARCA" ]; then
  if [ ! -s "$DUMP_FILE" ]; then
    paso "Bajando el dump de la base"
    curl -fL --retry 3 -o "$DUMP_FILE" "$DUMP_URL"
  fi
  paso "Restaurando la base (reconstruye los índices vectoriales, tarda unos minutos)"
  como_postgres "dropdb -p $PUERTO --if-exists $DB && createdb -p $PUERTO $DB"
  chmod a+r "$DUMP_FILE" 2>/dev/null || true  # pg_restore corre como el usuario postgres
  # Índices HNSW sin workers paralelos: en paralelo se arman en memoria compartida
  # (/dev/shm), que en contenedores suele ser chica y hace fallar el CREATE INDEX.
  como_postgres "PGOPTIONS='-c maintenance_work_mem=1GB -c max_parallel_maintenance_workers=0' pg_restore -p $PUERTO -d $DB --no-owner --exit-on-error -j 2 $DUMP_FILE"
  como_postgres "psql -q -p $PUERTO -d $DB -c 'ANALYZE'"
  touch "$MARCA"
fi

paso "Instalando dependencias de Python"
pip install -q -e .

# Sin .env propio: la configuración de la máquina va acá y las API keys las pone la
# notebook como variables de entorno (desde los Secrets de Colab), nunca en disco.
cat > .env <<EOF
DATABASE_URL=postgresql://postgres:postgres@localhost:$PUERTO/$DB
USE_FIXTURES=false
EOF

paso "Listo: $(como_postgres "psql -p $PUERTO -d $DB -Atc 'SELECT count(*) FROM catalogo.producto'") productos de SENASA en la base"
