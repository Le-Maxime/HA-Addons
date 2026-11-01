ARG BUILD_FROM=dungfu/twitch-drops-miner:latest
FROM ${BUILD_FROM}

USER root

# Устанавливаем Nginx и создаем директорию для PID-файла (поддержка Alpine и Debian)
RUN if command -v apk >/dev/null 2>&1; then \
        apk add --no-cache nginx; \
    elif command -v apt-get >/dev/null 2>&1; then \
        apt-get update && apt-get install -y --no-install-recommends nginx && rm -rf /var/lib/apt/lists/*; \
    fi && \
    mkdir -p /run/nginx

# Копируем конфигурацию Nginx и новый скрипт точки входа
COPY nginx.conf /etc/nginx/nginx.conf
COPY entrypoint-ingress.sh /entrypoint-ingress.sh
RUN chmod +x /entrypoint-ingress.sh

# Запускаем веб-интерфейс на порту 5801 (Nginx будет проксировать с 5800 на 5801)
ENV WEBUI_PORT=5801

ENTRYPOINT ["/entrypoint-ingress.sh"]
CMD ["--0utput", "/config/twitch_drops_miner"]