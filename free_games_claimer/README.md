# Free Games Claimer Remaster — Home Assistant Addon

**Current Version:** [v1.1.20260614-cca4992](https://github.com/P-Adamiec/Free-Games-Claimer-Remaster/commit/cca4992)

*   **Original Application:** [P-Adamiec/Free-Games-Claimer-Remaster](https://github.com/P-Adamiec/Free-Games-Claimer-Remaster)

This addon packages **Free Games Claimer Remaster** (a python tool for automatically claiming free games from Epic Games, Amazon Prime Gaming, GOG, and Steam) as a Home Assistant addon.

## 🚀 Features
*   **VNC Access (port 7080):** A virtual VNC desktop runs in the container, letting you see the browser and manually solve captchas or enter 2FA codes when required.
*   **Dual Notifications:** Supports concurrent notifications to both Discord webhooks and Telegram bots.
*   **Automatic Updates:** Version updates are monitored and pulled automatically from the upstream repo.
*   **Persistent Storage:** Data (session cookies, screenshots, sqlite database) is saved persistently under your local network share:
    `\\<HA-IP>\ADDON_CONFIGS\free_games_claimer`

## ⚙️ Configuration Options

Configure these parameters in the **Configuration** tab of the addon in the Home Assistant UI:

### 🖥️ Display & VNC Settings
*   `show`: Enable/disable VNC window rendering (`true` / `false`). Keep `true` for initial logins.
*   `width`: Width of the virtual VNC screen (default: `1280`).
*   `height`: Height of the virtual VNC screen (default: `720`).
*   `vnc_password`: Set password for VNC access (leave empty for none).

### ⏰ Scheduler
*   `scheduler_hours`: Time interval in hours between automated check and claim runs (default: `12`).

### 🔔 Notifications
*   `notify`: Telegram Apprise URL (Format: `tgram://<bot_token>/<chat_id>`).
*   `discord_webhook`: Discord Webhook URL.
*   `notify_summary`: Send a summary of all claimed games after each run (`true` / `false`).
*   `notify_errors`: Send notification on critical errors/crashes (`true` / `false`).
*   `notify_claim_fails`: Send notification on individual game claim failures (`true` / `false`).
*   `notify_login_request`: Alert when manual VNC login/2FA is required (`true` / `false`).

### 🔑 Default Credentials
*   `email` / `password`: Default credentials used for all stores unless overridden below.

### 🎮 Store Specifics

#### Epic Games
*   `eg_email` / `eg_password`: Epic Games credentials.
*   `eg_otpkey`: 2FA setup key (Manual Entry Key from Epic's authenticator setup).
*   `eg_parentalpin`: Parental Control PIN.

#### Prime Gaming (Amazon)
*   `pg_email` / `pg_password`: Amazon credentials.
*   `pg_otpkey`: Amazon 2FA setup key.
*   `pg_force_check_collected`: Force re-check already claimed games.
*   `pg_redeem`: Auto-redeem keys on external stores.
*   `pg_claimdlc`: Claim DLCs as well as base games.

#### GOG.com
*   `gog_email` / `gog_password`: GOG credentials.
*   `gog_newsletter`: Keep newsletter subscription after claiming (`true` / `false`).
*   `gog_force_redeem`: Force redeem old GOG codes.
*   `gog_otp_enable`: Auto-consume backup codes for GOG 2FA.
*   `gog_otp_codes`: Comma-separated list of GOG backup codes.

#### Steam
*   `steam_username` / `steam_password`: Steam credentials.

#### GamerPower / Fanatical / Itch.io / IndieGala
*(Make sure to add `gamerpower` to your `stores` list if you enable these)*
*   `fanatical_enable`: Enable Fanatical.com module.
*   `fanatical_email` / `fanatical_password`: Fanatical credentials.
*   `alienware_enable`: Enable Alienware Arena notifications.
*   `itchio_enable`: Enable Itch.io module.
*   `itchio_email` / `itchio_password`: Itch.io credentials.
*   `indiegala_enable`: Enable IndieGala module.
*   `indiegala_email` / `indiegala_password`: IndieGala credentials.
*   `unknown_stores_enable`: Open other unknown giveaway sites in VNC browser.

### 🛠️ Advanced & Debug
*   `stores`: Comma-separated list of active stores to run (default: `steam,epic,prime,gog`).
*   `reset_db_games`: Automatically delete all claims recorded in the last 7 days on startup.
*   `debug`: Enable verbose debug logging (`true` / `false`).
*   `dryrun`: Go through all steps but do not click "claim" buttons (`true` / `false`).
