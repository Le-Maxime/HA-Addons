import sqlite3
import datetime
import logging
import re
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def normalize_title(title: str) -> str:
    t = re.sub(r'\[.*?\]', '', title or "")
    t = re.sub(r'\b(Re:|CRACKED|HYPERVISOR PLAYABLE|NOT CRACKED|Info|CRACKFIX|Pre-Release)\b', '', t, flags=re.I)
    t = re.sub(r'-(?:voices38|voices38_crack)\b', '', t, flags=re.I)
    t = t.replace('.', ' ')
    t = re.sub(r'[^a-zA-Z0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip().lower()
    return t


def clean_game_title(raw_title: str) -> str:
    """Cleans game title from brackets, suffixes, crackfix tags, and filters out removed posts."""
    if not raw_title:
        return ""
    if any(b in raw_title.lower() for b in ["removed by reddit", "[deleted]", "[removed]", "bickering"]):
        return ""

    t = raw_title
    t = re.sub(r'\[.*?\]', '', t)
    t = re.sub(r'\b(Re:|CRACKED|HYPERVISOR PLAYABLE|NOT CRACKED|Info|Pre-Release|CRACKFIX|HYPERVISOR)\b', '', t, flags=re.I)
    t = re.sub(r'-(?:voices38|voices38_crack)\b', '', t, flags=re.I)
    t = re.sub(r'\(?v\d+[\.\d]*(?:\s+[a-zA-Z0-9]+)*\)?', '', t, flags=re.I)
    t = re.sub(r'Build\s*\d+', '', t, flags=re.I)
    t = t.replace(".", " ")
    t = re.sub(r'\s+', ' ', t).strip(" :-\t\r\n")
    return t


class PostStorage:
    """Persistent SQLite storage for tracking seen posts, saved releases, catalog, and Telegram subscribers."""

    def __init__(self, db_path: str = "/data/tracker.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initializes database tables if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # WAL mode prevents 'database is locked' when polling loop and Telegram listener write concurrently
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS seen_posts (
                    post_id TEXT PRIMARY KEY,
                    author_id TEXT,
                    author_name TEXT,
                    topic_title TEXT,
                    post_subject TEXT,
                    post_url TEXT,
                    posted_date TEXT,
                    first_seen_at TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recent_releases (
                    release_key TEXT PRIMARY KEY,
                    author_name TEXT,
                    normalized_title TEXT,
                    notified_at TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    chat_id TEXT PRIMARY KEY,
                    chat_type TEXT,
                    title TEXT,
                    is_allowed INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS saved_releases (
                    release_id TEXT PRIMARY KEY,
                    game_title TEXT,
                    author_name TEXT,
                    author_type TEXT,
                    is_update INTEGER,
                    build_display TEXT,
                    build_datetime TEXT,
                    cover_image TEXT,
                    message_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Automatic database maintenance & cleanup of legacy/moderated posts/non-release comments
            cursor.execute("""
                DELETE FROM saved_releases
                WHERE lower(game_title) LIKE '%removed by reddit%'
                   OR lower(game_title) LIKE '%[deleted]%'
                   OR lower(game_title) LIKE '%[removed]%'
                   OR lower(game_title) LIKE '%bickering%'
                   OR game_title = 'Неизвестная игра'
                   OR game_title = ''
                   OR (author_name = 'Artifact' AND release_id LIKE 'cr_%')
            """)
            conn.commit()

    # --- Saved Releases & Interactive Catalog ---

    def save_release(self, release_id: str, game_title: str, author_name: str, author_type: str,
                     is_update: bool, build_display: str, build_datetime: Optional[str],
                     cover_image: Optional[str], message_text: str):
        """Saves or updates a clean release in the database."""
        clean_t = clean_game_title(game_title)
        if not clean_t or any(b in clean_t.lower() for b in ["removed by reddit", "deleted", "removed", "bickering"]):
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO saved_releases (
                    release_id, game_title, author_name, author_type,
                    is_update, build_display, build_datetime, cover_image, message_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(release_id) DO UPDATE SET
                    game_title = excluded.game_title,
                    author_name = excluded.author_name,
                    author_type = excluded.author_type,
                    is_update = excluded.is_update,
                    build_display = excluded.build_display,
                    build_datetime = excluded.build_datetime,
                    cover_image = excluded.cover_image,
                    message_text = excluded.message_text
            """, (
                str(release_id),
                clean_t,
                author_name,
                author_type,
                1 if is_update else 0,
                build_display,
                build_datetime or "",
                cover_image or "",
                message_text
            ))
            conn.commit()

    def get_saved_release(self, release_id: str) -> Optional[Dict]:
        """Gets a single release by its release_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT release_id, game_title, author_name, author_type,
                       is_update, build_display, build_datetime, cover_image, message_text, created_at
                FROM saved_releases
                WHERE release_id = ?
            """, (str(release_id),))
            r = cursor.fetchone()
            if r:
                return {
                    "release_id": r[0],
                    "game_title": r[1],
                    "author_name": r[2],
                    "author_type": r[3],
                    "is_update": bool(r[4]),
                    "build_display": r[5],
                    "build_datetime": r[6],
                    "cover_image": r[7],
                    "message_text": r[8],
                    "created_at": r[9]
                }
            return None

    def get_catalog_releases(self, category: str = "all", offset: int = 0, limit: int = 6) -> Tuple[List[Dict], int]:
        """
        Returns a paginated list of releases for the interactive catalog, deduplicated per game.
        category: 'all', 'crack' (voices38), 'hv' (DenuvOwO)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            where_clauses = [
                "lower(game_title) NOT LIKE '%removed by reddit%'",
                "lower(game_title) NOT LIKE '%bickering%'",
                "game_title != 'Неизвестная игра'",
                "game_title != ''"
            ]
            params = []

            if category in ["crack", "voices38"]:
                where_clauses.append("(author_type = 'Кряк' OR author_name = 'voices38')")
            elif category in ["hv", "denuvo"]:
                where_clauses.append("(author_type = 'Гипервизор' OR author_name = 'DenuvOwO')")

            where_str = "WHERE " + " AND ".join(where_clauses)

            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM saved_releases {where_str}")
            total_count = cursor.fetchone()[0]

            # Get paginated items
            query = f"""
                SELECT release_id, game_title, author_name, author_type,
                       is_update, build_display, build_datetime, cover_image, message_text, created_at
                FROM saved_releases
                {where_str}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor.execute(query, params + [limit, offset])
            rows = cursor.fetchall()
            items = [
                {
                    "release_id": r[0],
                    "game_title": r[1],
                    "author_name": r[2],
                    "author_type": r[3],
                    "is_update": bool(r[4]),
                    "build_display": r[5],
                    "build_datetime": r[6],
                    "cover_image": r[7],
                    "message_text": r[8],
                    "created_at": r[9]
                }
                for r in rows
            ]
            return items, total_count

    def get_category_counts(self) -> Dict[str, int]:
        """Returns total counts for all, crack, and hv categories."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            base_where = "WHERE lower(game_title) NOT LIKE '%removed by reddit%' AND lower(game_title) NOT LIKE '%bickering%' AND game_title != 'Неизвестная игра' AND game_title != ''"
            cursor.execute(f"SELECT COUNT(*) FROM saved_releases {base_where}")
            all_c = cursor.fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) FROM saved_releases {base_where} AND (author_type = 'Кряк' OR author_name = 'voices38')")
            crack_c = cursor.fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) FROM saved_releases {base_where} AND (author_type = 'Гипервизор' OR author_name = 'DenuvOwO')")
            hv_c = cursor.fetchone()[0]
            return {"all": all_c, "crack": crack_c, "hv": hv_c}

    def search_saved_releases(self, query: str = "", limit: int = 15) -> List[Dict]:
        """Searches saved releases for inline mode in Telegram."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            base_where = "lower(game_title) NOT LIKE '%removed by reddit%' AND lower(game_title) NOT LIKE '%bickering%' AND game_title != 'Неизвестная игра' AND game_title != ''"
            q = (query or "").strip().lower()
            if not q:
                cursor.execute(f"""
                    SELECT release_id, game_title, author_name, author_type,
                           is_update, build_display, build_datetime, cover_image, message_text, created_at
                    FROM saved_releases
                    WHERE {base_where}
                    ORDER BY created_at DESC LIMIT ?
                """, (limit,))
            else:
                pat = f"%{q}%"
                cursor.execute(f"""
                    SELECT release_id, game_title, author_name, author_type,
                           is_update, build_display, build_datetime, cover_image, message_text, created_at
                    FROM saved_releases
                    WHERE ({base_where}) AND (lower(game_title) LIKE ? OR lower(author_name) LIKE ? OR lower(build_display) LIKE ?)
                    ORDER BY created_at DESC LIMIT ?
                """, (pat, pat, pat, limit))

            rows = cursor.fetchall()
            return [
                {
                    "release_id": r[0],
                    "game_title": r[1],
                    "author_name": r[2],
                    "author_type": r[3],
                    "is_update": bool(r[4]),
                    "build_display": r[5],
                    "build_datetime": r[6],
                    "cover_image": r[7],
                    "message_text": r[8],
                    "created_at": r[9]
                }
                for r in rows
            ]

    # --- Subscribers Management ---

    def ensure_admin(self, admin_id: str):
        """Ensures the primary admin chat_id is always approved."""
        if not admin_id:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO subscribers (chat_id, chat_type, title, is_allowed)
                VALUES (?, 'private', 'Administrator', 1)
                ON CONFLICT(chat_id) DO UPDATE SET is_allowed = 1
            """, (str(admin_id),))
            conn.commit()

    def get_allowed_subscribers(self) -> List[str]:
        """Returns all approved chat_ids (users and groups)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM subscribers WHERE is_allowed = 1")
            return [str(row[0]) for row in cursor.fetchall()]

    def get_subscriber(self, chat_id: str) -> Optional[Dict]:
        """Gets info about a subscriber."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id, chat_type, title, is_allowed, created_at FROM subscribers WHERE chat_id = ?", (str(chat_id),))
            row = cursor.fetchone()
            if row:
                return {
                    "chat_id": row[0],
                    "chat_type": row[1],
                    "title": row[2],
                    "is_allowed": bool(row[3]),
                    "created_at": row[4]
                }
            return None

    def add_or_update_subscriber(self, chat_id: str, chat_type: str, title: str, is_allowed: int = 0) -> bool:
        """Adds a subscriber or updates metadata. Returns True if newly added."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_allowed FROM subscribers WHERE chat_id = ?", (str(chat_id),))
            row = cursor.fetchone()
            if row is None:
                cursor.execute("""
                    INSERT INTO subscribers (chat_id, chat_type, title, is_allowed)
                    VALUES (?, ?, ?, ?)
                """, (str(chat_id), chat_type, title, is_allowed))
                conn.commit()
                return True
            else:
                cursor.execute("""
                    UPDATE subscribers SET chat_type = ?, title = ? WHERE chat_id = ?
                """, (chat_type, title, str(chat_id)))
                conn.commit()
                return False

    def set_subscriber_status(self, chat_id: str, is_allowed: int) -> bool:
        """Approves (1) or Revokes (0) a subscriber."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE subscribers SET is_allowed = ? WHERE chat_id = ?", (is_allowed, str(chat_id)))
            conn.commit()
            return cursor.rowcount > 0

    def list_all_subscribers(self) -> List[Dict]:
        """Lists all registered subscribers and groups."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id, chat_type, title, is_allowed, created_at FROM subscribers ORDER BY created_at ASC")
            return [
                {
                    "chat_id": r[0],
                    "chat_type": r[1],
                    "title": r[2],
                    "is_allowed": bool(r[3]),
                    "created_at": r[4]
                }
                for r in cursor.fetchall()
            ]

    # --- Posts Tracking ---

    def is_post_seen(self, post_id: str) -> bool:
        """Checks if a post has already been recorded."""
        if not post_id:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM seen_posts WHERE post_id = ?", (str(post_id),))
            return cursor.fetchone() is not None

    def has_seen_topic(self, author_id: str, topic_title: str, topic_url: str) -> bool:
        """Checks if this author has previously posted in this topic / game."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            m = re.search(r't=(\d+)', topic_url or "")
            if m:
                topic_id_pat = f"%t={m.group(1)}%"
                cursor.execute(
                    "SELECT 1 FROM seen_posts WHERE author_id = ? AND (post_url LIKE ? OR topic_title = ?) LIMIT 1",
                    (str(author_id), topic_id_pat, topic_title)
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM seen_posts WHERE author_id = ? AND topic_title = ? LIMIT 1",
                    (str(author_id), topic_title)
                )
            return cursor.fetchone() is not None

    def is_game_recently_notified(self, author_name: str, raw_title: str, max_hours: int = 12) -> bool:
        """Checks if a notification for this game by this author was sent recently."""
        norm = normalize_title(raw_title)
        if not norm:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT notified_at FROM recent_releases
                WHERE author_name = ? AND normalized_title = ?
                ORDER BY notified_at DESC LIMIT 1
            """, (author_name.lower(), norm))
            row = cursor.fetchone()
            if not row:
                return False
            try:
                notified_dt = datetime.datetime.fromisoformat(row[0])
                now = datetime.datetime.now(datetime.timezone.utc)
                if (now - notified_dt).total_seconds() < (max_hours * 3600):
                    return True
            except Exception:
                pass
            return False

    def record_notified_release(self, author_name: str, raw_title: str):
        """Records a notification event for title deduplication across sources."""
        norm = normalize_title(raw_title)
        if not norm:
            return
        key = f"{author_name.lower()}:{norm}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO recent_releases (release_key, author_name, normalized_title, notified_at)
                VALUES (?, ?, ?, ?)
            """, (key, author_name.lower(), norm, now))
            conn.commit()

    def mark_post_seen(self, post: Dict) -> bool:
        """Marks a single post as seen. Returns True if newly inserted."""
        post_id = str(post.get("post_id", ""))
        if not post_id or self.is_post_seen(post_id):
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor.execute("""
                INSERT OR IGNORE INTO seen_posts (
                    post_id, author_id, author_name, topic_title,
                    post_subject, post_url, posted_date, first_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post_id,
                str(post.get("author_id", "")),
                post.get("author", ""),
                post.get("topic_title", ""),
                post.get("post_subject", ""),
                post.get("post_url", ""),
                post.get("posted_date", ""),
                now
            ))
            conn.commit()
            return cursor.rowcount > 0

    def mark_posts_seen_bulk(self, posts: List[Dict]) -> int:
        """Marks multiple posts as seen at once."""
        count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            for post in posts:
                post_id = str(post.get("post_id", ""))
                if not post_id:
                    continue
                cursor.execute("""
                    INSERT OR IGNORE INTO seen_posts (
                        post_id, author_id, author_name, topic_title,
                        post_subject, post_url, posted_date, first_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    post_id,
                    str(post.get("author_id", "")),
                    post.get("author", ""),
                    post.get("topic_title", ""),
                    post.get("post_subject", ""),
                    post.get("post_url", ""),
                    post.get("posted_date", ""),
                    now
                ))
                if cursor.rowcount > 0:
                    count += 1
            conn.commit()
        return count

    def is_initial_run(self, author_id: str) -> bool:
        """Checks if we have ever recorded posts for this author."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM seen_posts WHERE author_id = ? LIMIT 1", (str(author_id),))
            return cursor.fetchone() is None
