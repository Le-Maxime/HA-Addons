#!/usr/bin/env python3
import asyncio
import os
import json
import logging
import re
import html
import sys
import glob
import subprocess
import traceback
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
                        raw_text = (message.get("text") or message.get("caption") or "").strip()
                        if not raw_text:
                            continue

                        if allowed_chat_ids and chat_id not in allowed_chat_ids:
                            logger.warning(f"Unauthorized access attempt from chat_id {chat_id}")
                            continue

                        # Preserve forwarded origin metadata if user forwards a message to the bot
                        fwd_prefix = ""
                        fwd_origin = message.get("forward_origin")
                        if fwd_origin:
                            origin_chat = fwd_origin.get("chat") or fwd_origin.get("sender_user") or {}
                            origin_name = origin_chat.get("title") or origin_chat.get("first_name") or fwd_origin.get("sender_user_name") or ""
                            if origin_name:
                                fwd_prefix = f"[Переслано из: {origin_name}]\n"
                        elif message.get("forward_from_chat") or message.get("forward_from"):
                            fc = message.get("forward_from_chat") or message.get("forward_from") or {}
                            origin_name = fc.get("title") or fc.get("first_name") or ""
                            if origin_name:
                                fwd_prefix = f"[Переслано из: {origin_name}]\n"

                        text = f"{fwd_prefix}{raw_text}" if fwd_prefix and not raw_text.startswith("/") else raw_text
                        logger.info(f"Received message from {chat_id}: {raw_text[:50]}...")

                        if raw_text in ["/start", "/help"]:
                            welcome = (
                                "🤖 <b>Antigravity AI Agent</b> подключен!\n\n"
                                "🧠 <b>Память диалога:</b> включена (агент помнит контекст всей беседы).\n"
                                "💬 <b>Чтение Telegram-чатов:</b> инструмент <code>tg-read</code> подключён.\n\n"
                                "<b>Команды:</b>\n"
                                "• <code>/new</code> или <code>/clear</code> — сбросить контекст и начать новую тему\n"
                                "• Любое сообщение или пересланный пост — задача для агента."
                            )
                            await send_tg_message(http_session, bot_token, chat_id, welcome, parse_mode="HTML")
                            continue

                        if raw_text.lower() in ["/new", "/clear", "/reset"]:
                            if os.path.exists(SESSION_FLAG):
                                try:
                                    os.remove(SESSION_FLAG)
                                except Exception:
                                    pass
                            clean_stale_locks()
                            await send_tg_message(http_session, bot_token, chat_id, "🧹 <b>Память диалога очищена!</b> Следующее сообщение начнет тему с чистого листа.", parse_mode="HTML")
                            continue

                        # Temporary status indicator
                        status_resp = await send_tg_message(http_session, bot_token, chat_id, "⏳ <i>Агент выполняет задачу...</i>", parse_mode="HTML")
                        status_msg_id = status_resp.get("result", {}).get("message_id") if status_resp else None

                        is_active = os.path.exists(SESSION_FLAG)
                        output, success = await run_antigravity(text, continue_session=is_active)

                        if success and not is_active:
                            with open(SESSION_FLAG, "w") as f:
                                f.write("1")

                        # Remove the temporary status message
                        await delete_tg_message(http_session, bot_token, chat_id, status_msg_id)

                        # Send formatted smart reply
                        await send_smart_reply(http_session, bot_token, chat_id, output)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in update polling loop: {e}\n{traceback.format_exc()}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
