# Twitch Drops Miner — Home Assistant Addon

**Current Version:** [v16.dev.25d88e5](https://github.com/fireph/docker-twitch-drops-miner/releases/tag/16.dev.25d88e5)

This addon packages **Twitch Drops Miner** (a tool for AFK mining Twitch drops with automatic claiming and channel switching) as a Home Assistant addon.

## 🚀 Features
*   **Ingress Support:** Access the web interface securely directly from the Home Assistant sidebar (no port forwarding required).
*   **Low Footprint:** Highly optimized, using only ~80MB RAM.
*   **Automated Updates:** Monitors Docker Hub and bumps versions automatically.
*   **Custom Sidebar Icon:** Customized pickaxe icon (`mdi:pickaxe`) matching the mining theme.

## ⚙️ Configuration & Access

Once installed, you can configure the addon settings:
*   **Show in sidebar:** Toggle this option to access the Twitch Drops Miner WebUI directly from the Home Assistant sidebar.
*   **Ingress:** By default, WebUI is accessible securely via Home Assistant's Ingress.

For advanced configurations, Twitch Drops Miner configuration files will be saved in your Home Assistant `/addon_configs/twitch_drops_miner/` directory (fully persistent and included in add-on backups).
