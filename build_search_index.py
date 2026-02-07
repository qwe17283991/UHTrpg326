#!/usr/bin/env python3
"""
搜尋索引建立腳本（含目錄路徑）
================================
掃描所有 .htm/.html 檔案，提取標題和內文，
並從 ___left.htm 的樹狀結構提取完整目錄路徑，
生成 search.json 供前端搜尋頁面使用。

使用方式：
    1. pip install beautifulsoup4
    2. 把此腳本放到你的網站資料夾裡
    3. 執行：python build_search_index.py
    4. 會在同資料夾生成 search.json
"""

import os
import json
import re
from bs4 import BeautifulSoup

# ============================================================
# 設定區
# ============================================================

SITE_DIR = '.'
MAX_CONTENT_LENGTH = 3000
SKIP_FILES = ['___', 'index', 'search', '$$unsavedpage']
LEFT_FILE = '___left.htm'

# ============================================================
# 從 ___left.htm 建立目錄路徑
# ============================================================

def build_breadcrumbs(site_dir):
    """從 ___left.htm 解析 d.add() 呼叫，建立每個檔案的完整目錄路徑"""
    left_path = os.path.join(site_dir, LEFT_FILE)
    if not os.path.exists(left_path):
        print(f"  找不到 {LEFT_FILE}，跳過目錄路徑建立")
        return {}

    with open(left_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # 解析所有 d.add(id, parent_id, "顯示名稱", "檔案名稱")
    pattern = r'd\.add\(\s*(\d+)\s*,\s*(-?\d+)\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\)'
    matches = re.findall(pattern, content)

    nodes = {}
    for match in matches:
        node_id = int(match[0])
        parent_id = int(match[1])
        name = match[2]
        url = match[3]
        nodes[node_id] = {
            'parent_id': parent_id,
            'name': name,
            'url': url
        }

    url_to_breadcrumb = {}

    def get_path(node_id):
        path = []
        current = node_id
        visited = set()
        while current in nodes and current not in visited:
            visited.add(current)
            path.append(nodes[current]['name'])
            current = nodes[current]['parent_id']
        path.reverse()
        return path

    for node_id, node in nodes.items():
        url = node['url']
        if url and not url.startswith('$$'):
            path = get_path(node_id)
            breadcrumb = ' → '.join(path)
            url_to_breadcrumb[url] = breadcrumb

    print(f"  從 {LEFT_FILE} 解析了 {len(url_to_breadcrumb)} 個目錄路徑")
    return url_to_breadcrumb

# ============================================================
# 主程式
# ============================================================

print("正在建立搜尋索引...")
print()

print("步驟 1/2：解析目錄結構...")
url_to_breadcrumb = build_breadcrumbs(SITE_DIR)

print("步驟 2/2：掃描檔案內容...")
index_data = []
skipped = 0
errors = 0

for root, dirs, files in os.walk(SITE_DIR):
    for file in files:
        if not (file.endswith('.htm') or file.endswith('.html')):
            continue

        if any(skip in file for skip in SKIP_FILES):
            skipped += 1
            continue

        file_path = os.path.join(root, file)
        rel_path = os.path.relpath(file_path, SITE_DIR).replace('\\', '/')

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            soup = BeautifulSoup(content, 'html.parser')

            for tag in soup(['script', 'style']):
                tag.decompose()

            for font in soup.find_all('font', class_='dtree'):
                font.decompose()

            title = ''
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            if not title:
                title = os.path.splitext(file)[0]

            text = soup.get_text(separator=' ', strip=True)
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) > MAX_CONTENT_LENGTH:
                text = text[:MAX_CONTENT_LENGTH]

            breadcrumb = url_to_breadcrumb.get(rel_path, '')

            entry = {
                'title': title,
                'url': rel_path,
                'content': text
            }
            if breadcrumb:
                entry['path'] = breadcrumb

            index_data.append(entry)

        except Exception as e:
            errors += 1
            print(f"  ✗ 無法讀取 {file}: {e}")

index_data.sort(key=lambda x: x['title'])

output_path = os.path.join(SITE_DIR, 'search.json')
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(index_data, f, ensure_ascii=False)

file_size = os.path.getsize(output_path)
if file_size > 1024 * 1024:
    size_str = f"{file_size / 1024 / 1024:.1f} MB"
else:
    size_str = f"{file_size / 1024:.0f} KB"

print()
print("=" * 50)
print(f"  索引頁面數：{len(index_data)}")
print(f"  含目錄路徑：{sum(1 for d in index_data if 'path' in d)}")
print(f"  跳過檔案數：{skipped}")
print(f"  讀取失敗數：{errors}")
print(f"  search.json：{size_str}")
print("=" * 50)
print()
print("完成！")
