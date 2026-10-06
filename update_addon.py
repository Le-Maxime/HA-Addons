import re
import urllib.request
import json
import os
import datetime

# Определение путей относительно расположения этого скрипта
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, 'twitch_drops_miner', 'config.yaml')
digest_path = os.path.join(script_dir, 'twitch_drops_miner', 'docker_digest.txt')
readme_path = os.path.join(script_dir, 'twitch_drops_miner', 'README.md')
changelog_path = os.path.join(script_dir, 'twitch_drops_miner', 'CHANGELOG.md')
root_readme_path = os.path.join(script_dir, 'README.md')

def update_root_readme_version(addon_folder, new_version):
    if not os.path.exists(root_readme_path):
        return
    with open(root_readme_path, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = rf'(\| \*\*[^\*]+\*\* \| \[`{addon_folder}`\]\(\./{addon_folder}\) \| `)[^`]+(` \|)'
    if re.search(pattern, content):
        new_content = re.sub(pattern, rf'\g<1>{new_version}\g<2>', content)
        with open(root_readme_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_content)
        print(f"Updated root README.md version for {addon_folder} to {new_version}")

def update_changelog(v_tag, t_version, c_path):
    release_body = ""
    api_url = f"https://api.github.com/repos/fireph/docker-twitch-drops-miner/releases/tags/{v_tag}"
    print(f"Fetching release notes from {api_url}...")
    try:
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            release_body = data.get('body', '').strip()
    except Exception as e:
        print(f"Could not fetch release notes from GitHub API: {e}")
        release_body = f"Version bumped to {t_version}. See [upstream release](https://github.com/fireph/docker-twitch-drops-miner/releases/tag/{v_tag}) for details."

    if not release_body:
        release_body = f"Version bumped to {t_version}."

    new_entry = f"## {t_version}\n\n{release_body}\n\n"

    if os.path.exists(c_path):
        with open(c_path, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'(#\s*Changelog\s*)', content, re.IGNORECASE)
        if match:
            header = match.group(1)
            if f"## {t_version}" not in content:
                new_content = content.replace(header, f"{header}\n{new_entry}")
                with open(c_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(new_content)
                print(f"Successfully inserted new release notes for {t_version} into CHANGELOG.md")
            else:
                print(f"Changelog already contains entry for {t_version}")
        else:
            if f"## {t_version}" not in content:
                new_content = f"# Changelog\n\n{new_entry}" + content
                with open(c_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(new_content)
                print(f"Prepended new release notes to CHANGELOG.md")
    else:
        with open(c_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(f"# Changelog\n\n{new_entry}")
        print(f"Created CHANGELOG.md with release notes for {t_version}")

# 1. TWITCH DROPS MINER
def update_twitch_drops_miner():
    print("--- Checking for Twitch Drops Miner updates ---")
    url = 'https://hub.docker.com/v2/repositories/dungfu/twitch-drops-miner/tags?page_size=100'
    print(f"Fetching latest image info from {url}...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            tags = res_data.get('results', [])
    except Exception as e:
        print(f"Error fetching tags from Docker Hub: {e}")
        return

    latest_digest = None
    for t in tags:
        if t.get('name') == 'latest':
            latest_digest = t.get('digest')
            break

    if not latest_digest:
        print("Could not find 'latest' tag digest in API response.")
        return

    print(f"Latest digest from Docker Hub: {latest_digest}")

    version_tag = None
    matching_tags = [t['name'] for t in tags if t.get('digest') == latest_digest]

    for tag in matching_tags:
        if tag == 'latest':
            continue
        if 'webui' in tag or 'tkinter' in tag:
            continue
        if re.search(r'\.[0-9a-f]{7}$', tag):
            version_tag = tag
            break

    if not version_tag:
        for tag in matching_tags:
            if tag != 'latest' and 'webui' not in tag and 'tkinter' not in tag:
                version_tag = tag
                break

    if not version_tag:
        print("Could not resolve specific version tag. Using fallback date-based version.")
        version_tag = datetime.datetime.now(datetime.timezone.utc).strftime("16.dev.%Y%m%d")

    target_version = version_tag if version_tag.startswith('v') else f"v{version_tag}"
    print(f"Resolved target version: {target_version}")

    stored_digest = ""
    if os.path.exists(digest_path):
        with open(digest_path, 'r', encoding='utf-8') as f:
            stored_digest = f.read().strip()

    current_version = ""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'version:\s*["\']?([^"\']+)["\']?', content)
        if match:
            current_version = match.group(1)

    print(f"Current local version: {current_version}")
    print(f"Stored local digest: {stored_digest}")

    if latest_digest == stored_digest and current_version == target_version:
        if not os.path.exists(changelog_path):
            print("CHANGELOG.md is missing. Bootstrapping it for current version...")
            update_changelog(version_tag, target_version, changelog_path)
        else:
            print("Twitch Drops Miner is up to date.")
        update_root_readme_version('twitch_drops_miner', target_version)
        return

    with open(digest_path, 'w', encoding='utf-8') as f:
        f.write(latest_digest)

    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        new_content = re.sub(
            r'(version:\s*["\']?)[^"\']*(["\']?)',
            r'\g<1>' + target_version + r'\g<2>',
            content
        )
        with open(config_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_content)
        print(f"Successfully bumped version in config.yaml from {current_version} to {target_version}")

    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme_content = f.read()
        pattern = r'(\bCurrent Version:\*\*\s*\[)[^\]]+(\]\(https://github.com/fireph/docker-twitch-drops-miner/releases/tag/)[^)]+(\))'
        if re.search(pattern, readme_content):
            new_readme_content = re.sub(
                pattern,
                r'\g<1>' + target_version + r'\g<2>' + version_tag + r'\g<3>',
                readme_content
            )
            with open(readme_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(new_readme_content)

    update_changelog(version_tag, target_version, changelog_path)
    update_root_readme_version('twitch_drops_miner', target_version)

# 2. FREE GAMES CLAIMER
def patch_fgc_notifier(fgc_dir):
    notifier_path = os.path.join(fgc_dir, 'src', 'core', 'notifier.py')
    if not os.path.exists(notifier_path):
        return

    with open(notifier_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if "from src.core.custom_notifier import custom_notify" in content:
        return

    target = "if cfg.notify_url:\n        tasks.append(send_apprise(message, title=title))"
    replacement = """if cfg.notify_url:
        try:
            from src.core.custom_notifier import custom_notify
            async def _send_custom():
                handled = await custom_notify(message, screenshot_path=screenshot_path, title=title)
                if not handled:
                    await send_apprise(message, title=title)
            tasks.append(_send_custom())
        except Exception:
            tasks.append(send_apprise(message, title=title))"""

    if target in content:
        new_content = content.replace(target, replacement)
        with open(notifier_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_content)

def patch_fgc_missing_base(fgc_dir):
    req_path = os.path.join(fgc_dir, 'requirements.txt')
    if os.path.exists(req_path):
        with open(req_path, 'r', encoding='utf-8') as f:
            r_content = f.read()
        if "nodriver" in r_content and "nodriver>=" not in r_content:
            r_content = re.sub(r'nodriver[^\r\n]*', 'nodriver>=0.50.5', r_content)
            with open(req_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(r_content)

    steam_path = os.path.join(fgc_dir, 'src', 'stores', 'steam.py')
    if os.path.exists(steam_path):
        with open(steam_path, 'r', encoding='utf-8') as f:
            s_content = f.read()
        if "from src.core.database import async_session, get_or_create, ClaimedGame" not in s_content:
            s_content = s_content.replace(
                "from src.core.database import async_session, get_or_create",
                "from src.core.database import async_session, get_or_create, ClaimedGame\nfrom sqlalchemy import select"
            )
        if 'requires base game (already known from DB)' not in s_content:
            target_pre = """        url = game.get("url", "")
        title = game.get("title", "Unknown")
        app_id = game.get("app_id", "")
        source = game.get("source", "unknown")"""
            repl_pre = """        url = game.get("url", "")
        title = game.get("title", "Unknown")
        app_id = game.get("app_id", "")
        if not app_id and url:
            app_id = self._extract_game_id(url)

        if app_id:
            async with async_session() as session:
                stmt = select(ClaimedGame).where(
                    ClaimedGame.store == "steam",
                    ClaimedGame.game_id == str(app_id),
                )
                existing = (await session.execute(stmt)).scalars().first()
                if existing:
                    if existing.status in ("claimed", "existed"):
                        logger.info("'%s' (%s) already in library (DB: %s), skipping.", title, app_id, existing.status)
                        return
                    if existing.status == "failed:missing_base":
                        logger.info("'%s' (%s) requires base game (already known from DB), skipping.", title, app_id)
                        return"""
            if target_pre in s_content:
                s_content = s_content.replace(target_pre, repl_pre)

        if 'failed:missing_base' not in s_content or 'status="failed:missing_base"' not in s_content:
            target_ensure = """        if not has_base_game:
            logger.warning("Skipping DLC '%s' because required base game is missing.", page_title)
            notify_game["status"] = "failed:missing_base"
            return"""
            repl_ensure = """        if not has_base_game:
            logger.warning("Skipping DLC '%s' because required base game is missing.", page_title)
            async with async_session() as session:
                obj, _ = await get_or_create(
                    session, store="steam", user=self.user or "unknown",
                    game_id=app_id or self._extract_game_id(current_url) or page_title,
                    title=page_title, url=current_url, status="failed:missing_base",
                )
                obj.status = "failed:missing_base"
                await session.commit()
            notify_game["status"] = "failed:missing_base"
            return"""
            if target_ensure in s_content:
                s_content = s_content.replace(target_ensure, repl_ensure)
        with open(steam_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(s_content)

    epic_path = os.path.join(fgc_dir, 'src', 'stores', 'epic.py')
    if os.path.exists(epic_path):
        with open(epic_path, 'r', encoding='utf-8') as f:
            e_content = f.read()
        if 'failed:missing_base' not in e_content:
            target_epic = """            # The page, not the database, decides: a row saying "claimed" can be stale
            # or simply wrong, and skipping on it alone would hide the game forever.
            if not created:"""
            repl_epic = """            # The page, not the database, decides: a row saying "claimed" can be stale
            # or simply wrong, and skipping on it alone would hide the game forever.
            # But a missing base game cannot be acquired automatically, so avoid repeated checks.
            if not created and obj.status == "failed:missing_base":
                logger.info("'%s' requires base game (already known from DB), skipping.", obj.title or game_id)
                return
            if not created:"""
            if target_epic in e_content:
                e_content = e_content.replace(target_epic, repl_epic)
                with open(epic_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(e_content)

    gp_path = os.path.join(fgc_dir, 'src', 'stores', 'gamerpower.py')
    if os.path.exists(gp_path):
        with open(gp_path, 'r', encoding='utf-8') as f:
            g_content = f.read()
        if 'ClaimedGame.status.in_(["claimed", "existed", "failed:missing_base"])' not in g_content:
            target_gp = 'ClaimedGame.status.in_(["claimed", "existed"])'
            repl_gp = 'ClaimedGame.status.in_(["claimed", "existed", "failed:missing_base"])'
            if target_gp in g_content:
                g_content = g_content.replace(target_gp, repl_gp)
                with open(gp_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(g_content)

    cfg_path = os.path.join(fgc_dir, 'config.yaml')
    if os.path.exists(cfg_path):
        with open(cfg_path, 'r', encoding='utf-8') as f:
            c_content = f.read()
        changed = False
        if "notify_missing_base:" not in c_content:
            c_content = c_content.replace(
                "options:\n",
                "options:\n  notify_missing_base: false\n"
            )
            c_content = c_content.replace(
                "schema:\n",
                "schema:\n  notify_missing_base: bool?\n"
            )
            changed = True
        if changed:
            with open(cfg_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(c_content)

def update_free_games_claimer():
    print("\n--- Checking for Free Games Claimer Remaster updates ---")
    fgc_dir = os.path.join(script_dir, 'free_games_claimer')
    fgc_config_path = os.path.join(fgc_dir, 'config.yaml')
    fgc_changelog_path = os.path.join(fgc_dir, 'CHANGELOG.md')
    fgc_readme_path = os.path.join(fgc_dir, 'README.md')
    
    url = "https://api.github.com/repos/P-Adamiec/Free-Games-Claimer-Remaster/commits/main"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            commit_data = json.loads(response.read().decode('utf-8'))
            sha = commit_data.get('sha', '')[:7]
            commit_date_str = commit_data.get('commit', {}).get('committer', {}).get('date', '')
            date_part = commit_date_str.split('T')[0].replace('-', '')
            target_version = f"v1.1.{date_part}-{sha}"
            commit_message = commit_data.get('commit', {}).get('message', '').strip()
    except Exception as e:
        print(f"Error fetching latest commit for Free Games Claimer: {e}")
        return

    print(f"Latest upstream version: {target_version}")
    
    current_version = ""
    if os.path.exists(fgc_config_path):
        with open(fgc_config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'version:\s*["\']?([^"\']+)["\']?', content)
        if match:
            current_version = match.group(1)
            
    print(f"Current local version: {current_version}")
    
    if current_version == target_version or (sha and sha in current_version):
        print("Free Games Claimer is up to date.")
        patch_fgc_notifier(fgc_dir)
        patch_fgc_missing_base(fgc_dir)
        update_root_readme_version('free_games_claimer', current_version)
        return
        
    print(f"Updating Free Games Claimer from {current_version} to {target_version}...")
    
    zip_url = "https://github.com/P-Adamiec/Free-Games-Claimer-Remaster/archive/refs/heads/main.zip"
    try:
        import zipfile
        import io
        import shutil
        
        print(f"Downloading source zip from {zip_url}...")
        req = urllib.request.Request(zip_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            zip_bytes = response.read()
            
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            temp_dir = os.path.join(script_dir, 'fgc_temp')
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)
            
            z.extractall(temp_dir)
            extracted_folder = os.path.join(temp_dir, 'Free-Games-Claimer-Remaster-main')
            
            def copy_file(src_name, dest_name=None):
                dest_name = dest_name or src_name
                src_file = os.path.join(extracted_folder, src_name)
                dest_file = os.path.join(fgc_dir, dest_name)
                if os.path.exists(src_file):
                    shutil.copy2(src_file, dest_file)
                    
            copy_file('main.py')
            copy_file('requirements.txt')
            copy_file('.dockerignore')
            copy_file('.gitignore')
            copy_file('LICENSE')
            
            dest_src = os.path.join(fgc_dir, 'src')
            custom_notifier_backup = None
            custom_notifier_file = os.path.join(dest_src, 'core', 'custom_notifier.py')
            if os.path.exists(custom_notifier_file):
                with open(custom_notifier_file, 'r', encoding='utf-8') as f:
                    custom_notifier_backup = f.read()

            if os.path.exists(dest_src):
                shutil.rmtree(dest_src)
            shutil.copytree(os.path.join(extracted_folder, 'src'), dest_src)
            
            if custom_notifier_backup:
                os.makedirs(os.path.join(dest_src, 'core'), exist_ok=True)
                with open(custom_notifier_file, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(custom_notifier_backup)

            patch_fgc_notifier(fgc_dir)
            patch_fgc_missing_base(fgc_dir)
            shutil.rmtree(temp_dir)
            print("Successfully updated source files.")
    except Exception as e:
        print(f"Error updating files: {e}")
        return

    with open(fgc_config_path, 'r', encoding='utf-8') as f:
        content = f.read()
    new_content = re.sub(
        r'(version:\s*["\']?)[^"\']*(["\']?)',
        r'\g<1>' + target_version + r'\g<2>',
        content
    )
    with open(fgc_config_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_content)
    
    if os.path.exists(fgc_readme_path):
        with open(fgc_readme_path, 'r', encoding='utf-8') as f:
            readme_content = f.read()
        pattern = r'(\bCurrent Version:\*\*\s*\[)[^\]]+(\]\(https://github.com/P-Adamiec/Free-Games-Claimer-Remaster/commit/)[^)]+(\))'
        if re.search(pattern, readme_content):
            new_readme_content = re.sub(
                pattern,
                r'\g<1>' + target_version + r'\g<2>' + sha + r'\g<3>',
                readme_content
            )
            with open(fgc_readme_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(new_readme_content)
    
    new_entry = f"## {target_version}\n\nUpstream update: {commit_message}\n\n"
    if os.path.exists(fgc_changelog_path):
        with open(fgc_changelog_path, 'r', encoding='utf-8') as f:
            changelog_content = f.read()
        match = re.search(r'(#\s*Changelog\s*)', changelog_content, re.IGNORECASE)
        if match:
            header = match.group(1)
            new_changelog = changelog_content.replace(header, f"{header}\n{new_entry}")
        else:
            new_changelog = f"# Changelog\n\n{new_entry}" + changelog_content
    else:
        new_changelog = f"# Changelog\n\n{new_entry}"
        
    with open(fgc_changelog_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_changelog)
    print("Updated CHANGELOG.md.")
    update_root_readme_version('free_games_claimer', target_version)

# 3. SPOOLMAN
def update_spoolman():
    print("\n--- Checking for Spoolman updates ---")
    spoolman_dir = os.path.join(script_dir, 'spoolman')
    spoolman_config_path = os.path.join(spoolman_dir, 'config.yaml')
    spoolman_changelog_path = os.path.join(spoolman_dir, 'CHANGELOG.md')
    spoolman_readme_path = os.path.join(spoolman_dir, 'README.md')
    
    url = "https://api.github.com/repos/Donkie/Spoolman/releases/latest"
    print(f"Fetching latest release from {url}...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            release_data = json.loads(response.read().decode('utf-8'))
            tag_name = release_data.get('tag_name', '').strip()
            target_version = tag_name.lstrip('v')
            release_body = release_data.get('body', '').strip()
    except Exception as e:
        print(f"Error fetching latest release for Spoolman: {e}")
        return

    if not target_version:
        print("Could not resolve Spoolman target version.")
        return

    print(f"Latest Spoolman upstream version: {target_version}")

    current_version = ""
    if os.path.exists(spoolman_config_path):
        with open(spoolman_config_path, 'r', encoding='utf-8') as f:
            c_content = f.read()
        match = re.search(r'version:\s*["\']?([^"\']+)["\']?', c_content)
        if match:
            current_version = match.group(1).lstrip('v')

    print(f"Current local Spoolman version: {current_version}")

    if current_version == target_version:
        print("Spoolman is up to date.")
        update_root_readme_version('spoolman', target_version)
        return

    print(f"Updating Spoolman from {current_version} to {target_version}...")

    with open(spoolman_config_path, 'r', encoding='utf-8') as f:
        c_content = f.read()
    new_c_content = re.sub(
        r'(version:\s*["\']?)[^"\']*(["\']?)',
        r'\g<1>' + target_version + r'\g<2>',
        c_content
    )
    new_c_content = re.sub(
        r'(\(v)[0-9\.]+(\))',
        r'\g<1>' + target_version + r'\g<2>',
        new_c_content
    )
    with open(spoolman_config_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_c_content)
    print("Updated version in spoolman/config.yaml.")

    if os.path.exists(spoolman_readme_path):
        with open(spoolman_readme_path, 'r', encoding='utf-8') as f:
            r_content = f.read()
        new_r_content = re.sub(
            r'Spoolman-v[0-9\.]+-blue',
            f'Spoolman-v{target_version}-blue',
            r_content
        )
        with open(spoolman_readme_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_r_content)
        print("Updated badge in spoolman/README.md.")

    if not release_body:
        release_body = f"Upstream release v{target_version}."
    new_entry = f"## {target_version}\n\n{release_body}\n\n"
    if os.path.exists(spoolman_changelog_path):
        with open(spoolman_changelog_path, 'r', encoding='utf-8') as f:
            ch_content = f.read()
        match = re.search(r'(#\s*Changelog\s*)', ch_content, re.IGNORECASE)
        if match:
            header = match.group(1)
            new_ch = ch_content.replace(header, f"{header}\n{new_entry}")
        else:
            new_ch = f"# Changelog\n\n{new_entry}" + ch_content
    else:
        new_ch = f"# Changelog\n\n{new_entry}"

    with open(spoolman_changelog_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_ch)
    print("Updated spoolman/CHANGELOG.md.")

    update_root_readme_version('spoolman', target_version)

if __name__ == "__main__":
    update_twitch_drops_miner()
    update_free_games_claimer()
    update_spoolman()
