#!/usr/bin/env python3
"""
搜尋索引建立腳本
================
掃描所有 .htm/.html 檔案，提取標題和內文，
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

# 網站資料夾路徑（'.' 代表腳本所在的資料夾）
SITE_DIR = '.'

# 每個頁面最多保留多少字的內文（太多會讓 JSON 檔案過大）
MAX_CONTENT_LENGTH = 3000

# 要跳過的檔案名稱關鍵字
SKIP_FILES = ['___', 'index', 'search', '$$unsavedpage']

# ============================================================
# 主程式
# ============================================================

index_data = []
skipped = 0
errors = 0

print("正在建立搜尋索引...")
print()

for root, dirs, files in os.walk(SITE_DIR):
    for file in files:
        if not (file.endswith('.htm') or file.endswith('.html')):
            continue

        # 跳過系統檔案
        if any(skip in file for skip in SKIP_FILES):
            skipped += 1
            continue

        file_path = os.path.join(root, file)
        rel_path = os.path.relpath(file_path, SITE_DIR).replace('\\', '/')

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            soup = BeautifulSoup(content, 'html.parser')

            # 移除 script 和 style 標籤的內容
            for tag in soup(['script', 'style']):
                tag.decompose()

            # 取得標題
            title = ''
            if soup.title and soup.title.string:
                title = soup.title.string.strip()
            if not title:
                # 用檔名當標題（去掉副檔名）
                title = os.path.splitext(file)[0]

            # 取得內文
            text = soup.get_text(separator=' ', strip=True)
            # 清理多餘空白
            text = re.sub(r'\s+', ' ', text).strip()
            # 限制長度
            if len(text) > MAX_CONTENT_LENGTH:
                text = text[:MAX_CONTENT_LENGTH]

            index_data.append({
                'title': title,
                'url': rel_path,
                'content': text
            })

        except Exception as e:
            errors += 1
            print(f"  ✗ 無法讀取 {file}: {e}")

# 按標題排序
index_data.sort(key=lambda x: x['title'])

# 輸出 JSON
output_path = os.path.join(SITE_DIR, 'search.json')
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(index_data, f, ensure_ascii=False)

# 計算檔案大小
file_size = os.path.getsize(output_path)
if file_size > 1024 * 1024:
    size_str = f"{file_size / 1024 / 1024:.1f} MB"
else:
    size_str = f"{file_size / 1024:.0f} KB"

print()
print("=" * 50)
print(f"  索引頁面數：{len(index_data)}")
print(f"  跳過檔案數：{skipped}")
print(f"  讀取失敗數：{errors}")
print(f"  search.json：{size_str}")
print("=" * 50)
print()

if file_size > 5 * 1024 * 1024:
    print(f"⚠ search.json 超過 5MB，可能導致載入緩慢。")
    print(f"  建議將 MAX_CONTENT_LENGTH 從 {MAX_CONTENT_LENGTH} 降低。")
print("完成！請將 search.json 和 search.html 一起上傳到網站。")
