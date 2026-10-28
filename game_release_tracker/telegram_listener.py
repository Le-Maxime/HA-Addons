import logging
import threading
import time
import re
import requests
from typing import Optional, Dict, Tuple, List
from storage import PostStorage

logger = logging.getLogger(__name__)


class TelegramListener:
    """
    Background listener for Telegram Bot updates.
    Handles:
    - Interactive Game Catalog with Categories & Pagination (all games from voices38 & DenuvOwO)
    - Full release details on game click (cover, build, links, NFO)
    - Return to catalog navigation across photo and text messages
    - Strict Admin-only access for /list, /allow, /deny and inline approval buttons
    - User access requests with Admin confirmation (Inline Buttons) without duplicate spam
    - Adding bot to Groups and Channels with Admin approval
    - Inline queries in any chat/group/PM (@le_crack_bot game_name)
    - Interactive in-chat /search and /find commands
    """

    def __init__(self, bot_token: str, admin_id: str, storage: PostStorage, notifier=None):
        self.bot_token = bot_token.strip()
        self.admin_id = str(admin_id).strip()
        self.storage = storage
        self.notifier = notifier
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.offset = 0
        self.running = False
        self._thread: Optional[threading.Thread] = None

        # Ensure admin is in approved subscribers
        if self.admin_id:
            self.storage.ensure_admin(self.admin_id)

    def _setup_bot_commands(self):
        """Sets user commands for all, and admin-only commands specifically for Admin."""
        user_commands = [
            {"command": "start", "description": "🚀 Главное меню и каталог"},
            {"command": "games", "description": "🎮 Каталог всех игр и взломов"},
            {"command": "search", "description": "🔎 Поиск релизов по названию"},
            {"command": "help", "description": "ℹ️ Справка и возможности"},
        ]
        admin_commands = [
            {"command": "start", "description": "👑 Главное меню администратора"},
            {"command": "games", "description": "🎮 Каталог всех игр и взломов"},
            {"command": "search", "description": "🔎 Поиск релизов по названию"},
            {"command": "list", "description": "📋 Список подписчиков и групп"},
            {"command": "allow", "description": "✅ Разрешить доступ: /allow ID"},
            {"command": "deny", "description": "❌ Запретить доступ: /deny ID"},
            {"command": "help", "description": "ℹ️ Полная справка администратора"},
        ]
        try:
            # Default for all regular users and groups
            requests.post(f"{self.base_url}/setMyCommands", json={"commands": user_commands}, timeout=10)
            # Personal menu specifically for Admin ID
            if self.admin_id:
                try:
                    scope = {"type": "chat", "chat_id": int(self.admin_id)}
                    requests.post(f"{self.base_url}/setMyCommands", json={"commands": admin_commands, "scope": scope}, timeout=10)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Could not set bot commands: {e}")

    def _init_offset(self):
        """Fetches the latest update_id so old backlog is not reprocessed on bot restart."""
        try:
            r = requests.get(f"{self.base_url}/getUpdates", params={"offset": -1, "timeout": 5}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                results = data.get("result", [])
                if results:
                    self.offset = results[-1]["update_id"] + 1
                    logger.info(f"Telegram listener offset initialized to {self.offset}")
        except Exception as e:
            logger.warning(f"Could not initialize Telegram offset: {e}")

    def start(self):
        """Starts the Telegram polling loop in a background thread."""
        if self.running or not self.bot_token:
            return
        self._setup_bot_commands()
        self._init_offset()
        self.running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="TelegramListener")
        self._thread.start()
        logger.info(f"TelegramListener started for Admin ID {self.admin_id}")

    def stop(self):
        """Stops the Telegram polling loop."""
        self.running = False

    def send_message(self, chat_id: str, text: str, reply_markup: Optional[Dict] = None) -> bool:
        """Sends a message with optional reply_markup (inline keyboard)."""
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            r = requests.post(f"{self.base_url}/sendMessage", json=payload, timeout=10)
            return r.status_code == 200
        except Exception as e:
            logger.error(f"Error sending message to {chat_id}: {e}")
            return False

    def edit_message_text(self, chat_id: str, message_id: int, text: str, reply_markup: Optional[Dict] = None) -> bool:
        """Edits an existing text message."""
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            r = requests.post(f"{self.base_url}/editMessageText", json=payload, timeout=10)
            return r.status_code == 200
        except Exception as e:
            logger.debug(f"Error editing message {message_id}: {e}")
            return False

    def delete_message(self, chat_id: str, message_id: int) -> bool:
        """Deletes a message by chat_id and message_id."""
        try:
            r = requests.post(f"{self.base_url}/deleteMessage", json={"chat_id": chat_id, "message_id": message_id}, timeout=10)
            return r.status_code == 200
        except Exception as e:
            logger.debug(f"Error deleting message {message_id}: {e}")
            return False

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> bool:
        """Answers a Telegram callback query."""
        payload = {
            "callback_query_id": callback_query_id,
            "text": text
        }
        try:
            r = requests.post(f"{self.base_url}/answerCallbackQuery", json=payload, timeout=10)
            return r.status_code == 200
        except Exception as e:
            logger.error(f"Error answering callback query {callback_query_id}: {e}")
            return False

    def answer_inline_query(self, inline_query_id: str, results: list, cache_time: int = 5) -> bool:
        """Answers an inline query from any chat or group."""
        payload = {
            "inline_query_id": inline_query_id,
            "results": results,
            "cache_time": cache_time,
            "is_personal": False
        }
        try:
            r = requests.post(f"{self.base_url}/answerInlineQuery", json=payload, timeout=10)
            return r.status_code == 200
        except Exception as e:
            logger.error(f"Error answering inline query {inline_query_id}: {e}")
            return False

    def _poll_loop(self):
        """Main long-polling loop for getUpdates."""
        while self.running:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {
                    "offset": self.offset,
                    "timeout": 20,
                    "allowed_updates": ["message", "callback_query", "my_chat_member", "inline_query"]
                }
                resp = requests.get(url, params=params, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        updates = data.get("result", [])
                        for u in updates:
                            self.offset = u["update_id"] + 1
                            self._handle_update(u)
                else:
                    logger.warning(f"getUpdates returned HTTP {resp.status_code}: {resp.text}")
                    time.sleep(3)
            except requests.exceptions.Timeout:
                continue
            except Exception as e:
                logger.error(f"Error in Telegram polling loop: {e}")
                time.sleep(5)

    def _handle_update(self, update: Dict):
        """Dispatches update to appropriate handler."""
        # 1. Handle Inline Queries (@le_crack_bot search_text in any group or PM)
        if "inline_query" in update:
            self._handle_inline_query(update["inline_query"])
            return

        # 2. Handle Callback Queries (Catalog navigation, Game Selection, Admin approval)
        if "callback_query" in update:
            self._handle_callback_query(update["callback_query"])
            return

        # 3. Handle Messages
        if "message" in update:
            self._handle_message(update["message"])
            return

        # 4. Handle Bot added to group/channel via my_chat_member
        if "my_chat_member" in update:
            self._handle_chat_member_update(update["my_chat_member"])
            return

    def _handle_inline_query(self, iq: Dict):
        """Handles inline search requests in any chat or group."""
        query_id = iq.get("id")
        query = (iq.get("query") or "").strip()

        releases = self.storage.search_saved_releases(query=query, limit=20)
        results = []

        if not releases and not query:
            results.append({
                "type": "article",
                "id": "info_placeholder",
                "title": "🔍 Поиск релизов DenuvOwO & voices38",
                "description": "Введите название игры, например: @le_crack_bot Assassin's Creed",
                "input_message_content": {
                    "message_text": "🎮 <b>Release Tracker Bot</b> (@le_crack_bot)\nИспользуйте инлайн-поиск для быстрой отправки релизов в любые группы!",
                    "parse_mode": "HTML"
                }
            })
        else:
            for idx, r in enumerate(releases):
                title_line = f"{r['game_title']}"
                clean_build = re.sub(r'<[^>]+>', '', r['build_display'])
                desc_line = f"🎮 Взлом ({r['author_type']}) • Билд: {clean_build}"
                thumb = r.get("cover_image") or "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/3321460/header.jpg"

                results.append({
                    "type": "article",
                    "id": f"rel_{r['release_id']}_{idx}",
                    "title": title_line,
                    "description": desc_line,
                    "thumb_url": thumb,
                    "input_message_content": {
                        "message_text": r["message_text"],
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False
                    }
                })

        self.answer_inline_query(query_id, results, cache_time=5)

    def _build_catalog_view(self, category: str = "all", page: int = 0) -> Tuple[str, Dict]:
        """Builds message text and inline keyboard for the interactive game catalog."""
        limit = 6
        offset = page * limit
        items, total = self.storage.get_catalog_releases(category=category, offset=offset, limit=limit)
        counts = self.storage.get_category_counts()

        total_pages = max(1, (total + limit - 1) // limit)
        page = min(page, total_pages - 1)

        cat_names = {
            "all": "Все релизы",
            "crack": "Взломы (voices38)",
            "hv": "Гипервизор (DenuvOwO)"
        }
        current_cat_name = cat_names.get(category, "Все релизы")

        text = (
            f"🎮 <b>Интерактивный каталог релизов</b>\n\n"
            f"📂 Раздел: <b>{current_cat_name}</b> (Всего: <code>{total}</code>)\n"
            f"📄 Страница <code>{page + 1}</code> из <code>{total_pages}</code>\n\n"
            f"<i>Выберите игру из списка ниже, чтобы получить последний билд и ссылки:</i>"
        )

        keyboard = []

        # 1. Category selector tabs
        tab_all = f"🌟 Все ({counts['all']})" if category != "all" else f"🔘 Все ({counts['all']})"
        tab_crack = f"🔓 Кряки ({counts['crack']})" if category != "crack" else f"🔘 Кряки ({counts['crack']})"
        tab_hv = f"⚡️ HV ({counts['hv']})" if category != "hv" else f"🔘 HV ({counts['hv']})"

        keyboard.append([
            {"text": tab_all, "callback_data": "cat:all:0"},
            {"text": tab_crack, "callback_data": "cat:crack:0"},
            {"text": tab_hv, "callback_data": "cat:hv:0"}
        ])

        # 2. Game buttons (1 button per game)
        for item in items:
            icon = "⚡️" if item["author_type"] == "Гипервизор" or item["author_type"] == "HV" else "🔓"
            title = item["game_title"]
            if len(title) > 35:
                title = title[:33] + "..."
            btn_text = f"{icon} {title} ({item['author_type']})"
            # Truncate release_id so total callback_data stays under Telegram's 64-byte limit
            rel_id_safe = item['release_id'].encode('utf-8')[:58].decode('utf-8', errors='ignore')
            keyboard.append([
                {"text": btn_text, "callback_data": f"view:{rel_id_safe}"}
            ])

        # 3. Pagination row
        nav_row = []
        if page > 0:
            nav_row.append({"text": "⬅️ Назад", "callback_data": f"cat:{category}:{page - 1}"})
        nav_row.append({"text": f"• {page + 1} / {total_pages} •", "callback_data": "noop"})
        if (page + 1) * limit < total:
            nav_row.append({"text": "Вперед ➡️", "callback_data": f"cat:{category}:{page + 1}"})
        keyboard.append(nav_row)

        # 4. Search button
        keyboard.append([
            {"text": "🔎 Поиск по названию", "switch_inline_query_current_chat": ""}
        ])

        return text, {"inline_keyboard": keyboard}

    def _handle_callback_query(self, cq: Dict):
        """Handles inline button clicks (Catalog navigation, game viewing, and Admin approval)."""
        from_user = cq.get("from", {})
        from_id = str(from_user.get("id", ""))
        cq_id = cq.get("id")
        data = cq.get("data", "")
        msg = cq.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        msg_id = msg.get("message_id")
        has_photo = bool(msg.get("photo"))

        if data == "noop":
            self.answer_callback_query(cq_id)
            return

        # 1. Catalog navigation: cat:<category>:<page>
        if data.startswith("cat:"):
            parts = data.split(":")
            category = parts[1] if len(parts) > 1 else "all"
            page = int(parts[2]) if len(parts) > 2 else 0
            text, reply_markup = self._build_catalog_view(category=category, page=page)

            self.answer_callback_query(cq_id)

            if has_photo:
                # If returning from a photo game card, delete photo card and send catalog text
                if msg_id:
                    self.delete_message(chat_id, msg_id)
                self.send_message(chat_id, text, reply_markup=reply_markup)
            else:
                # If currently on text catalog, edit text message in place for smooth pagination
                success = False
                if msg_id:
                    success = self.edit_message_text(chat_id, msg_id, text, reply_markup=reply_markup)
                if not success:
                    self.send_message(chat_id, text, reply_markup=reply_markup)
            return

        # 2. View specific game release: view:<release_id>
        if data.startswith("view:"):
            rel_id = data.split(":", 1)[1]
            rel = self.storage.get_saved_release(rel_id)
            if not rel:
                self.answer_callback_query(cq_id, text="⚠️ Информация о релизе не найдена.")
                return

            self.answer_callback_query(cq_id)
            cover = rel.get("cover_image")
            caption = rel.get("message_text")

            back_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🎮 Вернуться в каталог", "callback_data": "cat:all:0"},
                        {"text": "📤 Поделиться", "switch_inline_query": rel["game_title"]}
                    ]
                ]
            }

            # Delete the previous catalog menu message to keep the chat clean
            if msg_id and not has_photo:
                self.delete_message(chat_id, msg_id)

            sent = False
            if cover and self.notifier:
                sent = self.notifier.send_photo_to_chat(chat_id, cover, caption=caption, parse_mode="HTML", reply_markup=back_markup)
            if not sent:
                self.send_message(chat_id, caption, reply_markup=back_markup)
            return

        # 3. Admin Access Approval / Denial
        if from_id != self.admin_id:
            self.answer_callback_query(cq_id, text="⛔️ Доступ запрещен. Только администратор может управлять доступом.")
            return

        if data.startswith("allow:"):
            target_id = data.split(":", 1)[1]
            self.storage.set_subscriber_status(target_id, 1)
            self.answer_callback_query(cq_id, text="✅ Доступ разрешен!")

            old_text = msg.get("text", "")
            new_text = old_text + f"\n\n✅ <b>Доступ РАЗРЕШЕН администратором</b> (ID: <code>{target_id}</code>)"
            if msg_id:
                self.edit_message_text(chat_id, msg_id, new_text)

            self.send_message(
                target_id,
                "🎉 <b>Доступ одобрен!</b>\nТеперь в этот чат будут приходить уведомления о новых релизах."
            )
            logger.info(f"Admin approved access for {target_id}")

        elif data.startswith("deny:"):
            target_id = data.split(":", 1)[1]
            self.storage.set_subscriber_status(target_id, 0)
            self.answer_callback_query(cq_id, text="❌ В доступе отказано")

            old_text = msg.get("text", "")
            new_text = old_text + f"\n\n❌ <b>В доступе ОТКАЗАНО администратором</b> (ID: <code>{target_id}</code>)"
            if msg_id:
                self.edit_message_text(chat_id, msg_id, new_text)

            self.send_message(
                target_id,
                "⛔️ <b>Администратор отклонил запрос на доступ.</b>"
            )
            logger.info(f"Admin denied access for {target_id}")

    def _handle_message(self, msg: Dict):
        """Processes incoming user and group messages."""
        chat = msg.get("chat", {})
        chat_id = str(chat.get("id", ""))
        chat_type = chat.get("type", "private")
        text = (msg.get("text") or "").strip()
        from_user = msg.get("from", {})
        from_id = str(from_user.get("id", ""))
        from_username = from_user.get("username") or ""
        from_name = f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip()

        # Handle Groups & Supergroups
        if chat_type in ["group", "supergroup", "channel"]:
            group_title = chat.get("title", "Группа")
            sub = self.storage.get_subscriber(chat_id)

            if not sub:
                # First time group request
                is_new_group = self.storage.add_or_update_subscriber(chat_id, chat_type, group_title, is_allowed=0)
                self.send_message(
                    chat_id,
                    f"⏳ <b>Запрос на подключение группы «{group_title}» отправлен администратору.</b>\n"
                    "Уведомления начнут приходить после одобрения."
                )
                if is_new_group:
                    reply_markup = {
                        "inline_keyboard": [
                            [
                                {"text": "✅ Разрешить группу", "callback_data": f"allow:{chat_id}"},
                                {"text": "❌ Отклонить", "callback_data": f"deny:{chat_id}"}
                            ]
                        ]
                    }
                    admin_text = (
                        f"👥 <b>Запрос на подключение группы</b>\n\n"
                        f"📌 Группа: <b>{group_title}</b>\n"
                        f"🆔 ID группы: <code>{chat_id}</code>\n"
                        f"👤 Добавил: @{from_username} ({from_name}, ID: <code>{from_id}</code>)"
                    )
                    self.send_message(self.admin_id, admin_text, reply_markup=reply_markup)
            elif not sub.get("is_allowed"):
                # Group already pending
                if text.startswith("/start") or "new_chat_members" in msg:
                    self.send_message(
                        chat_id,
                        f"⏳ <b>Запрос на подключение группы «{group_title}» уже находится на рассмотрении.</b>"
                    )
            else:
                if text.startswith("/start") or text.startswith("/help"):
                    reply_markup = {
                        "inline_keyboard": [
                            [
                                {"text": "🎮 Каталог релизов", "callback_data": "cat:all:0"},
                                {"text": "🔎 Искать в группе", "switch_inline_query_current_chat": ""},
                            ]
                        ]
                    }
                    self.send_message(
                        chat_id,
                        f"✅ <b>Бот активен в группе «{group_title}»!</b>\nСюда автоматически приходят уведомления о новых релизах.\n\n"
                        "💡 Нажмите кнопку ниже для открытия каталога или поиска.",
                        reply_markup=reply_markup
                    )
                elif text.startswith("/games") or text.startswith("/catalog"):
                    cat_text, reply_markup = self._build_catalog_view("all", 0)
                    self.send_message(chat_id, cat_text, reply_markup=reply_markup)
                elif text.startswith("/search") or text.startswith("/find"):
                    query = re.sub(r'^/(?:search|find)\s*', '', text).strip()
                    self._perform_in_chat_search(chat_id, query)
            return

        # Handle Private Chats
        if chat_type == "private":
            user_title = f"@{from_username} ({from_name})" if from_username else from_name

            # STRICT CHECK: Admin-only commands (/list, /allow, /deny)
            if from_id == self.admin_id:
                if text.startswith("/start") or text.startswith("/help"):
                    help_text = (
                        "👑 <b>Панель администратора Release Tracker</b>\n\n"
                        "Команды управления:\n"
                        "• <code>/games</code> — интерактивный каталог всех релизов\n"
                        "• <code>/search [игра]</code> — найти релиз по базе\n"
                        "• <code>/list</code> — список всех подписчиков и групп\n"
                        "• <code>/allow ID</code> — вручную разрешить доступ чату\n"
                        "• <code>/deny ID</code> — запретить доступ чату\n"
                        "• <code>/help</code> — эта справка\n\n"
                        "💡 Нажмите <b>«🎮 Каталог игр»</b> для просмотра списка и выбора нужной игры:"
                    )
                    reply_markup = {
                        "inline_keyboard": [
                            [
                                {"text": "🎮 Каталог игр (Выбор)", "callback_data": "cat:all:0"},
                                {"text": "🔎 Поиск в чате", "switch_inline_query_current_chat": ""}
                            ],
                            [
                                {"text": "📤 Поделиться в группе", "switch_inline_query": ""}
                            ]
                        ]
                    }
                    self.send_message(chat_id, help_text, reply_markup=reply_markup)
                    return

                if text.startswith("/games") or text.startswith("/catalog"):
                    cat_text, reply_markup = self._build_catalog_view("all", 0)
                    self.send_message(chat_id, cat_text, reply_markup=reply_markup)
                    return

                if text.startswith("/search") or text.startswith("/find") or text.startswith("/s"):
                    query = re.sub(r'^/(?:search|find|s)\s*', '', text).strip()
                    self._perform_in_chat_search(chat_id, query)
                    return

                if text.startswith("/list") or text.startswith("/subscribers"):
                    subs = self.storage.list_all_subscribers()
                    if not subs:
                        self.send_message(chat_id, "ℹ️ Список подписчиков пуст.")
                        return

                    lines = ["📋 <b>Список чатов и подписчиков:</b>\n"]
                    for s in subs:
                        status_icon = "✅" if s["is_allowed"] else "⏳"
                        c_type = "👥 Группа" if s["chat_type"] in ["group", "supergroup"] else "👤 ЛС"
                        lines.append(f"{status_icon} {c_type}: <b>{s['title']}</b>\n   ID: <code>{s['chat_id']}</code>")

                    self.send_message(chat_id, "\n".join(lines))
                    return

                if text.startswith("/allow"):
                    parts = text.split()
                    if len(parts) > 1:
                        target = parts[1].strip()
                        self.storage.set_subscriber_status(target, 1)
                        self.send_message(chat_id, f"✅ Доступ для <code>{target}</code> успешно разрешен.")
                        self.send_message(target, "🎉 <b>Доступ одобрен!</b> Теперь вы будете получать уведомления о релизах.")
                    else:
                        self.send_message(chat_id, "⚠️ Укажите ID чата: <code>/allow 123456789</code>")
                    return

                if text.startswith("/deny") or text.startswith("/revoke"):
                    parts = text.split()
                    if len(parts) > 1:
                        target = parts[1].strip()
                        self.storage.set_subscriber_status(target, 0)
                        self.send_message(chat_id, f"❌ Доступ для <code>{target}</code> отозван.")
                        self.send_message(target, "⛔️ Доступ к уведомлениям был приостановлен администратором.")
                    else:
                        self.send_message(chat_id, "⚠️ Укажите ID чата: <code>/deny 123456789</code>")
                    return

            # Non-admin user (ANY /list, /allow, /deny attempts by non-admin are completely blocked)
            sub = self.storage.get_subscriber(chat_id)
            if sub and sub.get("is_allowed"):
                if text.startswith("/games") or text.startswith("/catalog"):
                    cat_text, reply_markup = self._build_catalog_view("all", 0)
                    self.send_message(chat_id, cat_text, reply_markup=reply_markup)
                    return

                if text.startswith("/search") or text.startswith("/find"):
                    query = re.sub(r'^/(?:search|find)\s*', '', text).strip()
                    self._perform_in_chat_search(chat_id, query)
                    return

                reply_markup = {
                    "inline_keyboard": [
                        [
                            {"text": "🎮 Каталог игр (Выбор)", "callback_data": "cat:all:0"},
                            {"text": "🔎 Поиск в чате", "switch_inline_query_current_chat": ""}
                        ],
                        [
                            {"text": "📤 Поделиться в группе", "switch_inline_query": ""}
                        ]
                    ]
                }
                self.send_message(
                    chat_id,
                    "👋 <b>Добро пожаловать в Release Tracker!</b>\n\n"
                    "Вам доступны все актуальные кряки от <b>voices38</b> и гипервизоры от <b>DenuvOwO</b>.\n\n"
                    "💡 Нажмите <b>«🎮 Каталог игр»</b> ниже или введите команду <code>/games</code>, чтобы выбрать нужную игру.",
                    reply_markup=reply_markup
                )
            elif sub and not sub.get("is_allowed"):
                # Request already pending - do not duplicate message to Admin
                self.send_message(
                    chat_id,
                    "⏳ <b>Ваш запрос на доступ уже находится на рассмотрении у администратора.</b>\n"
                    "Пожалуйста, ожидайте подтверждения."
                )
            else:
                # First time user request — add_or_update_subscriber returns True only if newly added
                is_new = self.storage.add_or_update_subscriber(chat_id, "private", user_title, is_allowed=0)
                self.send_message(
                    chat_id,
                    "🔒 <b>Доступ ограничен</b>\n"
                    "Запрос на доступ отправлен администратору бота. Ожидайте подтверждения."
                )

                if is_new:
                    # Send confirmation request with Inline Buttons to Admin ONCE (not on every repeated message)
                    reply_markup = {
                        "inline_keyboard": [
                            [
                                {"text": "✅ Разрешить", "callback_data": f"allow:{chat_id}"},
                                {"text": "❌ Запретить", "callback_data": f"deny:{chat_id}"}
                            ]
                        ]
                    }
                    admin_text = (
                        f"🔔 <b>Запрос доступа к боту</b>\n\n"
                        f"👤 Пользователь: @{from_username} (ID: <code>{chat_id}</code>)\n"
                        f"📝 Имя: {from_name}"
                    )
                    self.send_message(self.admin_id, admin_text, reply_markup=reply_markup)
                    logger.info(f"Access request received and sent to admin for user {chat_id} (@{from_username})")

    def _perform_in_chat_search(self, chat_id: str, query: str):
        """Performs a direct text/card search in PM or group."""
        releases = self.storage.search_saved_releases(query=query, limit=5)
        if not releases:
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "🔎 Искать через Inline", "switch_inline_query_current_chat": query}],
                    [{"text": "🎮 Открыть каталог", "callback_data": "cat:all:0"}]
                ]
            }
            msg = f"❌ По запросу «{query}» ничего не найдено в базе." if query else "ℹ️ В базе пока нет сохраненных релизов."
            self.send_message(chat_id, msg, reply_markup=reply_markup)
            return

        for r in releases:
            cover = r.get("cover_image")
            caption = r["message_text"]
            back_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🎮 Вернуться в каталог", "callback_data": "cat:all:0"},
                        {"text": "📤 Поделиться", "switch_inline_query": r["game_title"]}
                    ]
                ]
            }
            sent = False
            if cover and self.notifier:
                sent = self.notifier.send_photo_to_chat(chat_id, cover, caption=caption, parse_mode="HTML", reply_markup=back_markup)
            if not sent:
                self.send_message(chat_id, caption, reply_markup=back_markup)
            time.sleep(0.3)

    def _handle_chat_member_update(self, cm: Dict):
        """Handles bot being added or removed from groups."""
        chat = cm.get("chat", {})
        chat_id = str(chat.get("id", ""))
        chat_type = chat.get("type", "group")
        group_title = chat.get("title", "Группа")
        new_status = cm.get("new_chat_member", {}).get("status", "")
        from_user = cm.get("from", {})
        from_id = str(from_user.get("id", ""))
        from_username = from_user.get("username") or ""
        from_name = f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip()

        if new_status in ["member", "administrator"]:
            sub = self.storage.get_subscriber(chat_id)
            if not sub:
                self.storage.add_or_update_subscriber(chat_id, chat_type, group_title, is_allowed=0)
                self.send_message(
                    chat_id,
                    f"⏳ <b>Бот добавлен в группу «{group_title}».</b>\nЗапрос на активацию отправлен администратору."
                )
                reply_markup = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Разрешить группу", "callback_data": f"allow:{chat_id}"},
                            {"text": "❌ Отклонить", "callback_data": f"deny:{chat_id}"}
                        ]
                    ]
                }
                admin_text = (
                    f"👥 <b>Бот добавлен в новую группу</b>\n\n"
                    f"📌 Группа: <b>{group_title}</b>\n"
                    f"🆔 ID: <code>{chat_id}</code>\n"
                    f"👤 Добавил: @{from_username} ({from_name})"
                )
                self.send_message(self.admin_id, admin_text, reply_markup=reply_markup)
        elif new_status in ["left", "kicked"]:
            self.storage.set_subscriber_status(chat_id, 0)
            logger.info(f"Bot was removed from group {chat_id} ({group_title})")
