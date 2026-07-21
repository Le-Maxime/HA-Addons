# Changelog


## v1.1.20260721-3808055

Upstream update: v1.4: AliExpress check-in improvements, fingerprinting & store fixes, etc.

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/).

## [1.1] – 2026-06-08

### Added
- **Docker GHCR modernization (PR #5 by @Ch4r0ne)** – elegantly overhauled the GHCR image publishing workflow utilizing the official `docker/metadata-action`, standardizing dynamic tags (`main`, `latest`, `v*.*`) seamlessly via a dedicated `.github/workflows/docker-ghcr.yml`.
- **Remote VNC Customization (`VNC_IP`)** – users orchestrating the project on a remote NAS/server can now configure `VNC_IP` (defaults to `localhost`) to explicitly define the hyperlink printed in Discord 2FA/login notifications.
- **Database Games Reset (`RESET_DB_GAMES`)** – A new environment variable allows users to set it to `true` to retroactively erase any database claims recorded within the last 7 days upon initialization, ensuring the bot will retry claiming them.
- **Unified Master Notification** – Individual stores no longer send asynchronous Discord alerts immediately upon process completion. Instead, the orchestrator caches and aggregates all outcomes across platform limits, submitting a single tidy report segmented by store.
- **GamerPower standalone store** (`src/stores/gamerpower.py`) – GamerPower is now a fully separate module that routes external keys to Fanatical, Alienware, Itch.io, and IndieGala. It runs last by default to deduplicate against Steam, Epic, and GOG libraries globally. It can be selected via the `gamerpower` or `gp` alias in the `STORES` configuration. This store feature is still experimental and may not work as expected.
- **Fanatical giveaway support** – GamerPower now fully supports auto-claiming Fanatical giveaways (`FANATICAL_ENABLE=true`, `FANATICAL_EMAIL`, `FANATICAL_PASSWORD`), including auto-bypassing JS cookie banners.
- **Alienware Arena giveaway support** – GamerPower detects redirects to `alienwarearena.com` and operates in **notify-only** mode (`ALIENWARE_ENABLE=true`), sending a Discord alert to claim manually due to Alienware's ARP points requirements and hCaptcha protection.
- **Itch.io giveaway support** – GamerPower detects redirects to `itch.io` and auto-claims free DRM-free games (`ITCHIO_ENABLE=true`, `ITCHIO_EMAIL`, `ITCHIO_PASSWORD`). Handles "Download or Claim" and "No thanks" skip flows.
- **IndieGala giveaway support** – GamerPower detects redirects to `indiegala.com` and auto-claims free games (`INDIEGALA_ENABLE=true`, `INDIEGALA_EMAIL`, `INDIEGALA_PASSWORD`). Adds games to IndieGala library automatically.
- **Amazon security code & SMS OTP support** – detects Amazon shopping app / SMS OTP 2FA verification (e.g. "Two-Step Verification") during Prime Gaming login, sends a notification (Discord/Apprise), and waits for manual code entry via VNC.
- **Discord message batching** – notifications exceeding Discord's 2000-character limit are now automatically split into multiple sends.

### Changed
- **Epic Checkout Core Migration** – Standardized DOM matching patterns to gracefully navigate around arbitrary whitespace, and instituted cross-origin iframe (CDP `create_isolated_world`) boundary penetration logic to combat Epic's redesigned containerized checkout overlay flow.
- **Epic European Compliance** – Developed automatic acknowledgement for the new European Union "Right of Withdrawal" blocking modal required during cart transactions.
- **Removed `STEAM_USE_GAMERPOWER`** – Steam claiming now relies exclusively on SteamDB (`https://steamdb.info/upcoming/free/`) directly. GamerPower execution is handled by the unified module via the `STORES` array configuration, simplifying `.env`.
- **Improved Platform detection** – games were sometimes showing as "unknown" platform; the slug parser now scans all URL segments instead of only the last one (e.g. `/claims/game-name-gog/dp/` now correctly detects GOG).
- **Hardened Steam paid content guard** – verifies items are genuinely free (-100% / 0.00) before clicking any claim button, skipping paid DLCs to prevent accidental purchases.
- **Improved Discord 2FA notification** – removed duplicate notification with an ugly `<your-host>` placeholder; the VNC handler already sends a clean clickable `localhost` URL.

### Fixed
- **Steam Base Game prerequisites (DLC)** – Steam module natively detects if a free DLC requires a base game, automatically pausing to acquire the required base game (if it is also free) before proceeding with the DLC.
- **Docker GHCR Compatibility** – lowercased Docker image tags in configurations to ensure compatibility with GitHub Container Registry pushes.
- **SteamDB parsing** – relaxed the parser to accept `100%` discount strings, successfully catching free promos that lack the explicit "Free to Keep" badge.
- **Prime Gaming crashes** – fixed `ProtocolException: Session with given id not found` by adding a CDP session health check (`_ensure_page_alive`) that auto-recovers a stale tab reference after login or VNC interaction.
- **Prime Gaming session persistence** – injected global session health checks (`_ensure_logged_in(silent=True)`) before processing *every* game, preventing cascading failures caused by unexpected Luna "Sign in" overlays blocking the screen midway through a claiming loop.
- **Prime Gaming missing platforms** – implemented a Python-side browser URL `window.location.href` scraping fallback to extract platform slugs (e.g. `gog`) when Amazon Luna hides `detailUrl` elements from the DOM for already collected games, preventing them from being logged as "unknown".
- **GOG auto-redemption limits** – pending GOG codes extracted from Prime will no longer be automatically redeemed if `gog` is explicitly omitted from the `STORES` array layout.
- **GOG code redemption** – "Activate" / "Aktywuj" button was not clicked on non-English IPs; fixed by forcing English locale via `/en/redeem/` URL.
- **GOG 2FA detection** – resolved timeouts caused by missing Polish localization keywords by migrating the check to a rock-solid `/two_factor/` URL path validator. 
- **GOG auth timeouts** – expanded the login redirect patience from 14s to 26s to gracefully bridge heavily loaded regional GOG network backends without artificially triggering a VNC captcha warning.
- **Epic Games order confirmation** – fixed timeout errors by detecting the new "It's all yours" dialog and clicking `Continue browsing`.
- **VNC timeout behavior** – decluttered continuous waiting loop logs across all stores, silencing logs to fire only once every 60s, while gracefully extending the manual threshold limits defaults to 3 minutes.

### Unresolved / To Do
- **GOG translation interference** – disabled Chrome's automated Google Translate popup during login via JS `translate="no"` DOM injection and bypassed keyboard focus loss by writing login credentials directly to React's element state via `window.HTMLInputElement.prototype`. Further investigation needed to fully suppress popup across deeply cached legacy profiles – low priority as it does not affect functionality.

## [1.0] - 2026-05-13

### Architecture
- Complete rewrite from Node.js (Playwright) to **Python 3 + nodriver** for stealth browser automation
- ACID-compliant **SQLite** database via SQLAlchemy replaces volatile `.json` file writes
- Object-oriented `BaseClaimer` class – all store modules inherit unified browser management
- **APScheduler** cron-based scheduling replaces shell-level `sleep` loops
- Multi-arch Docker support: `linux/amd64` (Google Chrome) + `linux/arm64` (Chromium)

### Store Modules
- **Steam** (`src/stores/steam.py`) – Entirely new auto-claimer (original JS only scraped profiles)
  - Queries SteamDB for free-to-keep games
  - Claim button priority: `add_to_account` -> discount form -> `freeGameBtn` fallback
  - Automatic Steam Guard / 2FA login support
- **Epic Games** (`src/stores/epic.py`) – Headful nodriver bypasses hCaptcha checkpoints
- **Prime Gaming** (`src/stores/prime.py`)
  - URL slug-based platform detection (`-gog/dp/`, `-epic/dp/`, `-legacy/dp/`, `-aga/dp/`)
  - Direct navigation to detail pages – no more "Could not click" failures
  - Export codes to `prime-gaming.json` alongside SQLite
  - Automatic GOG code extraction and forwarding to GOG module for redemption
  - Account-linked platforms (Epic, Amazon) correctly identified and skipped
- **GOG** (`src/stores/gog.py`) – Direct auth page navigation, session persistence via `--restore-last-session`
  - Automatic redemption of GOG codes from Prime Gaming
  - Redemption guard: only triggers when pending codes exist or `GOG_FORCE_REDEEM` is set

### Infrastructure
- **VNC login fallback**: Configurable timeout for manual browser login via noVNC
- **Discord/Apprise notifications**: Granular `.env` triggers, game list formatting
- **Typed configuration** (`src/core/config.py`): Strict `.env` parsing into Python `Config` class
- **Startup banner**: Displays version and author on every launch

### Removed from Original
- ❌ `aliexpress.js` – Out of scope (not gaming)
- ❌ `unrealengine.js` – Out of scope
- ❌ `steam-games.js` – Only scraped profiles, never claimed games
