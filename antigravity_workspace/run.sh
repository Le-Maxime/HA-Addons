#!/bin/bash
set -e

echo "[$(date +'%Y-%m-%d %H:%M:%S')] [Antigravity] Starting Antigravity Agent Workspace..."

export HOME=/data
mkdir -p /data/.local/bin /data/.gemini /data/workspace /data/telegram_sessions /share/antigravity_projects

export PATH="/usr/local/bin:/opt/venv/bin:/data/.local/bin:/root/.local/bin:$PATH"

if ! command -v agy &> /dev/null; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [Antigravity] CLI not found in PATH, installing..."
    curl -fsSL https://antigravity.google/cli/install.sh | bash || true
    if [ -f "$HOME/.local/bin/agy" ]; then
        cp "$HOME/.local/bin/agy" /usr/local/bin/agy 2>/dev/null || true
    fi
fi

echo "[$(date +'%Y-%m-%d %H:%M:%S')] [Antigravity] Python venv active with: Telethon, Pyrogram, Pandas, Requests, Aiohttp"
echo "[$(date +'%Y-%m-%d %H:%M:%S')] [Antigravity] Workspace directory: /data/workspace (and /share/antigravity_projects)"
echo "[$(date +'%Y-%m-%d %H:%M:%S')] [Antigravity] Starting writable ttyd with tmux on port 7681 (session 'antigravity')..."

exec ttyd -W -p 7681 \
    -t fontSize=15 \
    -t theme='{"background": "#1e1e2e", "foreground": "#cdd6f4", "cursor": "#f5e0dc"}' \
    tmux new -A -s antigravity -c /data/workspace bash
