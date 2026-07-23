"""Custom Telegram Notifier for Free Games Claimer Remaster.

Provides clean, beautifully formatted Russian notifications with HTML support,
store icons, status badges, and photo attachments via Telegram Bot API.
"""

from __future__ import annotations

import logging
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
    "manual login required": "🔑 Требуется вход (VNC)",
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

def format_html_telegram(message: str, title: str | None = None) -> str:
    """Format standard claimer text into rich Telegram HTML."""
    lines = message.split("\n")
    formatted_lines = []

    # Header
    main_title = title or "Free Games Claimer"
    formatted_lines.append(f"🎮 <b>{main_title}</b>\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
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
