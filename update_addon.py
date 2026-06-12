import re
import urllib.request
import json
import os

# Определение путей относительно расположения этого скрипта
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, 'twitch_drops_miner', 'config.yaml')
digest_path = os.path.join(script_dir, 'twitch_drops_miner', 'docker_digest.txt')
readme_path = os.path.join(script_dir, 'README.md')
changelog_path = os.path.join(script_dir, 'twitch_drops_miner', 'CHANGELOG.md')

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
    exit(1)

# Находим хэш (digest) для тега 'latest'
latest_digest = None
for t in tags:
    if t.get('name') == 'latest':
        latest_digest = t.get('digest')
        break

if not latest_digest:
    print("Could not find 'latest' tag digest in API response.")
    exit(1)

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
    exit(0)

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
        exit(1)
else:
    print(f"Error: config.yaml not found at {config_path}")
    exit(1)

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
