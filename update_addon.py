import re
import urllib.request
import json
import os

# Определение путей относительно расположения этого скрипта
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, 'twitch_drops_miner', 'config.yaml')
digest_path = os.path.join(script_dir, 'twitch_drops_miner', 'docker_digest.txt')

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

# Формируем целевую версию (добавляем 'v', если пользователь так просит)
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
