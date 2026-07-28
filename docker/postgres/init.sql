-- Отдельная база и роль на каждый сервис: общий инстанс Postgres, но
-- изолированные схемы и права. База catalog создаётся самим образом из
-- POSTGRES_DB/POSTGRES_USER, здесь добавляются остальные.
CREATE ROLE indexing WITH LOGIN PASSWORD 'indexing';
CREATE DATABASE indexing OWNER indexing;

CREATE ROLE research_agent WITH LOGIN PASSWORD 'research_agent';
CREATE DATABASE research_agent OWNER research_agent;
