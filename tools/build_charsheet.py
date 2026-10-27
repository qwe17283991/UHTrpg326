#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角卡工具資料建置

從原始角卡試算表（例如「無限恐怖3.0 賽德納洲.xlsx」）產生：
  charsheet/template.xlsx  精簡樣板（另存一份 template.js 給網頁載入）：只保留「空白卡」「缺陷 3xx」「天賦 3xx」三張表，
                           其餘內容（公式、格式、合併儲存格、下拉選單、註解）原封不動。
  charsheet/data.js        缺陷、天賦清單（網頁下拉選單用）

從網站頁面產生（不需要試算表）：
  charsheet/rules.js       專長、怪癖清單，以及每個資源各等級的特性（網頁「帶入特性」用）

用法：
  python tools/build_charsheet.py "D:/下載/無限恐怖3.0 賽德納洲.xlsx"   # 全部重建
  python tools/build_charsheet.py --rules                                # 只重建 rules.js

規則表（缺陷、天賦）或空白卡有更新時用第一種；網站頁面有更新時用第二種
（推上 GitHub 時 Actions 也會自動跑第二種）。
"""

import base64
import json
import os
import posixpath
import re
import sys
import zipfile
from collections import defaultdict
from html import unescape

KEEP_SHEETS = ['空白卡', '缺陷 3xx', '天賦 3xx']
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'charsheet')


def rels_path(part):
    d, f = posixpath.split(part)
    return posixpath.join(d, '_rels', f + '.rels')


def rel_targets(z, part):
    """回傳 part 透過 .rels 連到的其他 part（絕對路徑）"""
    rp = rels_path(part)
    if rp not in z.namelist():
        return []
    xml = z.read(rp).decode('utf-8')
    base = posixpath.dirname(part)
    out = []
    for m in re.finditer(r'<Relationship [^>]*Target="([^"]+)"[^>]*/>', xml):
        if 'TargetMode="External"' in m.group(0):
            continue
        out.append(posixpath.normpath(posixpath.join(base, m.group(1))))
    return out


# 空白卡公式修正：(說明, 原本的寫法, 修正後的寫法)
# 若原始試算表已經改好，找不到原本的寫法時只會提示、不會出錯。
FORMULA_FIXES = [
    ('缺陷總等級漏算第 11 格缺陷（BS25）',
     '<f>SUM(BS5:BT24)</f>', '<f>SUM(BS5:BT26)</f>'),
    ('天賦剩餘點數漏扣第 5 格天賦（CO13）',
     'SUM($CO$5:$CP$12)</f>', 'SUM($CO$5:$CP$14)</f>'),
    ('檢定表「打遊戲、使用電腦」的附加查到空白的技能欄（應查 AF37 電腦）',
     re.compile(r'(<c r="BG38"[^>]*>)<f t="shared" si="\d+"/>'),
     r'\1<f>iferror(VLOOKUP(AU38,$CZ$155:$DI$186,5,false)+vlookup(AF37,$CZ$155:$DI$186,5,false),&quot;X&quot;)</f>'),
]


def fix_formulas(xml):
    for desc, old, new in FORMULA_FIXES:
        if isinstance(old, str):
            done = old in xml
            xml = xml.replace(old, new)
        else:
            xml, n = old.subn(new, xml)
            done = n > 0
        print(f'  公式修正：{desc} … {"已修正" if done else "找不到原本的寫法，略過"}')
    return xml


def build_template(src):
    z = zipfile.ZipFile(src)
    names = set(z.namelist())
    wb_xml = z.read('xl/workbook.xml').decode('utf-8')
    wb_rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')

    rid_target = {m.group(1): m.group(2) for m in re.finditer(r'<Relationship Id="([^"]+)"[^>]*Target="([^"]+)"', wb_rels)}
    sheets = re.findall(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"/>', wb_xml)
    keep_rids = {rid for name, rid in sheets if name in KEEP_SHEETS}
    drop_rids = {rid for name, rid in sheets if name not in KEEP_SHEETS}
    missing = set(KEEP_SHEETS) - {name for name, _ in sheets}
    if missing:
        sys.exit(f'找不到工作表：{missing}')

    # 要刪掉的工作表，以及只被它們用到的 part
    def closure(start):
        seen, stack = set(), list(start)
        while stack:
            p = stack.pop()
            if p in seen or p not in names:
                continue
            seen.add(p)
            stack.extend(rel_targets(z, p))
        return seen

    keep_parts = closure(['xl/' + rid_target[r] for r in keep_rids])
    drop_parts = closure(['xl/' + rid_target[r] for r in drop_rids]) - keep_parts
    drop_files = drop_parts | {rels_path(p) for p in drop_parts}
    drop_files.add('xl/calcChain.xml')  # 由試算表重建

    # workbook.xml：移除工作表；definedName 的 localSheetId 依新順序重編
    kept_order = [name for name, rid in sheets if rid in keep_rids]
    def fix_sheet(m):
        return m.group(0) if m.group(2) in keep_rids else ''
    wb_xml = re.sub(r'<sheet [^>]*name="([^"]+)"[^>]*r:id="([^"]+)"/>', fix_sheet, wb_xml)
    old_index = {i: name for i, (name, _) in enumerate(sheets)}
    def fix_dn(m):
        name = old_index.get(int(m.group(1)))
        return f'localSheetId="{kept_order.index(name)}"' if name in kept_order else m.group(0)
    wb_xml = re.sub(r'localSheetId="(\d+)"', fix_dn, wb_xml)
    # 打開時全部重算（Excel 用；Google 試算表匯入時本來就會重算）
    wb_xml = re.sub(r'<calcPr[^>]*/>', '<calcPr fullCalcOnLoad="1"/>', wb_xml)
    wb_rels = re.sub(r'<Relationship Id="(%s)"[^>]*/>' % '|'.join(map(re.escape, drop_rids)), '', wb_rels)

    ct = z.read('[Content_Types].xml').decode('utf-8')
    for p in drop_files:
        ct = ct.replace(f'<Override PartName="/{p}"', '<Override PartName="__DROP__"')
    ct = re.sub(r'<Override PartName="__DROP__"[^>]*/>', '', ct)

    blank = 'xl/' + rid_target[next(rid for name, rid in sheets if name == '空白卡')]

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, 'template.xlsx')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as o:
        for info in z.infolist():
            n = info.filename
            if n in drop_files:
                continue
            data = z.read(n)
            if n == blank:
                data = fix_formulas(data.decode('utf-8')).encode('utf-8')
            elif n == 'xl/workbook.xml':
                data = wb_xml.encode('utf-8')
            elif n == 'xl/_rels/workbook.xml.rels':
                data = wb_rels.encode('utf-8')
            elif n == '[Content_Types].xml':
                data = ct.encode('utf-8')
            o.writestr(info, data)
    print(f'  樣板：{out}（{os.path.getsize(out) // 1024} KB，保留 {", ".join(kept_order)}）')

    # 同一份樣板包成 .js，讓網頁直接用 <script> 載入（雙擊開啟 file:// 時也能用）
    js = os.path.join(OUT_DIR, 'template.js')
    with open(out, 'rb') as f, open(js, 'w', encoding='utf-8', newline='\n') as o:
        o.write('// 由 tools/build_charsheet.py 產生：charsheet/template.xlsx 的 base64\n')
        o.write('window.CHARSHEET_TEMPLATE = "' + base64.b64encode(f.read()).decode('ascii') + '";\n')
    print(f'  樣板（網頁用）：{js}')


def build_data(src):
    import openpyxl
    wb = openpyxl.load_workbook(src, read_only=True)

    def table(sheet):
        items, cat = [], ''
        for row in wb[sheet].iter_rows(min_row=2, values_only=True):
            num, name, pre, eff = (list(row) + [None] * 4)[:4]
            name = (str(name).strip() if name is not None else '')
            if not name or name == '-':
                continue
            if num is None and name.endswith('：'):
                cat = name.rstrip('：')
                continue
            m = re.search(r'[（(]\s*([+-]?\d+)\s*[)）]\s*$', name)
            items.append({
                'name': name,
                'cost': int(m.group(1)) if m else None,
                'cat': cat,
                'pre': '' if pre in (None, '-') else str(pre).strip(),
                'effect': '' if eff in (None, '-') else str(eff).strip(),
            })
        return items

    data = {'flaws': table('缺陷 3xx'), 'talents': table('天賦 3xx')}
    out = os.path.join(OUT_DIR, 'data.js')
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write('// 由 tools/build_charsheet.py 產生，請勿手動編輯\n')
        f.write('window.CHARSHEET_DATA = ')
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write(';\n')
    print(f'  資料：{out}（缺陷 {len(data["flaws"])} 項、天賦 {len(data["talents"])} 項）')


# ============================================================
# 從網站頁面抽取專長、怪癖、資源特性
# ============================================================

def page_lines(path):
    """把 .htm 轉成一行一行的純文字"""
    with open(path, encoding='utf-8', errors='ignore') as f:
        c = f.read()
    c = re.sub(r'(?is)<(style|script)[^>]*>.*?</\1>', '', c)
    c = re.sub(r'(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>', '\n', c)
    c = unescape(re.sub(r'<[^>]+>', '', c)).replace('\xa0', ' ')
    lines = (re.sub(r'[ \t　]+', ' ', l).strip() for l in c.split('\n'))
    return [l for l in lines if l]


def load_tree():
    with open(os.path.join(ROOT, '___left_data.js'), encoding='utf-8') as f:
        rows = re.findall(r'^d\.add\((\d+),(-?\d+),"([^"]*)","([^"]*)"\);?$', f.read(), re.M)
    node, kids = {}, defaultdict(list)
    for i, p, n, u in rows:
        node[int(i)] = (int(p), n, '' if u.startswith('$$') else u)
        kids[int(p)].append(int(i))
    return node, kids


def find(node, name, parent=None):
    for i, (p, n, u) in node.items():
        if n == name and (parent is None or p == parent):
            return i
    return None


def leaves(node, kids, i):
    out = []
    for k in kids[i]:
        if node[k][2]:
            out.append(k)
        out += leaves(node, kids, k)
    return out


SEP = re.compile(r'^[=＝]{5,}$')
FEAT_HEAD = re.compile(r'^(.{1,30}?)\s*[（(]\s*(\d+(?:\s*[~～\-－]\s*\d+)?)\s*[)）]\s*[:：]?$')


def parse_feats(lines, cat, url):
    """專長：「名稱（1~5）」開頭，下一行通常是「前提：」"""
    out = []
    for i, l in enumerate(lines):
        m = FEAT_HEAD.match(l)
        if not m or re.search(r'[:：]', m.group(1)):
            continue
        pre = next((re.split(r'[:：]', x, maxsplit=1)[1] for x in lines[i + 1:i + 3] if re.match(r'^前提\s*[:：]', x)), '')
        out.append({'name': m.group(1).strip(), 'lv': re.sub(r'\s*[~～\-－]\s*', '~', m.group(2).strip()),
                    'cat': cat, 'pre': pre.strip(), 'url': url})
    return out


LEVEL_HEAD = re.compile(r'^(?:等級)?([DCBAS]{1,2})(?:級)?(?:\s*[:：].*)?$|^([DCBAS]{1,2})級')
PRICE = re.compile(r'^價格\s*[:：]\s*([DCBAS]{1,2})\s*[+＋]')


def parse_traits(lines):
    """資源各等級的特性：以「價格：D+500」或「D級：」判斷目前等級，收集「特性：」那一行"""
    levels, cur = [], None
    for l in lines:
        m = PRICE.match(l)
        if m:
            cur = m.group(1)
        elif len(l) <= 20:
            m = LEVEL_HEAD.match(l)
            if m and (m.group(1) or m.group(2)):
                cur = m.group(1) or m.group(2)
        if re.match(r'^特性\s*[:：]', l):
            body = re.split(r'[:：]', l, maxsplit=1)[1].strip()
            if not body or body in ('無', '-'):
                continue
            names = [x.strip() for x in re.split(r'[、，,；;]', body) if x.strip()]
            levels.append([cur or '', names])
    return levels


def build_rules():
    node, kids = load_tree()
    feats, quirks, traits = [], [], {}

    # 一般專長：規則部分 → 專長概述 底下的各專長頁
    ov = find(node, '專長概述', find(node, '建立人物卡來參與遊戲'))
    skip = {'專長概述', '缺陷', '怪癖', '天賦'}

    def walk(i):
        for k in kids[i]:
            p, n, u = node[k]
            if n in skip:
                continue
            if u and os.path.exists(os.path.join(ROOT, u)):
                feats.extend(parse_feats(page_lines(os.path.join(ROOT, u)), n, u))
            walk(k)
    if ov is not None:
        walk(ov)

    # 怪癖
    qid = find(node, '怪癖')
    if qid is not None and node[qid][2]:
        lines, cat = page_lines(os.path.join(ROOT, node[qid][2])), ''
        for i, l in enumerate(lines):
            if re.search(r'類怪癖\s*[:：]$', l):
                cat = re.sub(r'\s*[:：]$', '', l)
            # 怪癖名稱是分隔線後的第一行，接著（可能隔一行「前提」）是「描述」
            elif i and SEP.match(lines[i - 1]) and len(l) <= 20 and any(x.startswith('描述') for x in lines[i + 1:i + 3]):
                pre = next((re.split(r'[:：]', x, maxsplit=1)[-1].strip() for x in lines[i + 1:i + 2] if x.startswith('前提')), '')
                j = next(j for j in range(i + 1, i + 3) if lines[j].startswith('描述'))
                desc = re.split(r'[:：]', lines[j], maxsplit=1)[-1].strip()
                eff = next((re.split(r'[:：]', x, maxsplit=1)[-1].strip() for x in lines[j + 1:j + 4] if x.startswith('效果')), '')
                quirks.append({'name': re.sub(r'\s*[:：]$', '', l), 'cat': cat, 'pre': pre, 'desc': desc, 'effect': eff, 'url': node[qid][2]})

    # 資源：各等級特性、資源專屬專長
    for k in leaves(node, kids, find(node, '資源部分')):
        u = node[k][2]
        path = os.path.join(ROOT, u)
        if not os.path.exists(path):
            continue
        lines = page_lines(path)
        t = parse_traits(lines)
        if t:
            traits[u] = t
        for i, l in enumerate(lines):
            if len(l) <= 40 and re.search(r'專屬.{0,12}專長\s*[:：]?$', l):
                block = []
                for x in lines[i + 1:]:
                    if re.search(r'技能樹\s*[:：]$', x):
                        break
                    block.append(x)
                for f in parse_feats(block, '資源專屬', u):
                    f['src'] = node[k][1]
                    feats.append(f)

    data = {'feats': feats, 'quirks': quirks, 'traits': traits}
    out = os.path.join(OUT_DIR, 'rules.js')
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write('// 由 tools/build_charsheet.py --rules 從網站頁面產生，請勿手動編輯\n')
        f.write('window.CHARSHEET_RULES = ')
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    spec = sum(1 for x in feats if x['cat'] == '資源專屬')
    print(f'  規則：{out}（專長 {len(feats) - spec} 項＋資源專屬專長 {spec} 項、怪癖 {len(quirks)} 項、'
          f'{len(traits)} 個資源頁有特性，{os.path.getsize(out) // 1024} KB）')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print('建置角卡工具資料…')
    if sys.argv[1] != '--rules':
        build_template(sys.argv[1])
        build_data(sys.argv[1])
    build_rules()
    print('完成！')
