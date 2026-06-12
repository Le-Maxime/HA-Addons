# Twitch Drops Miner — Home Assistant Addon

**Current Version:** `v16.dev.8c55d85`

This repository contains a custom Home Assistant addon for **Twitch Drops Miner** (a tool for AFK mining Twitch drops with automatic claiming and channel switching). 

It packages the unofficial, lightweight Docker image featuring a native web-based interface for easy management directly from your browser.

## 🔗 Credits & References
*   **Original Application:** [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner)
*   **Docker Container Project:** [fireph/docker-twitch-drops-miner](https://github.com/fireph/docker-twitch-drops-miner) (Docker Image: `dungfu/twitch-drops-miner`)

---

## 🚀 Features
*   **Ingress Support:** Access the web interface securely directly from the Home Assistant sidebar (no port forwarding required).
*   **Low Footprint:** Highly optimized, using only ~80MB RAM.
*   **Automated Updates:** The repository uses GitHub Actions to monitor Docker Hub. When a new docker image is pushed upstream, this addon repository automatically bumps its version so you get an update prompt in Home Assistant.

---

## 🛠️ Installation

1.  Copy the URL of this repository:
    ```
    https://github.com/DarkAssassinUA/HA-Addons
    ```
2.  In your Home Assistant interface, go to **Settings** -> **Add-ons**.
3.  Click the **Add-on Store** button in the bottom right corner.
4.  In the top right corner, click the three-dot menu icon and select **Repositories**.
5.  Paste the repository URL into the field and click **Add**.
6.  Close the dialog box and refresh the page.
7.  Scroll down to the bottom of the store, locate **Twitch Drops Miner** under the newly added repository, and click **Install**.

---

## ⚙️ Configuration & Access

Once installed, you can configure the addon settings:
*   **Show in sidebar:** Toggle this option to access the Twitch Drops Miner WebUI directly from the Home Assistant sidebar.
*   **Ingress:** By default, WebUI is accessible securely via Home Assistant's Ingress.

For advanced configurations, Twitch Drops Miner files will be saved in your Home Assistant `/config/twitch_drops_miner` directory.
