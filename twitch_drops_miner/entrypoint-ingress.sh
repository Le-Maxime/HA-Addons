#!/bin/sh

# Запуск Nginx в фоновом режиме
echo "Starting Nginx reverse proxy..."
nginx -g "daemon on;"

# Запуск оригинальной точки входа (которая находится на пути /entrypoint.sh в базовом образе)
echo "Starting Twitch Drops Miner..."
exec /entrypoint.sh "$@"
