#!/usr/bin/env python3
"""Read-only Telegram UserBot CLI tool for Antigravity (via Telethon)."""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Channel, Chat, MessageMediaDocument, MessageMediaPhoto, User

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = os.environ.get("TG_BRIDGE_CONFIG", "/share/antigravity_projects/config.json")
SESSION_PATH = os.environ.get("TG_SESSION_PATH", "/data/telegram_sessions/user_session")


def load_credentials() -> tuple[int, str]:
    api_id = os.environ.get("TG_API_ID", "").strip()
    api_hash = os.environ.get("TG_API_HASH", "").strip()

    if (not api_id or not api_hash) and os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            api_id = str(cfg.get("tg_api_id", api_id)).strip()
            api_hash = str(cfg.get("tg_api_hash", api_hash)).strip()
        except Exception as exc:
            print(f"❌ Ошибка чтения {CONFIG_PATH}: {exc}", file=sys.stderr)
            sys.exit(1)

    if not api_id or not api_hash:
        print(
            "❌ Не заданы tg_api_id / tg_api_hash в /share/antigravity_projects/config.json.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        return int(api_id), api_hash
    except ValueError:
        print(f"❌ Некорректный tg_api_id: {api_id}", file=sys.stderr)
        sys.exit(1)


def create_client(api_id: int, api_hash: str) -> TelegramClient:
    os.makedirs(os.path.dirname(SESSION_PATH), exist_ok=True)
    return TelegramClient(
        SESSION_PATH,
        api_id,
        api_hash,
        connection_retries=2,
        timeout=15,
    )


async def ensure_authorized(client: TelegramClient) -> bool:
    await client.connect()
    if not await client.is_user_authorized():
        print(
            "❌ Сессия Telegram UserBot ещё не авторизована.\n"
            "Откройте вкладку Antigravity в боковом меню Home Assistant и один раз выполните в терминале:\n"
            "  tg-login\n"
            "После ввода номера телефона и кода из Telegram файл сессии сохранится в /data/telegram_sessions/.",
            file=sys.stderr,
        )
        return False
    return True


def entity_kind(entity) -> str:
    if isinstance(entity, User):
        return "bot" if getattr(entity, "bot", False) else "user"
    if isinstance(entity, Chat):
        return "group"
    if isinstance(entity, Channel):
        return "channel" if getattr(entity, "broadcast", False) else "supergroup"
    return "unknown"


def entity_display_name(entity) -> str:
    if entity is None:
        return "Unknown"
    if isinstance(entity, User):
        parts = [p for p in [entity.first_name, entity.last_name] if p]
        name = " ".join(parts) if parts else (entity.username or str(entity.id))
        return name
    title = getattr(entity, "title", None)
    if title:
        return title
    return getattr(entity, "username", None) or str(getattr(entity, "id", "Unknown"))


def format_media_tag(msg) -> str:
    media = getattr(msg, "media", None)
    if not media:
        return ""
    if isinstance(media, MessageMediaPhoto):
        return "[Фото]"
    if isinstance(media, MessageMediaDocument):
        doc = getattr(media, "document", None)
        filename = ""
        mime = getattr(doc, "mime_type", "") if doc else ""
        if doc and getattr(doc, "attributes", None):
            for attr in doc.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    filename = attr.file_name
                    break
        if "audio" in mime or "ogg" in mime:
            return "[Аудио/Голосовое]"
        if "video" in mime:
            return f"[Видео{': ' + filename if filename else ''}]"
        return f"[Файл{': ' + filename if filename else ''}]"
    return f"[{type(media).__name__.replace('MessageMedia', '')}]"


async def resolve_sender_name(msg, cache: dict[int, str]) -> str:
    sender_id = getattr(msg, "sender_id", None)
    if sender_id and sender_id in cache:
        return cache[sender_id]

    sender = getattr(msg, "sender", None)
    if sender is None and sender_id is not None and len(cache) < 40:
        try:
            sender = await msg.get_sender()
        except Exception:
            sender = None

    if sender is not None:
        name = entity_display_name(sender)
        username = getattr(sender, "username", None)
        label = f"{name} (@{username})" if username else name
    elif msg.out:
        label = "Вы"
    elif sender_id is not None:
        label = f"ID:{sender_id}"
    else:
        label = "Чат/Канал"

    if sender_id is not None:
        cache[sender_id] = label
    return label


async def resolve_target(client: TelegramClient, target: str):
    raw = target.strip()
    lower = raw.lower()
    if lower in ("me", "saved", "избранное"):
        return await client.get_me()

    # Collect dialogs first so cache is populated and we can match by ID, username, or title
    dialogs = []
    async for d in client.iter_dialogs(limit=200):
        dialogs.append(d)

    # 1. Numeric ID
    try:
        target_id = int(raw)
        for d in dialogs:
            if d.id == target_id or getattr(d.entity, "id", None) == target_id:
                return d.entity
        return await client.get_entity(target_id)
    except ValueError:
        pass

    # 2. Username match (@username or username)
    handle = lower.lstrip("@")
    for d in dialogs:
        uname = getattr(d.entity, "username", None)
        if uname and uname.lower() == handle:
            return d.entity

    # 3. Exact title match (case-insensitive)
    for d in dialogs:
        if (d.name or "").strip().lower() == lower:
            return d.entity

    # 4. Partial title match
    matches = [d for d in dialogs if lower in (d.name or "").lower()]
    if len(matches) == 1:
        return matches[0].entity
    if len(matches) > 1:
        # Return most recent active match (iter_dialogs yields most recent first),
        # while informing caller on stderr about alternatives.
        alts = ", ".join(f"{m.name} [{m.id}]" for m in matches[:5])
        print(f"ℹ️ Найдено несколько чатов по '{raw}': {alts}. Выбран самый недавний: {matches[0].name} [{matches[0].id}]", file=sys.stderr)
        return matches[0].entity

    # 5. Direct Telegram resolve fallback (public @username or t.me link)
    return await client.get_entity(raw)


async def cmd_login(args) -> int:
    api_id, api_hash = load_credentials()
    client = create_client(api_id, api_hash)
    try:
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"✅ Вы уже авторизованы как: {entity_display_name(me)} (@{me.username or '-'}, ID: {me.id})")
            print(f"Файл сессии: {SESSION_PATH}.session")
            return 0

        print("=== Авторизация Telegram UserBot (Telethon) ===")
        print("Введите номер телефона в международном формате (например, +380XXXXXXXXX),")
        print("затем код подтверждения из Telegram (и облачный пароль 2FA, если он включён).\n")
        await client.start()
        me = await client.get_me()
        print(f"\n✅ Авторизация успешна! Аккаунт: {entity_display_name(me)} (@{me.username or '-'}, ID: {me.id})")
        print(f"Сессия сохранена в {SESSION_PATH}.session")
        return 0
    finally:
        await client.disconnect()


async def cmd_status(args) -> int:
    api_id, api_hash = load_credentials()
    client = create_client(api_id, api_hash)
    try:
        if not await ensure_authorized(client):
            return 1
        me = await client.get_me()
        print(f"✅ Telegram UserBot активен: {entity_display_name(me)} (@{me.username or '-'}, ID: {me.id})")
        print(f"Сессия: {SESSION_PATH}.session")
        return 0
    finally:
        await client.disconnect()


async def cmd_dialogs(args) -> int:
    api_id, api_hash = load_credentials()
    client = create_client(api_id, api_hash)
    try:
        if not await ensure_authorized(client):
            return 1

        scan_limit = max(args.limit * 4, 200) if (args.query or args.type != "all") else args.limit
        query = args.query.lower().strip() if args.query else ""
        items = []

        async for d in client.iter_dialogs(limit=scan_limit):
            kind = entity_kind(d.entity)
            if args.type != "all" and kind != args.type:
                continue
            title = d.name or "(Без названия)"
            username = getattr(d.entity, "username", None) or ""
            if query and query not in title.lower() and query not in username.lower() and query != str(d.id):
                continue

            last_dt = d.date.astimezone().strftime("%Y-%m-%d %H:%M") if d.date else ""
            items.append({
                "id": d.id,
                "type": kind,
                "title": title,
                "username": username,
                "unread": d.unread_count,
                "last_date": last_dt,
            })
            if len(items) >= args.limit:
                break

        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
            return 0

        if not items:
            print("Диалоги не найдены.")
            return 0

        for it in items:
            uname = f"@{it['username']}" if it["username"] else "-"
            unread = f" | непрочитано: {it['unread']}" if it["unread"] else ""
            print(f"[{it['id']}] ({it['type']}) {it['title']} | {uname}{unread} | {it['last_date']}")
        return 0
    finally:
        await client.disconnect()


async def cmd_history(args) -> int:
    api_id, api_hash = load_credentials()
    client = create_client(api_id, api_hash)
    try:
        if not await ensure_authorized(client):
            return 1

        try:
            entity = await resolve_target(client, args.target)
        except Exception as exc:
            print(f"❌ Не удалось найти чат '{args.target}': {exc}", file=sys.stderr)
            return 1

        cutoff = None
        if args.days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

        messages = []
        kwargs = {"limit": args.limit}
        if args.search:
            kwargs["search"] = args.search

        async for msg in client.iter_messages(entity, **kwargs):
            if cutoff and msg.date and msg.date < cutoff:
                break
            messages.append(msg)

        # Chronological order (oldest -> newest)
        messages.reverse()
        sender_cache: dict[int, str] = {}
        records = []

        for msg in messages:
            dt_str = msg.date.astimezone().strftime("%Y-%m-%d %H:%M") if msg.date else ""
            author = await resolve_sender_name(msg, sender_cache)
            media_tag = format_media_tag(msg)
            text = (msg.message or "").strip()
            parts = [p for p in [media_tag, text] if p]
            body = " ".join(parts) if parts else "[пустое/сервисное сообщение]"

            reply_to = getattr(msg, "reply_to_msg_id", None)
            fwd_info = ""
            if getattr(msg, "fwd_from", None):
                fwd_name = getattr(msg.fwd_from, "from_name", None) or "переслано"
                fwd_info = f" [fwd: {fwd_name}]"

            records.append({
                "id": msg.id,
                "date": dt_str,
                "author": author,
                "reply_to": reply_to,
                "forwarded": fwd_info.strip(),
                "text": body,
            })

        if args.json:
            print(json.dumps({
                "chat": entity_display_name(entity),
                "chat_id": getattr(entity, "id", None),
                "count": len(records),
                "messages": records,
            }, ensure_ascii=False, indent=2))
            return 0

        chat_title = entity_display_name(entity)
        chat_uname = getattr(entity, "username", None)
        header_extra = f"@{chat_uname}, " if chat_uname else ""
        print(f"=== {chat_title} ({header_extra}ID: {getattr(entity, 'id', '-')}) | сообщений: {len(records)} ===")
        for r in records:
            rep = f" (ответ на #{r['reply_to']})" if r["reply_to"] else ""
            fwd = f" {r['forwarded']}" if r["forwarded"] else ""
            print(f"[#{r['id']} | {r['date']}] {r['author']}{rep}{fwd}: {r['text']}")
        return 0
    finally:
        await client.disconnect()


async def cmd_search(args) -> int:
    api_id, api_hash = load_credentials()
    client = create_client(api_id, api_hash)
    try:
        if not await ensure_authorized(client):
            return 1

        cutoff = None
        if args.days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

        sender_cache: dict[int, str] = {}
        results = []

        async for msg in client.iter_messages(None, search=args.query, limit=args.limit):
            if cutoff and msg.date and msg.date < cutoff:
                break
            chat = getattr(msg, "chat", None)
            if chat is None:
                try:
                    chat = await msg.get_chat()
                except Exception:
                    chat = None

            chat_title = entity_display_name(chat)
            chat_id = getattr(msg, "chat_id", None)
            dt_str = msg.date.astimezone().strftime("%Y-%m-%d %H:%M") if msg.date else ""
            author = await resolve_sender_name(msg, sender_cache)
            media_tag = format_media_tag(msg)
            text = (msg.message or "").strip()
            body = " ".join(p for p in [media_tag, text] if p) or "[без текста]"

            results.append({
                "chat_id": chat_id,
                "chat_title": chat_title,
                "msg_id": msg.id,
                "date": dt_str,
                "author": author,
                "text": body,
            })

        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
            return 0

        if not results:
            print(f"По запросу '{args.query}' ничего не найдено.")
            return 0

        print(f"=== Найдено сообщений: {len(results)} ===")
        for r in results:
            print(f"[{r['date']}] [{r['chat_title']} ({r['chat_id']})] {r['author']}: {r['text']}")
        return 0
    finally:
        await client.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Telegram UserBot CLI for Antigravity")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Интерактивная авторизация в Telegram (телефон + код)")
    sub.add_parser("status", help="Проверить статус авторизации UserBot")

    p_dialogs = sub.add_parser("dialogs", help="Список чатов, групп и каналов")
    p_dialogs.add_argument("--limit", type=int, default=30)
    p_dialogs.add_argument("--query", type=str, default="")
    p_dialogs.add_argument("--type", choices=["all", "user", "bot", "group", "supergroup", "channel"], default="all")
    p_dialogs.add_argument("--json", action="store_true")

    p_hist = sub.add_parser("history", help="Прочитать историю сообщений из чата/канала")
    p_hist.add_argument("target", help="ID чата, @username, 'me'/'saved' или часть названия чата")
    p_hist.add_argument("--limit", type=int, default=50)
    p_hist.add_argument("--days", type=float, default=None)
    p_hist.add_argument("--search", type=str, default="")
    p_hist.add_argument("--json", action="store_true")

    p_search = sub.add_parser("search", help="Глобальный поиск сообщений по всем чатам")
    p_search.add_argument("query", help="Поисковый запрос")
    p_search.add_argument("--limit", type=int, default=30)
    p_search.add_argument("--days", type=float, default=None)
    p_search.add_argument("--json", action="store_true")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "login": cmd_login,
        "status": cmd_status,
        "dialogs": cmd_dialogs,
        "history": cmd_history,
        "search": cmd_search,
    }
    try:
        return asyncio.run(handlers[args.command](args))
    except FloodWaitError as exc:
        print(f"⚠️ Telegram ограничил частоту запросов (FloodWait {exc.seconds} сек).", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nПрервано пользователем.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
