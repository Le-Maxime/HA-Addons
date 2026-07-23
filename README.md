# DarkAssassinUA Home Assistant Add-ons Repository

Welcome! This is a personal repository of custom Home Assistant add-ons, designed to automate gaming rewards and tasks directly on your Home Assistant server.

## 📦 Available Add-ons

| Add-on | Directory | Current Version | Original Upstream | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Twitch Drops Miner** | [`twitch_drops_miner`](./twitch_drops_miner) | `v16.dev.8c55d85` | [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) | AFK Twitch drops mining with automated claiming and Ingress support. |
| **Free Games Claimer Remaster** | [`free_games_claimer`](./free_games_claimer) | `v1.1.20260721-3808055` | [P-Adamiec/Free-Games-Claimer-Remaster](https://github.com/P-Adamiec/Free-Games-Claimer-Remaster) | Automatic weekly/monthly free games claimer (Epic, Prime Gaming, GOG, Steam). |

---

## 🚀 Installation Instructions

To add these addons to your Home Assistant instance:

1.  Copy the URL of this repository:
    ```
    https://github.com/DarkAssassinUA/HA-Addons
    ```
2.  In your Home Assistant interface, go to **Settings** -> **Add-ons**.
3.  Click the **Add-on Store** button in the bottom right corner.
4.  In the top right corner, click the three-dot menu icon and select **Repositories**.
5.  Paste the repository URL into the field and click **Add**.
6.  Close the dialog box and refresh the page.
7.  Scroll down to the bottom of the store, locate the newly added **DarkAssassinUA Home Assistant Apps** section, and select the addon you wish to install.

---

## 🛠️ Automated Repository Maintenance

The add-ons in this repository are maintained automatically using **GitHub Actions Workflows**:
*   **Twitch Drops Miner:** Bumps version, pulls the latest Docker Hub digest, and compiles a CHANGELOG based on upstream releases every 6 hours.
*   **Free Games Claimer Remaster:** Tracks the main branch commits of the upstream repository, downloads new source code updates, bumps versions, and records commits in the CHANGELOG.
