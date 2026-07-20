#!/bin/sh
# Точка входа контейнера: PID 1 = python, чтобы SIGTERM доходил до сервиса
# и срабатывал graceful-дренаж (gRPC stop + broker drain). Аргументы образа
# (по умолчанию `serve`) передаются в Typer CLI без изменений.
set -eu

exec python -m embedding_service "$@"
