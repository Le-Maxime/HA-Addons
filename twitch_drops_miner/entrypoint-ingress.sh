#!/bin/sh

# Определение UID/GID для прав доступа (по умолчанию 1000)
USER_ID=${USER_ID:-1000}
GROUP_ID=${GROUP_ID:-1000}

echo "Configuring persistent directories..."

# Создаем папку кэша в постоянном внутреннем хранилище /data (пользователю кэш не нужен)
mkdir -p /data/cache

# Папка /config монтируется Home Assistant автоматически через 'addon_config:rw'
# и указывает на /addon_configs/twitch_drops_miner на хосте.

# Если папки в контейнере еще не являются ссылками, переносим файлы и заменяем их ссылками
if [ -d /TwitchDropsMiner/config ] && [ ! -L /TwitchDropsMiner/config ]; then
    cp -rp /TwitchDropsMiner/config/* /config/ 2>/dev/null
    rm -rf /TwitchDropsMiner/config
fi

if [ -d /TwitchDropsMiner/cache ] && [ ! -L /TwitchDropsMiner/cache ]; then
    cp -rp /TwitchDropsMiner/cache/* /data/cache/ 2>/dev/null
    rm -rf /TwitchDropsMiner/cache
fi

# Создаем символические ссылки
if [ ! -L /TwitchDropsMiner/config ]; then
    ln -s /config /TwitchDropsMiner/config
fi

if [ ! -L /TwitchDropsMiner/cache ]; then
    ln -s /data/cache /TwitchDropsMiner/cache
fi

# Выдаем права на запись пользователю приложения для обеих папок
chown -R $USER_ID:$GROUP_ID /config /data/cache

# Запуск Nginx в фоновом режиме
echo "Starting Nginx reverse proxy..."
nginx -g "daemon on;"

# Запуск оригинальной точки входа
echo "Starting Twitch Drops Miner..."
exec /entrypoint.sh "$@"
