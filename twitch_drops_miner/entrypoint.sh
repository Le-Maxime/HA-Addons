#!/bin/sh

# Запуск Nginx в фоновом режиме
echo "Starting Nginx reverse proxy..."
nginx -g "daemon on;"

# Запуск оригинальной точки входа с передачей аргументов
echo "Starting Twitch Drops Miner..."
exec /entrypoint-webui.sh "$@"
