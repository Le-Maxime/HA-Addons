ARG BUILD_FROM=dungfu/twitch-drops-miner:latest
FROM ${BUILD_FROM}

USER root

# Устанавливаем Nginx и создаем директорию для PID-файла
RUN apk add --no-cache nginx && \
    mkdir -p /run/nginx

# Копируем конфигурацию Nginx и новый скрипт точки входа
COPY nginx.conf /etc/nginx/nginx.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Запускаем веб-интерфейс на порту 5801 (Nginx будет проксировать с 5800 на 5801)
ENV WEBUI_PORT=5801

ENTRYPOINT ["/entrypoint.sh"]
CMD ["--0utput", "/config/twitch_drops_miner"]