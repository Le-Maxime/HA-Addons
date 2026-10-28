import re
import logging
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from typing import Dict, Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class CSRinClient:
    """Client for fetching and parsing data from cs.rin.ru forum with anti-bot challenge bypass and auth support."""

    BASE_URL = "https://cs.rin.ru/forum/"

    def __init__(self, user_agent: Optional[str] = None, timeout: int = 20, auth_config: Optional[Dict] = None):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Connection": "keep-alive",
        })

        self._apply_auth_cookies(auth_config)

    def _apply_auth_cookies(self, auth_config: Optional[Dict]):
        if not auth_config:
            return

        # Raw cookie string
        raw_cookie_str = auth_config.get("cookie_string", "").strip()
        if raw_cookie_str:
            for item in raw_cookie_str.split(";"):
                if "=" in item:
                    name, value = item.strip().split("=", 1)
                    self.session.cookies.set(name.strip(), value.strip(), domain="cs.rin.ru", path="/")
            logger.info("Custom cookie string applied to session.")

        # Dict of individual cookies
        cookies_dict = auth_config.get("cookies", {})
        for name, value in cookies_dict.items():
            if value and str(value).strip():
                self.session.cookies.set(name.strip(), str(value).strip(), domain="cs.rin.ru", path="/")
                logger.info(f"Applied auth cookie: {name}")

    def _bypass_security(self, resp_text: str, target_url: str) -> requests.Response:
        """Parses security token from 401 response and requests /securitycheck endpoint."""
        token_match = re.search(r'securitytoken=([^\s;"]+)', resp_text)
        exp_match = re.search(r'securitytoken_expiration=([^\s;"]+)', resp_text)

        if not (token_match and exp_match):
            raise RuntimeError("Failed to find security token in cs.rin.ru 401 response.")

        token = token_match.group(1)
        exp = exp_match.group(1)
        logger.info(f"Received security challenge. Handshaking token (exp={exp})...")

        self.session.cookies.set("securitytoken", token, domain="cs.rin.ru", path="/")
        self.session.cookies.set("securitytoken_expiration", exp, domain="cs.rin.ru", path="/")

        parsed = urlparse(target_url)
        check_path = "/securitycheck" + parsed.path
        check_url = urlunparse((parsed.scheme, parsed.netloc, check_path, parsed.params, parsed.query, parsed.fragment))

        resp = self.session.get(check_url, allow_redirects=True, timeout=self.timeout)
        if resp.status_code == 200:
            logger.info("Security check passed successfully.")
        else:
            logger.warning(f"Security check returned status code {resp.status_code}")
        return resp

    def get(self, url: str) -> requests.Response:
        """Performs a GET request, automatically resolving security checks when required."""
        resp = self.session.get(url, timeout=self.timeout)
        if resp.status_code == 401:
            logger.info("401 Unauthorized encountered. Initiating security bypass...")
            resp = self._bypass_security(resp.text, url)
        return resp

    def ensure_session(self):
        """Initializes the session via index.php to avoid triggering search flood limits during token handshake."""
        if "securitytoken" not in self.session.cookies:
            logger.info("Initializing forum session via index.php...")
            self.get("https://cs.rin.ru/forum/index.php")

    @staticmethod
    def clean_url(url: str, base: str = BASE_URL) -> str:
        """Normalizes URLs and removes session IDs (sid)."""
        full_url = urljoin(base, url)
        u = urlparse(full_url)
        query_params = parse_qs(u.query)
        query_params.pop("sid", None)
        new_query = urlencode(query_params, doseq=True)
        return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))

    def fetch_user_posts(self, author_id: str = "3625690") -> list:
        """
        Fetches the user's latest posts from cs.rin.ru search.php.
        Returns a list of dictionaries with post details.
        """
        self.ensure_session()

        url = f"https://cs.rin.ru/forum/search.php?author_id={author_id}&sr=posts"
        resp = self.get(url)
        if resp.status_code != 200:
            logger.error(f"Failed to fetch posts for author_id={author_id}: HTTP {resp.status_code}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Check for flood limit notice
        info_table = soup.find(lambda tag: tag.name == "table" and "cannot use search at this time" in tag.text)
        if info_table:
            logger.warning("Search flood limit reached. Waiting for next polling interval.")
            return []

        # Find search results table
        tables = soup.find_all("table", class_="tablebg")
        if len(tables) < 2:
            logger.warning(f"No search results table found for author_id={author_id}")
            return []

        main_table = tables[1]
        rows = main_table.find_all("tr", recursive=False)

        posts = []
        i = 1
        while i < len(rows):
            r1 = rows[i]
            r2 = rows[i + 1] if i + 1 < len(rows) else None
            r3 = rows[i + 2] if i + 2 < len(rows) else None

            # Look for post anchor: <a id="p12345" name="p12345">
            p_anchor = r1.find("a", id=re.compile(r"^p\d+")) or r1.find("a", attrs={"name": re.compile(r"^p\d+")})
            if not p_anchor:
                i += 1
                continue

            raw_post_id = p_anchor.get("name") or p_anchor.get("id") or ""
            post_id = raw_post_id.lstrip("p")

            # Forum info
            forum_a = r1.find("a", href=re.compile(r"viewforum\.php"))
            forum_name = forum_a.get_text(strip=True) if forum_a else ""
            forum_url = self.clean_url(forum_a["href"]) if forum_a else ""

            # Topic info
            topic_a = r1.find("a", href=re.compile(r"viewtopic\.php\?.*?t=\d+"))
            topic_title = topic_a.get_text(strip=True) if topic_a else ""
            topic_url = self.clean_url(topic_a["href"]) if topic_a else ""

            author = ""
            post_subject = ""
            post_url = f"https://cs.rin.ru/forum/viewtopic.php?p={post_id}#p{post_id}"
            posted_date = ""

            if r2:
                author_el = r2.find(class_="postauthor")
                if author_el:
                    author = author_el.get_text(strip=True)

                subj_a = r2.find("a", href=re.compile(r"viewtopic\.php\?.*?p=\d+"))
                if subj_a:
                    post_subject = subj_a.get_text(strip=True)
                    post_url = self.clean_url(subj_a["href"])

                date_div = r2.find(lambda tag: tag.name == "div" and "Posted:" in tag.text)
                if date_div:
                    posted_date = date_div.get_text(strip=True).replace("Posted:", "").strip(" \xa0\t\r\n")

            content_text = ""
            post_links = []
            if r3:
                postbody = r3.find(class_="postbody")
                if postbody:
                    content_text = postbody.get_text("\n", strip=True)
                    for link in postbody.find_all("a", href=True):
                        href = link["href"]
                        if not href.startswith("javascript") and not href.startswith("#"):
                            post_links.append(self.clean_url(href))
                else:
                    tds = r3.find_all("td")
                    if len(tds) >= 2:
                        content_text = tds[1].get_text("\n", strip=True)

            posts.append({
                "post_id": post_id,
                "author": author,
                "author_id": author_id,
                "forum_name": forum_name,
                "forum_url": forum_url,
                "topic_title": topic_title,
                "topic_url": topic_url,
                "post_subject": post_subject,
                "post_url": post_url,
                "posted_date": posted_date,
                "content_text": content_text,
                "post_links": list(set(post_links))
            })

            # Advance by 4 rows (r1, r2, r3, spacer)
            i += 4

        return posts
