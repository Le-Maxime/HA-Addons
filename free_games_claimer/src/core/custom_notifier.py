"""Custom Telegram Notifier for Free Games Claimer Remaster.

Provides clean, beautifully formatted Russian notifications with HTML support,
store icons, status badges, VNC IP customization, and photo attachments.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
import httpx

from src.core.config import cfg

logger = logging.getLogger("fgc.custom_notifier")

STORE_EMOJIS = {
    "epic": "🎁 <b>Epic Games Store</b>",
    "steam": "🕹 <b>Steam</b>",
    "gog": "🎮 <b>GOG.com</b>",
    "prime": "📦 <b>Prime Gaming</b>",
    "amazon": "📦 <b>Prime Gaming</b>",
    "gamerpower": "⚡ <b>GamerPower</b>",
    "fanatical": "🔥 <b>Fanatical</b>",
    "itchio": "🎯 <b>Itch.io</b>",
    "indiegala": "🎨 <b>IndieGala</b>",
    "alienware": "👽 <b>Alienware Arena</b>",
}

STATUS_TRANSLATIONS = {
    "claimed": "✅ Забрано",
    "already claimed": "ℹ️ Уже в библиотеке",
    "failed": "❌ Ошибка получения",
    "skipped": "⏭ Пропущено",
    "manual login needed": "🔑 Требуется вход (VNC)",
}

def parse_tgram_url(url: str) -> tuple[str, str] | None:
    """Extract (token, chat_id) from Apprise url like tgram://token/chat_id."""
    if not url or not url.startswith("tgram://"):
        return None
    
    clean_url = url.replace("tgram://", "").split("?")[0]
    parts = clean_url.split("/")
    
    if len(parts) >= 2:
        token = parts[0]
        chat_id = parts[1]
        return token, chat_id
    return None

def get_vnc_host() -> str:
    """Determine the host/IP to use for VNC links."""
    # 1. Custom VNC_IP from addon options / config
    vnc_ip = (getattr(cfg, "vnc_ip", "") or "").strip()
    if vnc_ip and vnc_ip.lower() != "localhost":
        return vnc_ip
    
    # 2. Check environment variable VNC_IP / HA_HOST
    env_vnc = os.getenv("VNC_IP") or os.getenv("HA_HOST")
    if env_vnc and env_vnc.lower() != "localhost":
        return env_vnc
        
    return "192.168.1.6"

def format_vnc_login_request(message: str) -> str:
    """Format VNC login request into a clean Russian Telegram HTML message."""
    target_host = get_vnc_host()
    
    # Extract store name
    store_name = "магазине"
    for store_key, store_label in STORE_EMOJIS.items():
        if store_key in message.lower():
            store_name = store_label
            break

    # Extract or fix VNC URL
    vnc_url_match = re.search(r'https?://[^\s]+', message)
    if vnc_url_match:
        vnc_url = vnc_url_match.group(0)
        # Replace localhost/127.0.0.1 with target_host
        vnc_url = re.sub(r'://(localhost|127\.0\.0\.1)', f'://{target_host}', vnc_url)
    else:
        vnc_url = f"http://{target_host}:7080/?autoconnect=true"

    # Extract timeout
    timeout_match = re.search(r'(\d+)\s*s', message)
    timeout_str = f"{timeout_match.group(1)} сек." if timeout_match else "180 сек."

    formatted = (
        f"🔑 <b>ТРЕБУЕТСЯ ВХОД (VNC)</b>\n\n"
        f"🛒 <b>Магазин:</b> {store_name}\n"
        f"⚠️ Пожалуйста, завершите вход в аккаунт или введите 2FA-код.\n\n"
        f"🌐 <b>Ссылка для входа:</b>\n"
        f'<a href="{vnc_url}"><b>👉 Открыть VNC в браузере 👈</b></a>\n\n'
        f"⏱ <b>Время ожидания:</b> {timeout_str}"
    )
    return formatted

def format_html_telegram(message: str, title: str | None = None) -> str:
    """Format standard claimer text into rich Telegram HTML."""
    target_host = get_vnc_host()

    # Check if this is a VNC login request
    if "manual login" in message.lower() or "open vnc" in message.lower() or "finish signing in" in message.lower():
        return format_vnc_login_request(message)

    lines = message.split("\n")
    formatted_lines = []

    # Header
    main_title = title or "Free Games Claimer"
    formatted_lines.append(f"🎮 <b>{main_title}</b>\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Replace localhost with target_host in any URLs
        if "localhost" in stripped or "127.0.0.1" in stripped:
            stripped = re.sub(r'://(localhost|127\.0\.0\.1)', f'://{target_host}', stripped)
        
        # Translate statuses
        for eng, ru in STATUS_TRANSLATIONS.items():
            if eng in stripped.lower():
                stripped = re.sub(re.escape(eng), ru, stripped, flags=re.IGNORECASE)

        # Translate store titles
        for store_key, store_label in STORE_EMOJIS.items():
            if store_key in stripped.lower() and ("[" in stripped or "store" in stripped.lower()):
                stripped = re.sub(re.escape(store_key), store_label, stripped, flags=re.IGNORECASE)

        # Convert Markdown links [Title](url) to HTML <a href="url">Title</a>
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        stripped = re.sub(link_pattern, r'<a href="\2"><b>\1</b></a>', stripped)

        # Convert markdown bold **text** to HTML <b>text</b>
        stripped = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', stripped)

        # Bullet points formatting
        if stripped.startswith("•") or stripped.startswith("-") or stripped.startswith("*"):
            bullet_content = stripped.lstrip("•-* ").strip()
            formatted_lines.append(f"  🔹 {bullet_content}")
        else:
            formatted_lines.append(stripped)

    return "\n".join(formatted_lines)

async def custom_notify(
    message: str,
    *,
    screenshot_path: Path | None = None,
    title: str | None = None,
) -> bool:
    """Custom Telegram sender via Bot API.
    
    Returns True if handled successfully, False to fallback to default notifier.
    """
    notify_url = cfg.notify_url
    parsed = parse_tgram_url(notify_url)
    if not parsed:
        return False

    bot_token, chat_id = parsed
    formatted_text = format_html_telegram(message, title=title)
    
    api_url = f"https://api.telegram.org/bot{bot_token}"
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if screenshot_path and screenshot_path.exists():
                # Send Photo with caption
                url = f"{api_url}/sendPhoto"
                data = {
                    "chat_id": chat_id,
                    "caption": formatted_text[:1024],
                    "parse_mode": "HTML"
                }
                files = {"photo": (screenshot_path.name, screenshot_path.read_bytes(), "image/png")}
                resp = await client.post(url, data=data, files=files)
            else:
                # Send Text Message
                url = f"{api_url}/sendMessage"
                data = {
                    "chat_id": chat_id,
                    "text": formatted_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }
                resp = await client.post(url, json=data)

            if resp.status_code == 200:
                logger.info("Custom Telegram notification sent successfully.")
                return True
            else:
                logger.warning("Telegram Bot API returned error %s: %s", resp.status_code, resp.text)
                return False
    except Exception as e:
        logger.exception("Failed to send custom Telegram notification", exc_info=e)
        return False
