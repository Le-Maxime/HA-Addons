import re
import urllib.request
import json
import os

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
    """Получает описание релиза с GitHub и записывает/добавляет его в CHANGELOG.md"""
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

    # Форматируем новую запись
    new_entry = f"## {t_version}\n\n{release_body}\n\n"

    # Записываем или вставляем в CHANGELOG.md
    if os.path.exists(c_path):
        with open(c_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Находим заголовок '# Changelog' и вставляем запись сразу после него
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
            # Если заголовка нет, добавляем его в начало
            if f"## {t_version}" not in content:
                new_content = f"# Changelog\n\n{new_entry}" + content
                with open(c_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(new_content)
                print(f"Prepended new release notes to CHANGELOG.md")
    else:
        # Создаем новый файл CHANGELOG.md
        with open(c_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(f"# Changelog\n\n{new_entry}")
        print(f"Created CHANGELOG.md with release notes for {t_version}")

def update_twitch_drops_miner():
    print("--- Checking for Twitch Drops Miner updates ---")
    # 1. Получение списка тегов с Docker Hub
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

    # Находим хэш (digest) для тега 'latest'
    latest_digest = None
    for t in tags:
        if t.get('name') == 'latest':
            latest_digest = t.get('digest')
            break

    if not latest_digest:
        print("Could not find 'latest' tag digest in API response.")
        return

    print(f"Latest digest from Docker Hub: {latest_digest}")

    # Ищем соответствующий тег версии (например, '16.dev.8c55d85')
    version_tag = None
    matching_tags = [t['name'] for t in tags if t.get('digest') == latest_digest]

    for tag in matching_tags:
        if tag == 'latest':
            continue
        if 'webui' in tag or 'tkinter' in tag:
            continue
        # Шаблон: заканчивается на точку и 7 символов хэша коммита
        if re.search(r'\.[0-9a-f]{7}$', tag):
            version_tag = tag
            break

    if not version_tag:
        # Фолбек на первый не-latest, не-webui/tkinter тег с тем же дайджестом
        for tag in matching_tags:
            if tag != 'latest' and 'webui' not in tag and 'tkinter' not in tag:
                version_tag = tag
                break

    if not version_tag:
        print("Could not resolve specific version tag. Using fallback date-based version.")
        # Фолбек на дату, если ничего не нашли
        import datetime
        version_tag = datetime.datetime.utcnow().strftime("16.dev.%Y%m%d")

    # Формируем целевую версию
    target_version = version_tag if version_tag.startswith('v') else f"v{version_tag}"
    print(f"Resolved target version: {target_version}")

    # 2. Чтение текущей версии и хэша из локальных файлов
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

    # Проверяем, нужны ли изменения
    if latest_digest == stored_digest and current_version == target_version:
        # Если изменений версии нет, но CHANGELOG.md отсутствует, создаем его для текущей версии
        if not os.path.exists(changelog_path):
            print("CHANGELOG.md is missing. Bootstrapping it for current version...")
            update_changelog(version_tag, target_version, changelog_path)
        else:
            print("No updates needed. Everything is up to date.")
        return

    # 3. Обновляем docker_digest.txt
    with open(digest_path, 'w', encoding='utf-8') as f:
        f.write(latest_digest)
    print(f"Updated docker_digest.txt with: {latest_digest}")

    # 4. Обновляем версию в config.yaml
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Заменяем старую версию на новую
        if re.search(r'version:\s*', content):
            new_content = re.sub(
                r'(version:\s*["\']?)[^"\']*(["\']?)',
                r'\g<1>' + target_version + r'\g<2>',
                content
            )
            with open(config_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(new_content)
            print(f"Successfully bumped version in config.yaml from {current_version} to {target_version}")
        else:
            print("Error: 'version:' key not found in config.yaml")
            return
    else:
        print(f"Error: config.yaml not found at {config_path}")
        return

    # 5. Обновляем версию в README.md
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            readme_content = f.read()
        
        # Регулярное выражение для поиска строки вида **Current Version:** [v16.dev.8c55d85](https://github.com/fireph/docker-twitch-drops-miner/releases/tag/16.dev.8c55d85)
        pattern = r'(\*\*Current Version:\*\*\s*\[)[^\]]+(\]\(https://github.com/fireph/docker-twitch-drops-miner/releases/tag/)[^)]+(\))'
        if re.search(pattern, readme_content):
            new_readme_content = re.sub(
                pattern,
                r'\g<1>' + target_version + r'\g<2>' + version_tag + r'\g<3>',
                readme_content
            )
            with open(readme_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(new_readme_content)
            print(f"Successfully bumped version link in README.md to {target_version}")
        else:
            print("Warning: '**Current Version:** [...](...)' pattern not found in README.md")
    else:
        print(f"Warning: README.md not found at {readme_path}")

    # 6. Обновляем CHANGELOG.md
    update_changelog(version_tag, target_version, changelog_path)
    update_root_readme_version('twitch_drops_miner', target_version)

# Run the Twitch Drops Miner update
update_twitch_drops_miner()

def patch_fgc_notifier(fgc_dir):
    notifier_path = os.path.join(fgc_dir, 'src', 'core', 'notifier.py')
    if not os.path.exists(notifier_path):
        return

    with open(notifier_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if "from src.core.custom_notifier import custom_notify" in content:
        print("Notifier is already patched with custom Telegram notifier.")
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
        print("Successfully re-applied custom Telegram notifier hook to notifier.py.")
    else:
        print("Warning: Could not automatically patch notifier.py (target pattern missing).")

def update_free_games_claimer():
    print("\n--- Checking for Free Games Claimer Remaster updates ---")
    fgc_dir = os.path.join(script_dir, 'free_games_claimer')
    fgc_config_path = os.path.join(fgc_dir, 'config.yaml')
    fgc_changelog_path = os.path.join(fgc_dir, 'CHANGELOG.md')
    fgc_readme_path = os.path.join(fgc_dir, 'README.md')
    
    # 1. Fetch latest commit from GitHub
    url = "https://api.github.com/repos/P-Adamiec/Free-Games-Claimer-Remaster/commits/main"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            commit_data = json.loads(response.read().decode('utf-8'))
            sha = commit_data.get('sha', '')[:7]
            commit_date_str = commit_data.get('commit', {}).get('committer', {}).get('date', '')
            # format date to YYYYMMDD
            date_part = commit_date_str.split('T')[0].replace('-', '')
            target_version = f"v1.1.{date_part}-{sha}"
            commit_message = commit_data.get('commit', {}).get('message', '').strip()
    except Exception as e:
        print(f"Error fetching latest commit for Free Games Claimer: {e}")
        return

    print(f"Latest upstream version: {target_version}")
    
    # Read current version
    current_version = ""
    if os.path.exists(fgc_config_path):
        with open(fgc_config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'version:\s*["\']?([^"\']+)["\']?', content)
        if match:
            current_version = match.group(1)
            
    print(f"Current local version: {current_version}")
    
    if current_version == target_version:
        print("Free Games Claimer is up to date.")
        # Ensure notifier is patched even if version matches
        patch_fgc_notifier(fgc_dir)
        update_root_readme_version('free_games_claimer', target_version)
        return
        
    print(f"Updating Free Games Claimer from {current_version} to {target_version}...")
    
    # 2. Download zip of the repository
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
            
            # Helper to copy file if exists
            def copy_file(src_name, dest_name=None):
                dest_name = dest_name or src_name
                src_file = os.path.join(extracted_folder, src_name)
                dest_file = os.path.join(fgc_dir, dest_name)
                if os.path.exists(src_file):
                    shutil.copy2(src_file, dest_file)
                    
            # Copy main files
            copy_file('main.py')
            copy_file('requirements.txt')
            copy_file('.dockerignore')
            copy_file('.gitignore')
            copy_file('LICENSE')
            
            # Copy src/ directory while preserving custom_notifier.py
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
                print("Preserved custom_notifier.py.")

            # Apply custom notifier patch to notifier.py
            patch_fgc_notifier(fgc_dir)

            # Clean up temp dir
            shutil.rmtree(temp_dir)
            print("Successfully copied source files.")
    except Exception as e:
        print(f"Error extracting and copying files: {e}")
        return

    # 3. Update version in config.yaml
    with open(fgc_config_path, 'r', encoding='utf-8') as f:
        content = f.read()
    new_content = re.sub(
        r'(version:\s*["\']?)[^"\']*(["\']?)',
        r'\g<1>' + target_version + r'\g<2>',
        content
    )
    with open(fgc_config_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_content)
    print("Updated version in config.yaml.")
    
    # 4. Update version in free_games_claimer/README.md
    if os.path.exists(fgc_readme_path):
        with open(fgc_readme_path, 'r', encoding='utf-8') as f:
            readme_content = f.read()
        
        pattern = r'(\*\*Current Version:\*\*\s*\[)[^\]]+(\]\(https://github.com/P-Adamiec/Free-Games-Claimer-Remaster/commit/)[^)]+(\))'
        if re.search(pattern, readme_content):
            new_readme_content = re.sub(
                pattern,
                r'\g<1>' + target_version + r'\g<2>' + sha + r'\g<3>',
                readme_content
            )
            with open(fgc_readme_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(new_readme_content)
            print("Updated version link in free_games_claimer/README.md")
    
    # 5. Update CHANGELOG.md
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

# Run both updaters
update_free_games_claimer()
