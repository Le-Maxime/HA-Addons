import html
import json
import logging
import os
import re
import datetime
from typing import Dict, Optional, Tuple, List
import requests
from storage import normalize_title, clean_game_title

logger = logging.getLogger(__name__)

KYIV_TZ = datetime.timezone(datetime.timedelta(hours=3))

IGNORED_DOWNLOAD_DOMAINS = [
    "ubisoft.com",
    "steampowered.com",
    "steamcommunity.com",
    "steamdb.info",
    "cs.rin.ru",
    "reddit.com",
    "redd.it",
    "youtube.com",
    "youtu.be",
    "discord.gg",
    "discord.com",
    "wikipedia.org",
    "twitter.com",
    "x.com"
]


def escape_html(text: str) -> str:
    if not text:
        return ""
    return html.escape(text, quote=False)


COVERS_DIR = "/data/covers"


def is_genuine_release_post(post: Dict) -> bool:
    """
    Determines if a post by voices38, Artifact, or DenuvOwO is an actual game release / crack / hypervisor / patch,
    rather than a normal forum reply / comment / bickering.
    """
    content = post.get("content_text") or ""
    topic_title = post.get("topic_title") or ""
    subject = post.get("post_subject") or ""
    full_text = f"{topic_title} {subject} {content}".lower()
    author = post.get("author", "").lower()
    author_type = post.get("author_type", "")

    # 1. Check for valid download links
    # download_links = structured (list of tuples/strings already parsed)
    # post_links = raw URL strings from csrin_client.fetch_user_posts()
    raw_download_links = list(post.get("download_links") or [])
    raw_post_links = post.get("post_links") or []
    for u in raw_post_links:
        raw_download_links.append(u)

    valid_links = []
    for item in raw_download_links:
        u = item[1] if isinstance(item, (list, tuple)) else item
        if u and not any(ign in u.lower() for ign in IGNORED_DOWNLOAD_DOMAINS):
            valid_links.append(u)

    if not valid_links:
        urls = re.findall(r'https?://[^\s<>"\')\]\}]+', content)
        for u in urls:
            u_clean = u.rstrip(".,;:)")
            if not any(ign in u_clean.lower() for ign in IGNORED_DOWNLOAD_DOMAINS):
                valid_links.append(u_clean)

    # 2. Check for BuildID / version patterns
    has_build_id = bool(re.search(r'(?:steam\s+build|buildid|build\s+id|build)(?:\s+is)?[:\s]+\d{5,}', content, re.I))
    has_version_pattern = bool(re.search(r'(?:game\s+)?(?:version|build)\s+is\s+[^\n\(\)]+', content, re.I))
    has_patchnotes = "steamdb.info/patchnotes" in content.lower()

    # 3. Check for NFO or Crack indicators
    has_nfo = any(k in full_text for k in ["nfo (text)", "nfo (image)", "pastebin.com", "ibb.co", "rentry.co"])
    has_crack_tag = any(k in full_text for k in [
        "crackfix", "only crack", "crack only", "voices38_crack",
        "hypervisor playable", "hypervisor", "denuvowo", "csf", "clean steam files"
    ])
    has_subject_release = bool(re.search(r'\b(CRACKED|CRACKFIX|HYPERVISOR|RELEASE)\b', f"{topic_title} {subject}", re.I))

    # 4. Artifact-specific detection:
    # Artifact posts contain filenames like "GameName.Crack.Only-ARTIFACT" or "GameName.Update.vX.Crack.Only-ARTIFACT"
    # These are posted in the content body without HTTP links (cs.rin.ru internal distribution)
    has_artifact_filename = bool(re.search(
        r'\w[\w.\-]+\.(?:Crack\.Only|Crackfix|Update\.v[\d.]+\.Crack\.Only)-ARTIFACT',
        content, re.I
    ))

    if valid_links:
        return True

    if has_artifact_filename:
        return True

    # Topic title pattern: "[Info]GameName [CRACKED]" or similar
    has_artifact_release_title = bool(re.search(
        r'(?:crack[.\-]only|cracked|crackfix)[.\-](?:artifact|voices38)',
        f"{topic_title} {subject}", re.I
    ))
    if has_artifact_release_title:
        return True

    if (has_build_id or has_version_pattern or has_patchnotes) and (has_nfo or has_crack_tag or has_subject_release):
        return True

    # If crack/release indicator in topic title AND any post_links exist
    if (has_crack_tag or has_subject_release) and raw_post_links:
        return True

    return False

def get_game_cover_image(game_title: str, content_text: str = "", release_id: str = "") -> Optional[str]:
    """
    Finds high-quality cover image from Steam assets.
    Caches downloaded covers to /data/covers/ to avoid repeated Steam API requests on every cycle.
    Returns local path if cached, otherwise a Steam CDN URL.
    """
    if not game_title or game_title == "Неизвестная игра":
        return None

    # Check local cache first - avoids all HTTP to Steam on subsequent cycles
    if release_id:
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', release_id)[:80]
        local_path = os.path.join(COVERS_DIR, f"{safe_id}.jpg")
        if os.path.isfile(local_path):
            return local_path

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    app_ids = []

    # 1. Direct AppID from text if present
    app_id_match = re.search(r'store\.steampowered\.com/app/(\d+)', content_text or "")
    if app_id_match:
        app_ids.append(app_id_match.group(1))

    # 2. Search Steam Store API with full game title
    try:
        search_url = f"https://store.steampowered.com/api/storesearch/?term={requests.utils.quote(game_title)}&l=english&cc=US"
        r = requests.get(search_url, headers=headers, timeout=3)
        if r.status_code == 200:
            for it in r.json().get('items', [])[:3]:
                aid = str(it.get('id'))
                if aid not in app_ids:
                    app_ids.append(aid)
    except Exception as e:
        logger.debug(f"Steam search error for {game_title}: {e}")

    found_url = None

    # 3. Check each App ID for valid cover image
    for aid in app_ids:
        candidates = [
            f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/capsule_616x353.jpg",
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/capsule_616x353.jpg",
            f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg",
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/header.jpg",
        ]
        for url in candidates:
            try:
                if requests.head(url, headers=headers, timeout=2).status_code == 200:
                    found_url = url
                    break
            except Exception:
                pass
        if found_url:
            break

        if not found_url:
            # Scrape og:image from store page if static 404s
            try:
                store_url = f"https://store.steampowered.com/app/{aid}/"
                r_page = requests.get(store_url, headers=headers, timeout=4)
                if r_page.status_code == 200:
                    m_og = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', r_page.text, re.I)
                    if m_og:
                        og_url = m_og.group(1)
                        if requests.head(og_url, headers=headers, timeout=2).status_code == 200:
                            found_url = og_url
                            break
            except Exception:
                pass

    # 4. Check if direct image in post content
    if not found_url:
        img_match = re.search(r'https?://[^\s<>"\')\]\}]+?\.(?:jpg|jpeg|png|webp)', content_text or "", re.I)
        if img_match:
            url = img_match.group(0)
            if "steamstatic.com" in url or "steamcdn" in url:
                found_url = url

    # Save to local cache if we found a URL and have a release_id
    if found_url and release_id:
        try:
            os.makedirs(COVERS_DIR, exist_ok=True)
            r_img = requests.get(found_url, headers=headers, timeout=8)
            if r_img.status_code == 200 and r_img.content:
                safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', release_id)[:80]
                local_path = os.path.join(COVERS_DIR, f"{safe_id}.jpg")
                with open(local_path, "wb") as f:
                    f.write(r_img.content)
                logger.debug(f"Cached cover for '{game_title}' → {local_path}")
                return local_path
        except Exception as e:
            logger.debug(f"Could not cache cover for {game_title}: {e}")

    return found_url



def resolve_build_release_time(game_title: str, version_str: str = "", build_id: str = "", content_text: str = "") -> Optional[str]:
    """
    Resolves the build/patch release date & time in Kyiv time (UTC+3).
    Strict: Only returns a date if a specific BuildID or version string matched.
    """
    if not build_id and not version_str:
        return None

    app_id = None
    app_id_match = re.search(r'store\.steampowered\.com/app/(\d+)', content_text or "")
    if app_id_match:
        app_id = app_id_match.group(1)
    else:
        try:
            search_url = f"https://store.steampowered.com/api/storesearch/?term={requests.utils.quote(game_title)}&l=english&cc=US"
            r = requests.get(search_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
            if r.status_code == 200:
                items = r.json().get('items', [])
                if items:
                    app_id = items[0].get('id')
        except Exception:
            pass

    if not app_id:
        return None

    try:
        news_url = f"https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid={app_id}&count=15&maxlength=200"
        r = requests.get(news_url, timeout=5)
        if r.status_code == 200:
            newsitems = r.json().get('appnews', {}).get('newsitems', [])
            clean_ver = re.sub(r'^[vV]', '', version_str or "").strip()

            for item in newsitems:
                title = item.get('title', '')
                contents = item.get('contents', '')
                if clean_ver and clean_ver in (title + " " + contents):
                    ts = item.get('date', 0)
                    dt = datetime.datetime.fromtimestamp(ts, KYIV_TZ)
                    return dt.strftime('%d.%m.%Y %H:%M')

                if build_id and build_id in (title + " " + contents):
                    ts = item.get('date', 0)
                    dt = datetime.datetime.fromtimestamp(ts, KYIV_TZ)
                    return dt.strftime('%d.%m.%Y %H:%M')
    except Exception as e:
        logger.debug(f"Error querying Steam news for {game_title}: {e}")

    return None


def parse_post_details(post: Dict) -> Tuple[str, str, List[Tuple[Optional[str], str]], Optional[str]]:
    """
    Extracts:
    1. Clean Game Title
    2. Build / Version with SteamDB patchnotes link
    3. List of (label, download_link) without unwanted official/store URLs
    4. Build Release DateTime in Kyiv time (UTC+3)
    """
    game_title = post.get("game_title")
    topic_title = post.get("topic_title") or ""
    subject = post.get("post_subject") or ""
    content_text = post.get("content_text") or ""
    author = post.get("author", "")
    author_type = post.get("author_type", "")
    if not author_type:
        author_type = "HV" if ("denuvo" in author.lower() or "artifact" in author.lower()) else ("Кряк" if "voices38" in author.lower() else "HV")

    if not game_title:
        raw_title = topic_title or subject or ""
        game_title = clean_game_title(raw_title)

        if not game_title:
            first_line = content_text.split("\n")[0] if content_text else ""
            game_title = clean_game_title(first_line)

    # Artifact-specific: extract game title from filename like "FINAL.FANTASY.RESONANCE.Crack.Only-ARTIFACT"
    # The cleaned topic/subject may still give "Неизвестная игра" if brackets-heavy; use filename as override
    if (not game_title or game_title == "Неизвестная игра") and content_text:
        artifact_m = re.search(
            r'^([A-Za-z0-9][A-Za-z0-9.\-]+?)\.(?:Crack\.Only|Crackfix|Update\.v[\d.]+\.Crack\.Only)-ARTIFACT',
            content_text, re.MULTILINE | re.IGNORECASE
        )
        if artifact_m:
            raw_fn = artifact_m.group(1).replace('.', ' ')
            game_title = raw_fn.strip()

    if not game_title:
        game_title = "Неизвестная игра"

    # 2. BuildID & Version
    build_id = None
    build_id_match = re.search(r'(?:steam\s+build|buildid|build\s+id|build)(?:\s+is)?[:\s]+(\d{5,})', content_text, re.I)
    if build_id_match:
        build_id = build_id_match.group(1)
    else:
        sdb_m = re.search(r'steamdb\.info/patchnotes/(\d+)', content_text, re.I)
        if sdb_m:
            build_id = sdb_m.group(1)

    version_str = None
    version_match = re.search(r'(?:Game\s+)?(?:version)\s+(?:is|:)?\s*([vV]?\d[\d\.]*[^\s\n\(\)]*)', content_text, re.I)
    if not version_match:
        version_match = re.search(r'(?:Game\s+)?(?:version|build)\s+is\s+([^\n\(\)]+)', content_text, re.I)
    if version_match:
        v_cand = version_match.group(1).strip()
        if not (v_cand.isdigit() and len(v_cand) >= 5):
            version_str = v_cand

    if not version_str:
        ver_fn = re.search(r'Update\.(v?[\d]+(?:\.[\d]+)*)', content_text, re.I)
        if ver_fn:
            version_str = ver_fn.group(1).rstrip('.')

    paren_version = re.search(r'\((v[\d\.]+[^\)]*)\)', content_text, re.I)
    if paren_version and not version_str:
        version_str = paren_version.group(1).strip()

    steamdb_url = f"https://steamdb.info/patchnotes/{build_id}/" if build_id else None

    if build_id and version_str:
        build_display = f"{version_str} (<a href=\"{steamdb_url}\">{build_id}</a>)"
    elif build_id:
        build_display = f"<a href=\"{steamdb_url}\">{build_id}</a>"
    elif version_str:
        build_display = f"{version_str}"
    else:
        build_display = "Не указан"

    # 3. Download Links & Context-Aware Labeling (Full Game vs Crack vs Hypervisor vs NFO)
    raw_download_links = list(post.get("download_links") or [])
    # Also include raw URL strings from csrin_client (post_links field)
    for u in (post.get("post_links") or []):
        raw_download_links.append(u)
    download_links = []

    for item in raw_download_links:
        if isinstance(item, (list, tuple)):
            lbl, u = item
        else:
            lbl, u = None, item
        if u and not any(ign in u.lower() for ign in IGNORED_DOWNLOAD_DOMAINS):
            download_links.append((lbl, u))

    if not download_links:
        raw_urls = re.findall(r'https?://[^\s<>"\'\)\]\}]+', content_text)
        seen_urls = set()

        for u in raw_urls:
            u_clean = u.rstrip(".,;:)")
            if u_clean in seen_urls:
                continue
            seen_urls.add(u_clean)

            if any(ign in u_clean.lower() for ign in IGNORED_DOWNLOAD_DOMAINS):
                continue

            # Context immediately preceding this URL in content_text
            pos = content_text.find(u)
            preceding_text = ""
            if pos != -1:
                start_pos = max(0, pos - 120)
                chunk = content_text[start_pos:pos]
                last_http = chunk.rfind("http")
                if last_http != -1:
                    chunk = chunk[last_http:]
                    chunk = re.sub(r'https?://[^\s]+', '', chunk)
                preceding_text = chunk.lower()

            label = None
            if any(k in preceding_text for k in ["nfo (text)", "pastebin.com", "rentry.co"]):
                label = "NFO (Text)"
            elif any(k in preceding_text for k in ["nfo (image)", "ibb.co"]):
                label = "NFO (Image)"
            elif any(k in preceding_text for k in ["crack only", "crack:", "только кряк", "crack only:"]):
                label = "Только кряк"
            elif any(k in preceding_text for k in ["hypervisor", "hv:", "hv "]):
                label = "Гипервизор"
            elif any(k in preceding_text for k in ["csf", "clean steam"]):
                label = "CSF"
            elif any(k in preceding_text for k in ["patch:", "патч"]):
                label = "Патч"
            elif any(k in preceding_text for k in ["update:", "обновление"]):
                label = "Обновление"
            else:
                if "pastebin.com" in u_clean or "rentry.co" in u_clean:
                    label = "NFO (Text)"
                elif "ibb.co" in u_clean or re.search(r'\.(?:png|jpg|jpeg)$', u_clean):
                    label = "NFO (Image)"
                elif author_type == "HV" or "denuvo" in author.lower() or "artifact" in author.lower():
                    label = "Гипервизор"
                else:
                    label = "Игра"

            download_links.append((label, u_clean))

    # De-duplicate and differentiate 2 file links (Full game >= 1GB vs Crack < 1GB)
    cleaned_download_links = []
    for lbl, link in download_links:
        if link and not any(ign in link.lower() for ign in IGNORED_DOWNLOAD_DOMAINS):
            cleaned_download_links.append((lbl, link))

    non_nfo = [item for item in cleaned_download_links if item[0] not in ["NFO (Text)", "NFO (Image)"]]
    if len(non_nfo) == 2 and author_type != "HV":
        l1, u1 = non_nfo[0]
        l2, u2 = non_nfo[1]
        if l1 == l2 or (l1 == "Только кряк" and l2 == "Только кряк") or (l1 == "Игра" and l2 == "Игра"):
            # First is Full Game (85+ GB), second is Crack only (< 1GB)
            idx1 = cleaned_download_links.index(non_nfo[0])
            idx2 = cleaned_download_links.index(non_nfo[1])
            cleaned_download_links[idx1] = ("Игра", u1)
            cleaned_download_links[idx2] = ("Только кряк", u2)

    # 4. Resolve Build Release Date & Time (strict match only)
    build_datetime = post.get("build_datetime") or resolve_build_release_time(game_title, version_str, build_id, content_text)

    return game_title, build_display, cleaned_download_links, build_datetime


def format_and_save_post(post: Dict, storage) -> Optional[str]:
    """
    Parses and stores a post into storage.saved_releases for catalog and inline use.
    Card Header is clean: '🎮 Взлом (Кряк)' or '🎮 Взлом (Гипервизор)' - NO 'новый релиз'.
    """
    if not storage:
        return None
    try:
        if not is_genuine_release_post(post):
            return None

        game_title, build_display, download_links, build_datetime = parse_post_details(post)

        if not game_title or game_title == "Неизвестная игра" or any(b in game_title.lower() for b in ["removed by reddit", "deleted", "removed", "bickering"]):
            return None

        post_url = post.get("post_url") or ""
        author = post.get("author", "")

        author_type = post.get("author_type")
        if not author_type:
            author_type = "HV" if ("denuvo" in author.lower() or "artifact" in author.lower()) else ("Кряк" if "voices38" in author.lower() else "HV")

        type_label = "Гипервизор" if (author_type in ["HV", "Гипервизор"] or "denuvo" in author.lower() or "artifact" in author.lower()) else "Кряк"
        type_header = f"🎮 <b>Взлом ({type_label})</b>"

        lines = [
            type_header,
            f"🎮 <b>Игра:</b> {escape_html(game_title)}",
            f"📦 <b>Билд:</b> {build_display}",
        ]

        if build_datetime:
            lines.append(f"🕒 <b>Дата билда:</b> {build_datetime} (UTC+3)")

        game_links = []
        crack_links = []
        hv_links = []
        nfo_text_links = []
        nfo_img_links = []
        other_links = []

        for label, url in download_links:
            if any(ign in url.lower() for ign in IGNORED_DOWNLOAD_DOMAINS):
                continue

            lbl = (label or "").lower()
            if "nfo (text)" in lbl or "pastebin.com" in url or "rentry.co" in url:
                nfo_text_links.append(url)
            elif "nfo (image)" in lbl or "ibb.co" in url or re.search(r'\.(?:png|jpg|jpeg)$', url):
                nfo_img_links.append(url)
            elif "crack only" in lbl or "crack" in lbl or "кряк" in lbl:
                crack_links.append(url)
            elif "hypervisor" in lbl or "hv" in lbl or "гипервизор" in lbl:
                hv_links.append(url)
            elif "csf" in lbl:
                other_links.append(("CSF", url))
            elif "patch" in lbl or "патч" in lbl:
                other_links.append(("Патч", url))
            elif "update" in lbl or "обновление" in lbl:
                other_links.append(("Обновление", url))
            elif "игра" in lbl or "game" in lbl:
                game_links.append(url)
            else:
                if type_label == "Гипервизор":
                    hv_links.append(url)
                else:
                    game_links.append(url)

        dl_parts = []
        for u in hv_links:
            dl_parts.append(f"(<a href=\"{u}\">Гипервизор</a>)")
        for u in game_links:
            dl_parts.append(f"(<a href=\"{u}\">Игра</a>)")
        for u in crack_links:
            dl_parts.append(f"(<a href=\"{u}\">Только кряк</a>)")
        for lbl, u in other_links:
            dl_parts.append(f"(<a href=\"{u}\">{lbl}</a>)")

        if dl_parts:
            lines.append(f"⬇️ <b>Скачать:</b> {' '.join(dl_parts)}")
        elif post_url and "cs.rin.ru" in post_url:
            lines.append(f"⬇️ <b>Скачать:</b> (<a href=\"{post_url}\">Ссылка в посте</a>)")

        nfo_parts = []
        for u in nfo_text_links:
            nfo_parts.append(f"(<a href=\"{u}\">Текст</a>)")
        for u in nfo_img_links:
            nfo_parts.append(f"(<a href=\"{u}\">Картинкой</a>)")

        if nfo_parts:
            lines.append(f"📄 <b>NFO:</b> {' '.join(nfo_parts)}")

        # ONLY link to cs.rin.ru
        rin_url = None
        if post_url and "cs.rin.ru" in post_url:
            rin_url = post_url
        else:
            sources = post.get("sources") or []
            for name, url in sources:
                if "cs.rin.ru" in url:
                    rin_url = url
                    break

        if rin_url:
            lines.append(f"\n🔗 <a href=\"{rin_url}\">Открыть на cs.rin.ru</a>")

        message_text = "\n".join(lines)

        norm_key = normalize_title(game_title)
        if not norm_key:
            return None
        # Use short ASCII prefix so callback_data stays well under Telegram's 64-byte limit
        prefix = "hv" if type_label == "Гипервизор" else "cr"
        rel_id = f"{prefix}_{norm_key[:55]}"

        # Fetch cover, using local cache first (avoids repeated Steam API calls every cycle)
        existing_cover = post.get("cover_image")
        if existing_cover and (os.path.isfile(existing_cover) or existing_cover.startswith("http")):
            cover_image = existing_cover
        else:
            cover_image = get_game_cover_image(game_title, post.get("content_text", ""), release_id=rel_id)

        storage.save_release(
            release_id=rel_id,
            game_title=game_title,
            author_name=author,
            author_type=type_label,
            is_update=bool(post.get("is_update", False)),
            build_display=build_display,
            build_datetime=build_datetime,
            cover_image=cover_image,
            message_text=message_text
        )
        return rel_id
    except Exception as e:
        logger.debug(f"Error in format_and_save_post: {e}")
        return None


class TelegramNotifier:
    """Sends notifications via Telegram Bot API with cover image, build time, multi-chat and inline support."""

    def __init__(self, bot_token: str, default_chat_id: str, storage=None):
        self.bot_token = bot_token.strip()
        self.default_chat_id = str(default_chat_id).strip()
        self.storage = storage
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        self.photo_url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"

    def get_recipient_chats(self) -> List[str]:
        """Gets all approved subscribers from storage or defaults to default_chat_id."""
        if self.storage:
            try:
                subs = self.storage.get_allowed_subscribers()
                if subs:
                    return subs
            except Exception as e:
                logger.error(f"Error getting subscribers from storage: {e}")
        return [self.default_chat_id] if self.default_chat_id else []

    def send_photo_to_chat(self, chat_id: str, photo: str, caption: str, parse_mode: str = "HTML", reply_markup: Optional[Dict] = None) -> bool:
        if not self.bot_token or not chat_id or not photo:
            return False

        # Telegram caps photo captions at 1024 bytes
        if caption:
            encoded = caption.encode("utf-8")
            if len(encoded) > 1024:
                caption = encoded[:1020].decode("utf-8", errors="ignore").rstrip() + "..."

        try:
            if os.path.isfile(photo):
                # Local cached file — upload via multipart/form-data
                data = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": parse_mode,
                }
                if reply_markup:
                    data["reply_markup"] = json.dumps(reply_markup)
                with open(photo, "rb") as f:
                    resp = requests.post(self.photo_url, data=data, files={"photo": ("cover.jpg", f, "image/jpeg")}, timeout=20)
            else:
                # Remote URL — send as JSON
                payload = {
                    "chat_id": chat_id,
                    "photo": photo,
                    "caption": caption,
                    "parse_mode": parse_mode,
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                resp = requests.post(self.photo_url, json=payload, timeout=12)

            if resp.status_code == 200:
                logger.info(f"Telegram photo notification sent to {chat_id}")
                return True
            else:
                logger.warning(f"sendPhoto to {chat_id} failed (HTTP {resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            logger.warning(f"Error calling sendPhoto for {chat_id}: {e}")
            return False

    def send_message_to_chat(self, chat_id: str, text: str, parse_mode: str = "HTML", disable_web_page_preview: bool = False, reply_markup: Optional[Dict] = None) -> bool:
        if not self.bot_token or not chat_id:
            return False

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            resp = requests.post(self.api_url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"Telegram text notification sent to {chat_id}")
                return True
            else:
                logger.error(f"Failed to send Telegram message to {chat_id}: HTTP {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Error sending Telegram message to {chat_id}: {e}")
            return False

    def notify_new_post(self, post: Dict, max_content_length: int = 1500) -> bool:
        if not is_genuine_release_post(post):
            return False

        # Save to database first
        format_and_save_post(post, self.storage)

        game_title, build_display, download_links, build_datetime = parse_post_details(post)
        if not game_title or game_title == "Неизвестная игра" or any(b in game_title.lower() for b in ["removed by reddit", "deleted", "removed", "bickering"]):
            return False

        post_url = post.get("post_url") or ""
        author = post.get("author", "")

        author_type = post.get("author_type")
        if not author_type:
            author_type = "HV" if ("denuvo" in author.lower() or "artifact" in author.lower()) else ("Кряк" if "voices38" in author.lower() else "HV")

        type_label = "Гипервизор" if (author_type in ["HV", "Гипервизор"] or "denuvo" in author.lower() or "artifact" in author.lower()) else "Кряк"

        is_update = post.get("is_update", False)
        if not is_update:
            content_lower = (post.get("content_text") or "").lower()
            if any(w in content_lower for w in ["hotfix", "fixed link", "update", "patch", "crackfix"]):
                is_update = True

        status_word = "Обновление" if is_update else "Новый релиз"
        type_icon = "🔄" if is_update else "🆕"
        type_header = f"{type_icon} <b>{status_word} ({type_label})</b>"

        lines = [
            type_header,
            f"🎮 <b>Игра:</b> {escape_html(game_title)}",
            f"📦 <b>Билд:</b> {build_display}",
        ]

        if build_datetime:
            lines.append(f"🕒 <b>Дата билда:</b> {build_datetime} (UTC+3)")

        game_links = []
        crack_links = []
        hv_links = []
        nfo_text_links = []
        nfo_img_links = []
        other_links = []

        for label, url in download_links:
            if any(ign in url.lower() for ign in IGNORED_DOWNLOAD_DOMAINS):
                continue

            lbl = (label or "").lower()
            if "nfo (text)" in lbl or "pastebin.com" in url or "rentry.co" in url:
                nfo_text_links.append(url)
            elif "nfo (image)" in lbl or "ibb.co" in url or re.search(r'\.(?:png|jpg|jpeg)$', url):
                nfo_img_links.append(url)
            elif "crack only" in lbl or "crack" in lbl or "кряк" in lbl:
                crack_links.append(url)
            elif "hypervisor" in lbl or "hv" in lbl or "гипервизор" in lbl:
                hv_links.append(url)
            elif "csf" in lbl:
                other_links.append(("CSF", url))
            elif "patch" in lbl or "патч" in lbl:
                other_links.append(("Патч", url))
            elif "update" in lbl or "обновление" in lbl:
                other_links.append(("Обновление", url))
            elif "игра" in lbl or "game" in lbl:
                game_links.append(url)
            else:
                if type_label == "Гипервизор":
                    hv_links.append(url)
                else:
                    game_links.append(url)

        dl_parts = []
        for u in hv_links:
            dl_parts.append(f"(<a href=\"{u}\">Гипервизор</a>)")
        for u in game_links:
            dl_parts.append(f"(<a href=\"{u}\">Игра</a>)")
        for u in crack_links:
            dl_parts.append(f"(<a href=\"{u}\">Только кряк</a>)")
        for lbl, u in other_links:
            dl_parts.append(f"(<a href=\"{u}\">{lbl}</a>)")

        if dl_parts:
            lines.append(f"⬇️ <b>Скачать:</b> {' '.join(dl_parts)}")
        elif post_url and "cs.rin.ru" in post_url:
            lines.append(f"⬇️ <b>Скачать:</b> (<a href=\"{post_url}\">Ссылка в посте</a>)")

        nfo_parts = []
        for u in nfo_text_links:
            nfo_parts.append(f"(<a href=\"{u}\">Текст</a>)")
        for u in nfo_img_links:
            nfo_parts.append(f"(<a href=\"{u}\">Картинкой</a>)")

        if nfo_parts:
            lines.append(f"📄 <b>NFO:</b> {' '.join(nfo_parts)}")

        # ONLY link to cs.rin.ru
        rin_url = None
        if post_url and "cs.rin.ru" in post_url:
            rin_url = post_url
        else:
            sources = post.get("sources") or []
            for name, url in sources:
                if "cs.rin.ru" in url:
                    rin_url = url
                    break

        if rin_url:
            lines.append(f"\n🔗 <a href=\"{rin_url}\">Открыть на cs.rin.ru</a>")

        message_text = "\n".join(lines)

        # Resolve cover from cache using consistent release_id
        norm_key = normalize_title(game_title)
        rel_id_for_cover = f"{'hv' if type_label == 'Гипервизор' else 'cr'}_{norm_key[:55]}"
        existing_cover = post.get("cover_image")
        if existing_cover and (os.path.isfile(existing_cover) or existing_cover.startswith("http")):
            cover_image = existing_cover
        else:
            cover_image = get_game_cover_image(game_title, post.get("content_text", ""), release_id=rel_id_for_cover)

        recipients = self.get_recipient_chats()
        if not recipients:
            logger.warning("No approved recipients configured for Telegram notification.")
            return False

        any_success = False
        for chat_id in recipients:
            sent = False
            if cover_image:
                sent = self.send_photo_to_chat(chat_id, cover_image, caption=message_text, parse_mode="HTML")
            if not sent:
                sent = self.send_message_to_chat(chat_id, message_text, parse_mode="HTML")
            if sent:
                any_success = True

        return any_success


class DiscordNotifier:
    """Sends notifications via Discord Webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url.strip()

    def send_post(self, post: Dict, max_content_length: int = 1500) -> bool:
        if not self.webhook_url or not is_genuine_release_post(post):
            return False

        game_title, build_display, download_links, build_datetime = parse_post_details(post)
        if not game_title or game_title == "Неизвестная игра" or any(b in game_title.lower() for b in ["removed by reddit", "deleted", "removed", "bickering"]):
            return False

        post_url = post.get("post_url") or ""
        author = post.get("author", "")

        author_type = post.get("author_type")
        if not author_type:
            author_type = "HV" if ("denuvo" in author.lower() or "artifact" in author.lower()) else ("Кряк" if "voices38" in author.lower() else "HV")

        type_label = "Гипервизор" if (author_type in ["HV", "Гипервизор"] or "denuvo" in author.lower() or "artifact" in author.lower()) else "Кряк"

        is_update = post.get("is_update", False)
        status_word = "Обновление" if is_update else "Новый релиз"
        type_str = f"{status_word} ({type_label})"

        desc_lines = [
            f"**Тип:** {type_str}",
            f"**Игра:** {game_title}",
            f"**Билд:** {re.sub(r'<[^>]+>', '', build_display)}",
        ]

        if build_datetime:
            desc_lines.append(f"**Дата билда:** {build_datetime} (UTC+3)")

        game_links = []
        crack_links = []
        hv_links = []
        nfo_text_links = []
        nfo_img_links = []
        other_links = []

        for label, url in download_links:
            if any(ign in url.lower() for ign in IGNORED_DOWNLOAD_DOMAINS):
                continue

            lbl = (label or "").lower()
            if "nfo (text)" in lbl or "pastebin.com" in url or "rentry.co" in url:
                nfo_text_links.append(url)
            elif "nfo (image)" in lbl or "ibb.co" in url or re.search(r'\.(?:png|jpg|jpeg)$', url):
                nfo_img_links.append(url)
            elif "crack only" in lbl or "crack" in lbl or "кряк" in lbl:
                crack_links.append(url)
            elif "hypervisor" in lbl or "hv" in lbl or "гипервизор" in lbl:
                hv_links.append(url)
            elif "csf" in lbl:
                other_links.append(("CSF", url))
            elif "patch" in lbl or "патч" in lbl:
                other_links.append(("Патч", url))
            elif "update" in lbl or "обновление" in lbl:
                other_links.append(("Обновление", url))
            elif "игра" in lbl or "game" in lbl:
                game_links.append(url)
            else:
                if type_label == "Гипервизор":
                    hv_links.append(url)
                else:
                    game_links.append(url)

        dl_parts = []
        for u in hv_links:
            dl_parts.append(f"([Гипервизор]({u}))")
        for u in game_links:
            dl_parts.append(f"([Игра]({u}))")
        for u in crack_links:
            dl_parts.append(f"([Только кряк]({u}))")
        for lbl, u in other_links:
            dl_parts.append(f"([{lbl}]({u}))")

        if dl_parts:
            desc_lines.append(f"**Скачать:** {' '.join(dl_parts)}")
        elif post_url and "cs.rin.ru" in post_url:
            desc_lines.append(f"**Скачать:** ([Ссылка в посте]({post_url}))")

        nfo_parts = []
        for u in nfo_text_links:
            desc_lines.append(f"([Текст]({u}))")
        for u in nfo_img_links:
            desc_lines.append(f"([Картинкой]({u}))")

        if nfo_parts:
            desc_lines.append(f"**NFO:** {' '.join(nfo_parts)}")

        # ONLY link to cs.rin.ru
        rin_url = None
        if post_url and "cs.rin.ru" in post_url:
            rin_url = post_url
        else:
            sources = post.get("sources") or []
            for name, url in sources:
                if "cs.rin.ru" in url:
                    rin_url = url
                    break

        if rin_url:
            desc_lines.append(f"\n**Открыть:** [cs.rin.ru]({rin_url})")

        cover_image = post.get("cover_image") or get_game_cover_image(game_title, post.get("content_text", ""))

        embed = {
            "title": f"🎮 {type_str}: {game_title}",
            "url": rin_url or "https://cs.rin.ru/forum/",
            "color": 0x3498db if is_update else 0x2ecc71,
            "description": "\n".join(desc_lines),
            "footer": {
                "text": f"{author} • {post.get('posted_date', '')}"
            }
        }
        if cover_image:
            embed["image"] = {"url": cover_image}

        try:
            resp = requests.post(self.webhook_url, json={"embeds": [embed]}, timeout=10)
            return resp.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Error sending Discord webhook: {e}")
            return False


class NotificationManager:
    """Dispatches notifications to configured channels."""

    def __init__(self, telegram_token: str = "", telegram_chat_id: str = "", discord_webhook: str = "", storage=None):
        self.telegram_notifier: Optional[TelegramNotifier] = None
        self.discord_notifier: Optional[DiscordNotifier] = None

        if telegram_token and telegram_chat_id:
            self.telegram_notifier = TelegramNotifier(telegram_token, telegram_chat_id, storage=storage)

        if discord_webhook:
            self.discord_notifier = DiscordNotifier(discord_webhook)

    def notify(self, post: Dict):
        if self.telegram_notifier:
            self.telegram_notifier.notify_new_post(post)
        if self.discord_notifier:
            self.discord_notifier.send_post(post)
