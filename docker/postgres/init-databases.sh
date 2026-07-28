#!/bin/sh
# Создаёт роль и базу каждому сервису: общий инстанс, изолированные схемы и
# права. Ни одна сервисная роль не является суперпользователем кластера.
#
# Скрипт, а не .sql: файлы .sql psql выполняет без подстановки переменных, а
# пароли обязаны приходить из окружения. Подставляет их сам psql — :'...' для
# литерала и :"..." для идентификатора, поэтому экранирование не на нас.
set -eu

: "${CATALOG_DB_PASSWORD:?переменная не задана}"
: "${INDEXING_DB_PASSWORD:?переменная не задана}"
: "${RESEARCH_AGENT_DB_PASSWORD:?переменная не задана}"

create_service_database() {
psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "${POSTGRES_DB:-$POSTGRES_USER}" \
  -v role="$1" \
  -v password="$2" <<'SQL'
CREATE ROLE :"role" WITH LOGIN PASSWORD :'password';
CREATE DATABASE :"role" OWNER :"role";
SQL
}

create_service_database catalog "$CATALOG_DB_PASSWORD"
create_service_database indexing "$INDEXING_DB_PASSWORD"
create_service_database research_agent "$RESEARCH_AGENT_DB_PASSWORD"
