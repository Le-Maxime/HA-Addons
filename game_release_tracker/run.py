import os
import time
import json
import logging
import re
from typing import List, Dict

from csrin_client import CSRinClient
from reddit_client import RedditUserClient
from storage import PostStorage, normalize_title, clean_game_title
from notifier import NotificationManager, parse_post_details, format_and_save_post, is_genuine_release_post
from telegram_listener import TelegramListener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ReleaseTracker")


def load_ha_options() -> Dict:
    """Loads addon options from Home Assistant config file if available."""
    options_path = "/data/options.json"
    if os.path.exists(options_path):
        try:
            with open(options_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not read options from {options_path}: {e}")

    # Fallback to environment variables
    return {
        "check_interval_seconds": os.getenv("CHECK_INTERVAL_SECONDS", "120"),
        "telegram_token": os.getenv("TELEGRAM_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "discord_webhook": os.getenv("DISCORD_WEBHOOK", ""),
        "csrinru_phpbb3_u": os.getenv("CSRIN_COOKIE_U", ""),
        "csrinru_phpbb3_k": os.getenv("CSRIN_COOKIE_K", ""),
        "csrinru_phpbb3_sid": os.getenv("CSRIN_COOKIE_SID", ""),
        "securitytoken": os.getenv("CSRIN_SECURITY_TOKEN", ""),
        "securitytoken_expiration": os.getenv("CSRIN_SECURITY_EXP", ""),
    }


def sync_all_catalog_releases(
    denuvo_posts: List[Dict],
    voices_rin_posts: List[Dict],
    reddit_posts: List[Dict],
    artifact_posts: List[Dict],
    storage: PostStorage
):
    """
    Indexes and unifies all historical and current releases into storage.saved_releases.
    Merges Reddit (NFO/artwork/links) and cs.rin.ru (builds/patchnotes/direct links) into a single game card.
    Directs all topic links ONLY to cs.rin.ru.
    """
    # 1. DenuvOwO (Гипервизор)
    for p in denuvo_posts:
        p["author_type"] = "HV"
        p["author"] = "DenuvOwO"
        if is_genuine_release_post(p):
            format_and_save_post(p, storage)

    # 2. voices38 (Кряк) — Merge across Rin and Reddit
    _sync_crack_author_catalog(
        author_name="voices38",
        rin_posts=voices_rin_posts,
        reddit_posts=reddit_posts,
        storage=storage
    )

    # 3. Artifact (Гипервизор) — only cs.rin.ru
    _sync_crack_author_catalog(
        author_name="Artifact",
        rin_posts=artifact_posts,
        reddit_posts=[],
        storage=storage,
        author_type="HV"
    )


def _sync_crack_author_catalog(
    author_name: str,
    rin_posts: List[Dict],
    reddit_posts: List[Dict],
    storage: PostStorage,
    author_type: str = "Кряк"
):
    """Indexes crack releases for one author into saved_releases, merging rin + reddit by game title."""
    grouped = {}
    for p in rin_posts:
        if not is_genuine_release_post(p):
            continue
        title, build_disp, dls, dt = parse_post_details(p)
        clean_t = clean_game_title(title)
        if not clean_t:
            continue
        norm = normalize_title(clean_t)
        if norm not in grouped:
            grouped[norm] = {"rin": [], "reddit": [], "game_title": clean_t}
        grouped[norm]["rin"].append(p)

    for p in reddit_posts:
        if not is_genuine_release_post(p):
            continue
        title, build_disp, dls, dt = parse_post_details(p)
        clean_t = clean_game_title(title)
        if not clean_t:
            continue
        norm = normalize_title(clean_t)
        if norm not in grouped:
            grouped[norm] = {"rin": [], "reddit": [], "game_title": clean_t}
        grouped[norm]["reddit"].append(p)

    for norm_key, group in grouped.items():
        rin_list = group["rin"]
        reddit_list = group["reddit"]
        game_title = group["game_title"]

        base_post = rin_list[0] if rin_list else reddit_list[0]
        _, build_disp, direct_links, build_datetime = parse_post_details(base_post)

        combined_links = list(direct_links)
        seen_links = {u for lbl, u in direct_links}

        for p in rin_list + reddit_list:
            _, b_disp, _, b_dt = parse_post_details(p)
            if b_disp and b_disp != "Не указан":
                build_disp = b_disp
            if b_dt:
                build_datetime = b_dt

        sources = []
        if rin_list:
            sources.append(("cs.rin.ru", rin_list[0].get("post_url")))
            for rp in rin_list:
                _, _, r_links, _ = parse_post_details(rp)
                for lbl, u in r_links:
                    if u not in seen_links:
                        seen_links.add(u)
                        combined_links.append((lbl, u))

        if reddit_list:
            for red_p in reddit_list:
                _, _, red_links, _ = parse_post_details(red_p)
                for lbl, u in red_links:
                    if u not in seen_links:
                        seen_links.add(u)
                        combined_links.append((lbl, u))

        merged_post = {
            "game_title": game_title,
            "author": author_name,
            "author_id": author_name,
            "author_type": author_type,
            "is_update": False,
            "post_url": rin_list[0].get("post_url") if rin_list else "",
            "content_text": base_post.get("content_text"),
            "download_links": combined_links,
            "build_datetime": build_datetime,
            "sources": sources
        }
        format_and_save_post(merged_post, storage)


def process_crack_author_updates(
    author_name: str,
    author_id: str,
    new_rin_posts: List[Dict],
    new_reddit_posts: List[Dict],
    storage: PostStorage,
    notifier: NotificationManager,
    author_type: str = "Кряк"
):
    """
    Generic handler for a crack author (voices38, Artifact, etc.).
    Groups new genuine release posts by normalized game title, merges rin + reddit,
    notifies once per game, marks all individual posts seen.
    """
    grouped_by_game = {}

    for p in new_rin_posts:
        if not is_genuine_release_post(p):
            storage.mark_post_seen(p)
            continue
        title = p.get("game_title") or p.get("topic_title") or p.get("post_subject") or "Неизвестная игра"
        clean_t = clean_game_title(title)
        if not clean_t:
            storage.mark_post_seen(p)
            continue
        norm_key = normalize_title(clean_t)
        if norm_key not in grouped_by_game:
            grouped_by_game[norm_key] = {"rin": [], "reddit": [], "sample_title": clean_t}
        grouped_by_game[norm_key]["rin"].append(p)

    for p in new_reddit_posts:
        if not is_genuine_release_post(p):
            storage.mark_post_seen(p)
            continue
        title = p.get("game_title") or p.get("post_subject") or "Неизвестная игра"
        clean_t = clean_game_title(title)
        if not clean_t:
            storage.mark_post_seen(p)
            continue
        norm_key = normalize_title(clean_t)
        if norm_key not in grouped_by_game:
            grouped_by_game[norm_key] = {"rin": [], "reddit": [], "sample_title": clean_t}
        grouped_by_game[norm_key]["reddit"].append(p)

    for norm_key, group in grouped_by_game.items():
        rin_list = group["rin"]
        reddit_list = group["reddit"]
        sample_title = group["sample_title"]

        is_recently_notified = storage.is_game_recently_notified(author_name, sample_title, max_hours=12)

        base_post = rin_list[0] if rin_list else reddit_list[0]
        game_title, build_disp, direct_links, build_datetime = parse_post_details(base_post)

        combined_links = list(direct_links)
        seen_links = {u for lbl, u in direct_links}

        for p in rin_list + reddit_list:
            _, b_disp, _, b_dt = parse_post_details(p)
            if b_disp and b_disp != "Не указан":
                build_disp = b_disp
            if b_dt:
                build_datetime = b_dt

        sources = []
        if rin_list:
            sources.append(("cs.rin.ru", rin_list[0].get("post_url")))
            for rp in rin_list:
                _, _, r_links, _ = parse_post_details(rp)
                for lbl, u in r_links:
                    if u not in seen_links:
                        seen_links.add(u)
                        combined_links.append((lbl, u))

        if reddit_list:
            for red_p in reddit_list:
                _, _, red_links, _ = parse_post_details(red_p)
                for lbl, u in red_links:
                    if u not in seen_links:
                        seen_links.add(u)
                        combined_links.append((lbl, u))

        # Check if this is an update (topic already seen before)
        is_update = False
        if rin_list:
            is_update = storage.has_seen_topic(author_id, rin_list[0].get("topic_title", ""), rin_list[0].get("post_url", ""))
        elif reddit_list:
            is_update = storage.is_post_seen(reddit_list[0].get("post_id"))

        merged_post = {
            "game_title": game_title,
            "author": author_name,
            "author_id": author_id,
            "author_type": author_type,
            "is_update": is_update,
            "post_url": rin_list[0].get("post_url") if rin_list else "",
            "content_text": base_post.get("content_text"),
            "download_links": combined_links,
            "build_datetime": build_datetime,
            "sources": sources
        }

        format_and_save_post(merged_post, storage)

        if not is_recently_notified:
            logger.info(f"Notifying {author_name} release: {game_title} (Sources: {[s[0] for s in sources]})")
            notifier.notify(merged_post)
            storage.record_notified_release(author_name, sample_title)
        else:
            logger.info(f"{author_name} release '{game_title}' already notified recently. Skipping spam.")

        for p in (rin_list + reddit_list):
            storage.mark_post_seen(p)


def main():
    logger.info("Starting Release Tracker (DenuvOwO HV + Artifact HV + voices38 Crack) Home Assistant Add-on...")

    options = load_ha_options()

    check_interval = int(options.get("check_interval_seconds", 120))
    telegram_token = str(options.get("telegram_token", "")).strip()
    telegram_chat_id = str(options.get("telegram_chat_id", "")).strip()
    discord_webhook = str(options.get("discord_webhook", "")).strip()

    # Build auth cookies from options
    cookies = {}
    for key in ["csrinru_phpbb3_u", "csrinru_phpbb3_k", "csrinru_phpbb3_sid", "securitytoken", "securitytoken_expiration"]:
        val = options.get(key)
        if val and str(val).strip():
            cookies[key] = str(val).strip()

    auth_config = {"cookies": cookies} if cookies else None

    logger.info(f"Check Interval: {check_interval} seconds")
    logger.info(f"Telegram Configured: {bool(telegram_token and telegram_chat_id)}")

    if not (telegram_token and telegram_chat_id) and not discord_webhook:
        logger.warning("No notification channels configured! Please specify telegram_token & telegram_chat_id (or discord_webhook) in the Add-on Configuration tab.")

    if not auth_config:
        logger.warning("No cs.rin.ru cookies configured. The bot will run in guest mode, which may hit search flood limits frequently. See Documentation tab for cookie setup instructions.")

    csrin_client = CSRinClient(auth_config=auth_config)
    reddit_client = RedditUserClient(username="voices38", author_type="Кряк")

    db_path = "/data/tracker.db" if os.path.exists("/data") else "tracker.db"
    storage = PostStorage(db_path)
    storage.ensure_admin(telegram_chat_id)

    notifier = NotificationManager(
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
        discord_webhook=discord_webhook,
        storage=storage
    )

    # Start Telegram background listener for access control, group requests, and interactive catalog
    if telegram_token and telegram_chat_id:
        listener = TelegramListener(
            bot_token=telegram_token,
            admin_id=telegram_chat_id,
            storage=storage,
            notifier=notifier.telegram_notifier
        )
        listener.start()

    logger.info("Beginning monitoring loop...")
    while True:
        try:
            denuvo_posts = []
            voices_rin_posts = []
            reddit_posts = []
            artifact_posts = []

            # 1. Check DenuvOwO (cs.rin.ru author_id = 3625690)
            logger.info("Checking cs.rin.ru for DenuvOwO (ID: 3625690)...")
            try:
                denuvo_posts = csrin_client.fetch_user_posts(author_id="3625690")
                if denuvo_posts and storage.is_initial_run("3625690"):
                    logger.info(f"First run for DenuvOwO: indexed {len(denuvo_posts)} existing posts.")
                    storage.mark_posts_seen_bulk(denuvo_posts)
            except Exception as e:
                logger.error(f"Error checking DenuvOwO on cs.rin.ru: {e}")

            # 2. Check voices38 on cs.rin.ru (author_id = 885704)
            new_voices_rin = []
            logger.info("Checking cs.rin.ru for voices38 (ID: 885704)...")
            try:
                voices_rin_posts = csrin_client.fetch_user_posts(author_id="885704")
                if voices_rin_posts:
                    if storage.is_initial_run("885704"):
                        logger.info(f"First run for voices38 (cs.rin.ru): indexed {len(voices_rin_posts)} existing posts.")
                        storage.mark_posts_seen_bulk(voices_rin_posts)
                    else:
                        for p in voices_rin_posts:
                            if not storage.is_post_seen(p.get("post_id")):
                                if is_genuine_release_post(p):
                                    new_voices_rin.append(p)
                                else:
                                    logger.info(f"Skipping non-release discussion comment by voices38 (Post ID {p.get('post_id')})")
                                    storage.mark_post_seen(p)
            except Exception as e:
                logger.error(f"Error checking voices38 on cs.rin.ru: {e}")

            # 3. Check voices38 on Reddit
            new_voices_reddit = []
            logger.info("Checking Reddit for voices38 (/u/voices38)...")
            try:
                reddit_posts = reddit_client.fetch_posts()
                if reddit_posts:
                    if storage.is_initial_run("voices38_reddit"):
                        logger.info(f"First run for voices38 (Reddit): indexed {len(reddit_posts)} existing posts.")
                        storage.mark_posts_seen_bulk(reddit_posts)
                        storage.mark_post_seen({"post_id": "voices38_reddit_init", "author_id": "voices38_reddit"})
                    else:
                        for p in reddit_posts:
                            if not storage.is_post_seen(p.get("post_id")):
                                if is_genuine_release_post(p):
                                    new_voices_reddit.append(p)
                                else:
                                    logger.info(f"Skipping non-release Reddit post by voices38 (Post ID {p.get('post_id')})")
                                    storage.mark_post_seen(p)
            except Exception as e:
                logger.error(f"Error checking voices38 on Reddit: {e}")

            # 4. Check Artifact on cs.rin.ru (author_id = 3880030)
            new_artifact_rin = []
            logger.info("Checking cs.rin.ru for Artifact (ID: 3880030)...")
            try:
                artifact_posts = csrin_client.fetch_user_posts(author_id="3880030")
                if artifact_posts:
                    if storage.is_initial_run("3880030"):
                        logger.info(f"First run for Artifact (cs.rin.ru): indexed {len(artifact_posts)} existing posts.")
                        storage.mark_posts_seen_bulk(artifact_posts)
                    else:
                        for p in artifact_posts:
                            p["author"] = "Artifact"
                            p["author_type"] = "HV"
                            if not storage.is_post_seen(p.get("post_id")):
                                if is_genuine_release_post(p):
                                    new_artifact_rin.append(p)
                                else:
                                    logger.info(f"Skipping non-release comment by Artifact (Post ID {p.get('post_id')})")
                                    storage.mark_post_seen(p)
            except Exception as e:
                logger.error(f"Error checking Artifact on cs.rin.ru: {e}")

            # 5. Synchronize & Unify ALL Releases into Catalog (only when data available, skips flood-limit cycles)
            if denuvo_posts or voices_rin_posts or reddit_posts or artifact_posts:
                try:
                    sync_all_catalog_releases(denuvo_posts, voices_rin_posts, reddit_posts, artifact_posts, storage)
                except Exception as e:
                    logger.error(f"Error in sync_all_catalog_releases: {e}")

            # 6. Process new DenuvOwO posts
            if denuvo_posts and not storage.is_initial_run("3625690"):
                new_denuvo = [p for p in denuvo_posts if not storage.is_post_seen(p.get("post_id"))]
                for post in reversed(new_denuvo):
                    if not is_genuine_release_post(post):
                        logger.info(f"Skipping non-release comment by DenuvOwO (Post ID {post.get('post_id')})")
                        storage.mark_post_seen(post)
                        continue
                    is_update = storage.has_seen_topic("3625690", post.get("topic_title", ""), post.get("post_url", ""))
                    post["is_update"] = is_update
                    logger.info(f"Notifying DenuvOwO post #{post.get('post_id')} (Update={is_update})")
                    notifier.notify(post)
                    storage.mark_post_seen(post)

            # 7. Process new voices38 updates (Rin + Reddit merged)
            if new_voices_rin or new_voices_reddit:
                logger.info(f"Processing genuine voices38 updates: {len(new_voices_rin)} Rin post(s), {len(new_voices_reddit)} Reddit post(s)")
                process_crack_author_updates("voices38", "885704", new_voices_rin, new_voices_reddit, storage, notifier)

            # 8. Process new Artifact updates
            if new_artifact_rin:
                logger.info(f"Processing genuine Artifact updates: {len(new_artifact_rin)} Rin post(s)")
                process_crack_author_updates("Artifact", "3880030", new_artifact_rin, [], storage, notifier, author_type="HV")

        except Exception as e:
            logger.error(f"Unexpected error in monitoring cycle: {e}", exc_info=True)

        logger.info(f"Sleeping for {check_interval} seconds...")
        time.sleep(check_interval)


if __name__ == "__main__":
    main()
