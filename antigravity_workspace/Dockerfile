ARG BUILD_FROM=debian:bookworm-slim
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 \
    DEBIAN_FRONTEND=noninteractive

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    nano \
    jq \
    tmux \
    ca-certificates \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
RUN set -x && \
    ARCH="x86_64" && \
    if [ "$TARGETARCH" = "arm64" ]; then ARCH="aarch64"; fi && \
    curl -fsSL -o /usr/local/bin/ttyd "https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.${ARCH}" && \
    chmod +x /usr/local/bin/ttyd

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    telethon \
    pyrogram \
    tgcrypto \
    requests \
    aiohttp \
    pandas \
    beautifulsoup4 \
    python-dotenv

RUN HOME=/root curl -fsSL https://antigravity.google/cli/install.sh | bash || true
RUN if [ -f /root/.local/bin/agy ]; then cp /root/.local/bin/agy /usr/local/bin/agy && chmod +x /usr/local/bin/agy; fi

COPY run.sh /run.sh
RUN chmod +x /run.sh

WORKDIR /data

CMD [ "/run.sh" ]
