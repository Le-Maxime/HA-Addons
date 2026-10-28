import subprocess
import xml.etree.ElementTree as ET
import logging
import re
import sys
import requests
from bs4 import BeautifulSoup
from typing import List, Dict

logger = logging.getLogger(__name__)


class RedditUserClient:
    """Client for tracking Reddit user submissions using RSS/Atom feed."""

    def __init__(self, username: str = "voices38", author_type: str = "Кряк"):
        self.username = username
        self.author_type = author_type
        self.rss_url = f"https://www.reddit.com/user/{username}/submitted/.rss"

    def _fetch_xml(self) -> str:
        # Use curl directly as primary method to match browser TLS fingerprint
        try:
            cmd = [
                "curl.exe" if sys.platform == "win32" else "curl",
                "-s", "-L",
                "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
                self.rss_url
            ]
            raw = subprocess.check_output(cmd, timeout=15).decode("utf-8", errors="ignore")
            if "<feed" in raw:
                return raw
        except Exception as e:
            logger.warning(f"curl fetch error for reddit user {self.username}: {e}")

        # Fallback to requests if curl fails
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            resp = requests.get(self.rss_url, headers=headers, timeout=10)
            if resp.status_code == 200 and "<feed" in resp.text:
                return resp.text
        except Exception:
            pass

        return ""

    def fetch_posts(self) -> List[Dict]:
        raw_xml = self._fetch_xml()
        if not raw_xml:
            logger.warning(f"Failed to retrieve RSS feed for reddit user {self.username}.")
            return []

        try:
            root = ET.fromstring(raw_xml)
        except Exception as e:
            logger.error(f"Error parsing Reddit XML for {self.username}: {e}")
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        posts = []
        for e in entries:
            title_el = e.find("atom:title", ns)
            raw_title = title_el.text if title_el is not None else ""

            link_el = e.find("atom:link", ns)
            post_url = link_el.get("href") if link_el is not None else ""

            id_el = e.find("atom:id", ns)
            post_id = id_el.text if id_el is not None else post_url

            content_el = e.find("atom:content", ns)
            content_html = content_el.text if content_el is not None else ""

            c_soup = BeautifulSoup(content_html, "html.parser")
            content_text = c_soup.get_text("\n", strip=True)

            # Skip removed posts
            if "Removed by Reddit" in content_text and not raw_title:
                continue

            # Extract download / nfo / steam links
            download_links = []
            for a in c_soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if "reddit.com" not in href and not href.startswith("#"):
                    download_links.append((text or "Ссылка", href))

            # Clean game title
            game_title = re.sub(r'-(?:voices38|CRACKFIX|voices38_crack)\b', '', raw_title, flags=re.I)
            game_title = game_title.replace(".", " ").strip()

            # Check if update / crackfix
            is_update = bool(re.search(r'\b(CRACKFIX|Update|Fixed|Fix|Patch|Hotfix)\b', raw_title + " " + content_text, re.I))

            posts.append({
                "post_id": post_id,
                "author": self.username,
                "author_id": self.username,
                "author_type": self.author_type,
                "game_title": game_title,
                "topic_title": raw_title,
                "post_subject": raw_title,
                "post_url": post_url,
                "content_text": content_text,
                "download_links": download_links,
                "is_update": is_update,
                "source": "reddit"
            })

        return posts
