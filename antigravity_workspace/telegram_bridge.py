#!/usr/bin/env python3
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import os
import json
import logging
import re
import html
import sys
import glob
import subprocess
import traceback
from typing import Awaitable, Callable
import aiohttp

# Force unbuffered output so logs appear instantly
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True
)
logger = logging.getLogger("telegram_bridge")

CONFIG_PATH = "/share/antigravity_projects/config.json"
WORKSPACE_DIR = "/data/workspace"
SESSION_FLAG = "/data/.session_active"
TEXT_DEBOUNCE_SEC = 1.0
FORWARD_DEBOUNCE_SEC = 2.5
MAX_BATCH_WAIT_SEC = 10.0

def load_config():
    default_config = {
        "bot_token": "",
        "allowed_chat_ids": [],
        "tg_api_id": "",
        "tg_api_hash": ""
    }
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {CONFIG_PATH}: {e}")
        return default_config

def ensure_tg_tools_integrated():
    """Creates global tg-read / tg-login wrappers and updates AGENTS.md for agy."""
    reader_candidates = [
        "/share/antigravity_projects/tg_reader.py",
        "/data/scripts/tg_reader.py"
    ]
    reader_path = next((p for p in reader_candidates if os.path.exists(p)), None)
    if not reader_path:
        return

    try:
        with open("/usr/local/bin/tg-read", "w", encoding="utf-8") as f:
            f.write(f"#!/bin/bash\nexec /opt/venv/bin/python {reader_path} \"$@\"\n")
        os.chmod("/usr/local/bin/tg-read", 0o755)

        with open("/usr/local/bin/tg-login", "w", encoding="utf-8") as f:
            f.write(f"#!/bin/bash\nexec /opt/venv/bin/python {reader_path} login \"$@\"\n")
        os.chmod("/usr/local/bin/tg-login", 0o755)
        logger.info(f"Installed tg-read & tg-login wrappers -> {reader_path}")
    except Exception as e:
        logger.warning(f"Failed to install tg-read wrappers: {e}")

    begin_marker = "<!-- BEGIN ANTIGRAVITY TG_READER -->"
    end_marker = "<!-- END ANTIGRAVITY TG_READER -->"
    managed_block = f"""{begin_marker}
## Доступ к Telegram-перепискам пользователя (`tg-read`)
У тебя есть встроенный CLI-инструмент `tg-read` (Telethon UserBot, только чтение) для анализа личных переписок, групп и каналов пользователя.
Когда пользователь просит прочитать, найти, пересказать или проанализировать сообщения/чаты/каналы в Telegram — вызывай `tg-read` через bash:
- `tg-read status` — проверить статус авторизации UserBot
- `tg-read dialogs --limit 30 [--query "текст"] [--type user|group|supergroup|channel]` — список диалогов (ID, название, @username)
- `tg-read history "<ID, @username или часть названия>" --limit 50 [--days 7] [--search "слово"]` — история сообщений в хронологическом порядке (поддерживает `"me"` / `"избранное"`)
- `tg-read search "<запрос>" --limit 30 [--days 7]` — глобальный поиск по всем чатам

Правила:
- Если `tg-read` сообщает, что сессия не авторизована, скажи пользователю открыть вкладку **Antigravity** в боковом меню Home Assistant и один раз выполнить в терминале команду `tg-login` (ввести телефон и код из Telegram).
- Если имя чата неоднозначно или не найдено, сначала выполни `tg-read dialogs --query "..."`, чтобы увидеть точный ID и название.
{end_marker}"""

    for agents_path in ["/data/workspace/AGENTS.md", "/data/.gemini/AGENTS.md"]:
        try:
            os.makedirs(os.path.dirname(agents_path), exist_ok=True)
            existing = ""
            if os.path.exists(agents_path):
                with open(agents_path, "r", encoding="utf-8") as f:
                    existing = f.read()
            if begin_marker in existing and end_marker in existing:
                pattern = re.escape(begin_marker) + r".*?" + re.escape(end_marker)
                updated = re.sub(pattern, lambda _: managed_block, existing, flags=re.DOTALL)
            else:
                sep = "\n\n" if existing.strip() else ""
                updated = existing.rstrip() + sep + managed_block + "\n"
            with open(agents_path, "w", encoding="utf-8") as f:
                f.write(updated)
        except Exception as e:
            logger.warning(f"Failed updating {agents_path}: {e}")

def clean_stale_locks():
    """Removes stale lock files if a previous process was abruptly killed."""
    try:
        patterns = ["/data/**/.lock", "/data/**/*.lock", "/data/.gemini/**/*.lock"]
        for p in patterns:
            for lock in glob.glob(p, recursive=True):
                logger.warning(f"Removing stale lock file: {lock}")
                try:
                    os.remove(lock)
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Error scanning lock files: {e}")

def _format_blockquote(match: re.Match) -> str:
    """Converts consecutive escaped blockquote lines into a Telegram <blockquote>."""
    block = match.group(0)
    trailing_nl = "\n" if block.endswith("\n") else ""
    lines = [re.sub(r"^&gt;\s?", "", line) for line in block.rstrip("\n").split("\n")]
    return "<blockquote>" + "\n".join(lines) + "</blockquote>" + trailing_nl


def _format_header(match: re.Match) -> str:
    """Formats Markdown headings as bold without duplicating outer <b> tags."""
    content = match.group(1).strip()
    if (
        content.startswith("<b>")
        and content.endswith("</b>")
        and "<b>" not in content[3:-4]
        and "</b>" not in content[3:-4]
    ):
        return content
    return f"<b>{content}</b>"


def _apply_inline_formatting(text: str) -> str:
    """Applies Markdown bold, strikethrough, and italic emphasis to escaped text."""
    text = re.sub(r"\*\*(?!\s)([^\n]+?)(?<!\s)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\w)__(?!\s)([^_\n]+?)(?<!\s)__(?!\w)", r"<b>\1</b>", text)
    text = re.sub(r"~~(?!\s)([^\n]+?)(?<!\s)~~", r"<s>\1</s>", text)
    text = re.sub(r"(?<!\w)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(?!\s)([^_\n]+?)(?<!\s)_(?!\w)", r"<i>\1</i>", text)
    return text


def markdown_to_telegram_html(text: str) -> str:
    """Converts standard Markdown into clean, Telegram-compatible HTML."""
    if not text:
        return ""

    # Strip NUL bytes so sentinel tokens cannot collide with input text
    text = text.replace("\x00", "")
    placeholders: list[tuple[str, str]] = []

    def reserve(prefix: str, rendered: str) -> str:
        token = f"\x00{prefix}{len(placeholders)}\x00"
        placeholders.append((token, rendered))
        return token

    # 1. Protect and format fenced code blocks: ```lang\ncode``` and ```code```
    def save_code_block(match: re.Match) -> str:
        lang = (match.group(1) or "").strip() if match.lastindex and match.lastindex >= 2 else ""
        code = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)
        escaped_code = html.escape(code.strip("\r\n"), quote=False)
        if lang:
            tag = f'<pre><code class="language-{html.escape(lang, quote=True)}">{escaped_code}</code></pre>'
        else:
            tag = f"<pre>{escaped_code}</pre>"
        return reserve("CB", tag)

    text = re.sub(r"```(?:([a-zA-Z0-9_+#.-]+)[ \t]*)?\r?\n(.*?)```", save_code_block, text, flags=re.DOTALL)
    text = re.sub(r"```([^`\n]+?)```", save_code_block, text)

    # 2. Protect and format inline code: ``code`` and `code`
    def save_inline_code(match: re.Match) -> str:
        escaped_code = html.escape(match.group(1), quote=False)
        return reserve("IC", f"<code>{escaped_code}</code>")

    text = re.sub(r"(?<!`)``(?!`)([^\n]+?)``(?!`)", save_inline_code, text)
    text = re.sub(r"`([^`\n]+?)`", save_inline_code, text)

    # 3. Escape HTML entities for remaining plain text
    text = html.escape(text, quote=False)

    # 4. Protect Markdown links [label](https://...) before inline emphasis rules
    def save_link(match: re.Match) -> str:
        label = _apply_inline_formatting(match.group(1))
        url = match.group(2).replace('"', "%22")
        return reserve("LK", f'<a href="{url}">{label}</a>')

    text = re.sub(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)", save_link, text)

    # 5. Block-level elements (horizontal rules, bullets, blockquotes)
    text = re.sub(r"^[ \t]*[-*_]{3,}[ \t]*$", "──────────", text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*[\*\-]\s+", "• ", text, flags=re.MULTILINE)
    text = re.sub(r"(?:^&gt;\s?.*(?:\n|$))+", _format_blockquote, text, flags=re.MULTILINE)

    # 6. Inline emphasis (never touches underscore/asterisk-free \x00 placeholders)
    text = _apply_inline_formatting(text)

    # 7. Headings (# Header .. ###### Header)
    text = re.sub(r"^[ \t]*#{1,6}\s+(.+)$", _format_header, text, flags=re.MULTILINE)

    # 8. Restore reserved code blocks, inline code, and links (reverse order handles nested tokens cleanly)
    for token, rendered in reversed(placeholders):
        text = text.replace(token, rendered)

    return text


def split_markdown_chunks(text: str, max_chars: int = 3000) -> list[str]:
    """Splits Markdown into chunks on line boundaries while keeping fenced code blocks intact."""
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0
    open_fence = ""

    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        line_len = len(line)

        if current_lines and current_len + line_len > max_chars:
            if open_fence:
                current_lines.append("\n```\n" if not current_lines[-1].endswith("\n") else "```\n")
            chunks.append("".join(current_lines).rstrip("\n"))
            current_lines = [open_fence + "\n"] if open_fence else []
            current_len = len(current_lines[0]) if current_lines else 0

        current_lines.append(line)
        current_len += line_len

        if stripped.startswith("```"):
            open_fence = "" if open_fence else stripped.rstrip("\r\n")

    if current_lines:
        chunks.append("".join(current_lines).rstrip("\n"))

    return [c for c in chunks if c]

async def run_antigravity(prompt: str, continue_session: bool) -> tuple[str, bool]:
    # Proper flag order: options first, -p <prompt> last
    cmd = ["agy", "--dangerously-skip-permissions", "--print-timeout", "120s"]
    if continue_session:
        cmd.append("-c")
    cmd.extend(["-p", prompt])

    logger.info(f"Executing Antigravity: agy (continue={continue_session}) prompt={prompt[:40]}...")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=WORKSPACE_DIR,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Outer timeout safety guard (130s)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=130.0)
        except asyncio.CancelledError:
            logger.info("Antigravity execution cancelled; terminating child process...")
            try:
                process.kill()
                await process.wait()
            except Exception as pe:
                logger.error(f"Error killing cancelled process: {pe}")
            raise
        except asyncio.TimeoutError:
            logger.error("Antigravity process timed out after 130s! Terminating...")
            try:
                process.kill()
                await process.wait()
            except Exception as pe:
                logger.error(f"Error killing timed out process: {pe}")
            return "⏱️ Превышено время ожидания ответа агента (2 мин). Возможно, задача слишком сложная. Попробуйте разбить запрос или начать с /new.", False

        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        logger.info(f"Antigravity finished with code {process.returncode}. Output: {len(out)} chars, Stderr: {len(err)} chars")
        if err:
            logger.info(f"Antigravity stderr: {err[:200]}")

        # If previous session context failed or was broken, retry with fresh session
        if process.returncode != 0 and continue_session:
            err_lower = err.lower()
            if any(k in err_lower for k in ["no conversation", "not found", "not active", "corrupt", "failed to resume"]):
                logger.warning("Session failed with -c, falling back to clean session...")
                return await run_antigravity(prompt, continue_session=False)

        if process.returncode != 0 and not out:
            return f"⚠️ Ошибка выполнения:\n{err}", False

        return out if out else "✅ Задача выполнена (без текстового вывода).", True

    except Exception as e:
        logger.error(f"Exception during run_antigravity: {e}\n{traceback.format_exc()}")
        return f"⚠️ Системная ошибка: {e}", False

async def send_tg_message(session, bot_token, chat_id, text, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()
            if not data.get("ok"):
                logger.warning(f"Telegram API warning: {data.get('description')}")
                if parse_mode:
                    logger.warning(f"Retrying plain text without {parse_mode}...")
                    payload.pop("parse_mode", None)
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as fallback_resp:
                        return await fallback_resp.json()
            return data
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {e}")
        return None

async def send_smart_reply(session, bot_token, chat_id, raw_text):
    formatted = markdown_to_telegram_html(raw_text)

    # Standard length: <= 4000 characters
    if len(formatted) <= 4000:
        res = await send_tg_message(session, bot_token, chat_id, formatted, parse_mode="HTML")
        logger.info(f"Sent reply ({len(formatted)} chars), status: ok={res.get('ok') if res else False}")
        return

    # If message is huge (>8000 chars), save and send as .md document
    if len(raw_text) > 8000:
        file_path = "/data/workspace/last_response.md"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(raw_text)
            url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
            with open(file_path, "rb") as doc_file:
                form_data = aiohttp.FormData()
                form_data.add_field("chat_id", str(chat_id))
                form_data.add_field("caption", "📄 Ответ слишком большой для одного сообщения, прикрепляю файлом:")
                form_data.add_field("document", doc_file, filename="response.md")
                async with session.post(url, data=form_data, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        logger.info("Sent reply as markdown document")
                        return
        except Exception as e:
            logger.error(f"Failed to send response as document: {e}")

    # Otherwise split Markdown on line/fence boundaries so every HTML chunk stays valid
    for md_chunk in split_markdown_chunks(raw_text, max_chars=2800):
        html_chunk = markdown_to_telegram_html(md_chunk)
        if len(html_chunk) <= 4096:
            await send_tg_message(session, bot_token, chat_id, html_chunk, parse_mode="HTML")
        else:
            for sub_chunk in split_markdown_chunks(md_chunk, max_chars=1400):
                sub_html = markdown_to_telegram_html(sub_chunk)
                if len(sub_html) <= 4096:
                    await send_tg_message(session, bot_token, chat_id, sub_html, parse_mode="HTML")
                else:
                    for i in range(0, len(sub_chunk), 3500):
                        await send_tg_message(session, bot_token, chat_id, sub_chunk[i:i+3500], parse_mode=None)
    logger.info("Sent chunked reply")

async def delete_tg_message(session, bot_token, chat_id, message_id):
    if not message_id:
        return
    try:
        url = f"https://api.telegram.org/bot{bot_token}/deleteMessage"
        async with session.post(url, json={"chat_id": chat_id, "message_id": message_id}, timeout=aiohttp.ClientTimeout(total=10)):
            pass
    except Exception:
        pass

@dataclass
class IncomingItem:
    """Normalized incoming Telegram message queued for batch processing."""

    text: str
    is_forward: bool = False
    forward_header: str = ""
    has_media_group: bool = False


@dataclass
class ChatState:
    """Per-chat debounce buffer and worker lifecycle state."""

    buffer: list[IncomingItem] = field(default_factory=list)
    last_item_at: float = 0.0
    worker_task: asyncio.Task | None = None
    generation: int = 0


def _format_user_label(user: dict) -> str:
    """Builds a readable sender display name from a Telegram user/chat object."""
    if not isinstance(user, dict):
        return ""
    title = user.get("title")
    if title:
        return str(title).strip()
    parts = [p for p in [user.get("first_name"), user.get("last_name")] if p]
    if parts:
        return " ".join(str(p).strip() for p in parts)
    username = user.get("username")
    return f"@{username}" if username else ""


def extract_forward_metadata(message: dict) -> tuple[bool, str]:
    """Extracts forwarded author/chat and timestamp metadata from a Telegram message."""
    origin_name = ""
    fwd_ts = None

    fwd_origin = message.get("forward_origin")
    if isinstance(fwd_origin, dict):
        fwd_ts = fwd_origin.get("date")
        for key in ("chat", "sender_chat", "sender_user"):
            origin_name = _format_user_label(fwd_origin.get(key))
            if origin_name:
                break
        if not origin_name:
            origin_name = str(fwd_origin.get("sender_user_name") or "").strip()
    elif any(k in message for k in ("forward_from_chat", "forward_from", "forward_sender_name", "forward_date")):
        fwd_ts = message.get("forward_date")
        origin_name = (
            _format_user_label(message.get("forward_from_chat"))
            or _format_user_label(message.get("forward_from"))
            or str(message.get("forward_sender_name") or "").strip()
        )
    else:
        return False, ""

    time_suffix = ""
    if isinstance(fwd_ts, (int, float)):
        try:
            time_suffix = f" ({datetime.fromtimestamp(fwd_ts).strftime('%H:%M:%S')})"
        except Exception:
            time_suffix = ""

    label = origin_name or "неизвестного отправителя"
    return True, f"[Переслано от {label}{time_suffix}]"


def _extract_media_placeholder(message: dict, include_sticker: bool) -> str:
    """Returns a readable fallback tag when a message has media without text/caption."""
    if message.get("photo"):
        return "[Фото]"
    if message.get("video"):
        return "[Видео]"
    if message.get("voice"):
        return "[Голосовое сообщение]"
    if message.get("audio"):
        return "[Аудио]"
    if message.get("video_note"):
        return "[Видеосообщение]"
    doc = message.get("document")
    if isinstance(doc, dict):
        fname = doc.get("file_name")
        return f"[Файл: {fname}]" if fname else "[Файл]"
    if include_sticker and isinstance(message.get("sticker"), dict):
        emoji = message["sticker"].get("emoji") or ""
        return f"[Стикер {emoji}]".strip()
    return ""


def extract_incoming_item(message: dict) -> IncomingItem | None:
    """Parses a Telegram update message into an IncomingItem, or None if unsupported."""
    is_forward, forward_header = extract_forward_metadata(message)
    raw_text = (message.get("text") or message.get("caption") or "").strip()
    if not raw_text:
        raw_text = _extract_media_placeholder(message, include_sticker=is_forward)
    if not raw_text:
        return None
    return IncomingItem(
        text=raw_text,
        is_forward=is_forward,
        forward_header=forward_header,
        has_media_group=bool(message.get("media_group_id")),
    )


def format_message_batch(items: list[IncomingItem]) -> str:
    """Combines one or more debounced messages into a clean prompt for Antigravity."""
    if len(items) == 1:
        item = items[0]
        if item.is_forward:
            return f"{item.forward_header}:\n{item.text}"
        return item.text

    has_forwards = any(it.is_forward for it in items)
    if not has_forwards:
        return "\n\n".join(it.text for it in items)

    parts = []
    for it in items:
        if it.is_forward:
            parts.append(f"{it.forward_header}:\n{it.text}")
        else:
            parts.append(f"[Комментарий/запрос пользователя]:\n{it.text}")
    return "\n\n".join(parts)


class ChatCoordinator:
    """Buffers rapid bursts and forwarded message groups per chat into a single agent run."""

    def __init__(
        self,
        handler: Callable[[int, str, int, int], Awaitable[None]],
        text_debounce: float = TEXT_DEBOUNCE_SEC,
        forward_debounce: float = FORWARD_DEBOUNCE_SEC,
        max_batch_wait: float = MAX_BATCH_WAIT_SEC,
    ):
        self._handler = handler
        self.text_debounce = text_debounce
        self.forward_debounce = forward_debounce
        self.max_batch_wait = max_batch_wait
        self._chats: dict[int, ChatState] = {}

    def get_generation(self, chat_id: int) -> int:
        """Returns the current session generation counter for a chat."""
        return self._chats.setdefault(chat_id, ChatState()).generation

    def enqueue(self, chat_id: int, item: IncomingItem) -> None:
        """Adds an incoming message to the chat buffer and starts its worker if idle."""
        loop = asyncio.get_running_loop()
        state = self._chats.setdefault(chat_id, ChatState())
        state.buffer.append(item)
        state.last_item_at = loop.time()

        if state.worker_task is None or state.worker_task.done():
            state.worker_task = asyncio.create_task(self._chat_worker(chat_id, state))

    async def reset_chat(self, chat_id: int) -> None:
        """Clears queued messages, invalidates the session generation, and stops active execution."""
        state = self._chats.setdefault(chat_id, ChatState())
        state.buffer.clear()
        state.generation += 1
        task = state.worker_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            state.worker_task = None

    async def shutdown(self) -> None:
        """Cancels all active chat workers cleanly on exit."""
        tasks = [s.worker_task for s in self._chats.values() if s.worker_task and not s.worker_task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _chat_worker(self, chat_id: int, state: ChatState) -> None:
        loop = asyncio.get_running_loop()
        while state.buffer:
            wait_started_at = loop.time()
            while True:
                if not state.buffer:
                    return
                delay = (
                    self.forward_debounce
                    if any(it.is_forward or it.has_media_group for it in state.buffer)
                    else self.text_debounce
                )
                target = min(state.last_item_at + delay, wait_started_at + self.max_batch_wait)
                remaining = target - loop.time()
                if remaining <= 0:
                    break
                await asyncio.sleep(remaining)

            if not state.buffer:
                return

            batch = state.buffer[:]
            state.buffer.clear()
            prompt = format_message_batch(batch)
            gen = state.generation
            await self._handler(chat_id, prompt, gen, len(batch))


async def main():
    logger.info("Starting Telegram Bridge (Production-grade)...")
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    clean_stale_locks()
    ensure_tg_tools_integrated()

    config = load_config()
    bot_token = config.get("bot_token", "").strip()
    allowed_chat_ids = config.get("allowed_chat_ids", [])

    if not bot_token:
        logger.warning(f"No bot_token found in {CONFIG_PATH}! Waiting...")
        while not bot_token:
            await asyncio.sleep(10)
            config = load_config()
            bot_token = config.get("bot_token", "").strip()

    logger.info(f"Using Bot Token: {bot_token[:10]}... Allowed chat IDs: {allowed_chat_ids}")

    async with aiohttp.ClientSession() as http_session:
        try:
            async with http_session.get(f"https://api.telegram.org/bot{bot_token}/getMe") as resp:
                data = await resp.json()
                if data.get("ok"):
                    bot_name = data["result"].get("username")
                    logger.info(f"Connected to Telegram as @{bot_name}!")
        except Exception as e:
            logger.error(f"Network error during getMe: {e}")

        async def handle_batched_prompt(chat_id: int, prompt: str, generation: int, count: int) -> None:
            logger.info(f"Processing batch of {count} message(s) for {chat_id} ({len(prompt)} chars)")
            status_resp = await send_tg_message(http_session, bot_token, chat_id, "⏳ <i>Агент выполняет задачу...</i>", parse_mode="HTML")
            status_msg_id = status_resp.get("result", {}).get("message_id") if status_resp else None

            try:
                is_active = os.path.exists(SESSION_FLAG)
                output, success = await run_antigravity(prompt, continue_session=is_active)

                if generation != coordinator.get_generation(chat_id):
                    logger.info(f"Discarding stale response for {chat_id} after session reset")
                    return

                if success and not is_active:
                    with open(SESSION_FLAG, "w") as f:
                        f.write("1")

                await delete_tg_message(http_session, bot_token, chat_id, status_msg_id)
                status_msg_id = None
                await send_smart_reply(http_session, bot_token, chat_id, output)
            except asyncio.CancelledError:
                await delete_tg_message(http_session, bot_token, chat_id, status_msg_id)
                raise
            except Exception as e:
                logger.error(f"Error handling batch for {chat_id}: {e}\n{traceback.format_exc()}")
                await delete_tg_message(http_session, bot_token, chat_id, status_msg_id)
                await send_tg_message(http_session, bot_token, chat_id, f"⚠️ Системная ошибка: {e}", parse_mode=None)

        coordinator = ChatCoordinator(handle_batched_prompt)

        # Start offset at latest update on boot so it does not replay stale messages
        offset = 0
        try:
            async with http_session.get(f"https://api.telegram.org/bot{bot_token}/getUpdates?offset=-1") as resp:
                data = await resp.json()
                if data.get("ok") and data.get("result"):
                    offset = data["result"][-1]["update_id"] + 1
                    logger.info(f"Initialized offset to {offset} (skipping old queued messages)")
        except Exception as e:
            logger.error(f"Error fetching initial offset: {e}")

        try:
            while True:
                try:
                    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?offset={offset}&timeout=30"
                    async with http_session.get(url, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                        if resp.status != 200:
                            await asyncio.sleep(5)
                            continue
                        updates_data = await resp.json()

                        if not updates_data.get("ok"):
                            await asyncio.sleep(5)
                            continue

                        for update in updates_data.get("result", []):
                            offset = update["update_id"] + 1
                            message = update.get("message")
                            if not message:
                                continue

                            chat_id = message["chat"]["id"]
                            if allowed_chat_ids and chat_id not in allowed_chat_ids:
                                logger.warning(f"Unauthorized access attempt from chat_id {chat_id}")
                                continue

                            item = extract_incoming_item(message)
                            if item is None:
                                continue

                            logger.info(
                                f"Received {'forwarded ' if item.is_forward else ''}message from {chat_id}: {item.text[:50]}..."
                            )

                            if not item.is_forward and item.text in ["/start", "/help"]:
                                welcome = (
                                    "🤖 <b>Antigravity AI Agent</b> подключен!\n\n"
                                    "🧠 <b>Память диалога:</b> включена (агент помнит контекст всей беседы).\n"
                                    "📦 <b>Группировка пересланных сообщений:</b> пачка пересланных сообщений объединяется в один запрос.\n"
                                    "💬 <b>Чтение Telegram-чатов:</b> инструмент <code>tg-read</code> подключён.\n\n"
                                    "<b>Команды:</b>\n"
                                    "• <code>/new</code> или <code>/clear</code> — сбросить контекст и начать новую тему\n"
                                    "• Любое сообщение или пересланный пост — задача для агента."
                                )
                                await send_tg_message(http_session, bot_token, chat_id, welcome, parse_mode="HTML")
                                continue

                            if not item.is_forward and item.text.lower() in ["/new", "/clear", "/reset"]:
                                await coordinator.reset_chat(chat_id)
                                if os.path.exists(SESSION_FLAG):
                                    try:
                                        os.remove(SESSION_FLAG)
                                    except Exception:
                                        pass
                                clean_stale_locks()
                                await send_tg_message(
                                    http_session,
                                    bot_token,
                                    chat_id,
                                    "🧹 <b>Память диалога очищена!</b> Следующее сообщение начнет тему с чистого листа.",
                                    parse_mode="HTML",
                                )
                                continue

                            coordinator.enqueue(chat_id, item)

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error in update polling loop: {e}\n{traceback.format_exc()}")
                    await asyncio.sleep(5)
        finally:
            await coordinator.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
