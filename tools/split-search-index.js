// 將 search.json 拆成 search-index/ 底下的小檔案，讓全文搜尋可以分段、平行載入。
// 每次更新 search.json 後，在專案根目錄執行：
//   node tools/split-search-index.js
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const OUT = path.join(ROOT, 'search-index');
const CHUNKS = 6;

const data = JSON.parse(fs.readFileSync(path.join(ROOT, 'search.json'), 'utf8'));

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT);

// 標題檔：只含標題、網址、路徑，檔案小，先載入讓標題搜尋馬上能用
const titles = data.map(d => [d.title, d.url, d.path || '']);
fs.writeFileSync(path.join(OUT, 'titles.json'), JSON.stringify(titles));

// 內文檔：依順序切成 CHUNKS 份，每份是內文字串陣列
const size = Math.ceil(data.length / CHUNKS);
const chunks = [];
for (let i = 0; i < CHUNKS; i++) {
  const start = i * size;
  const part = data.slice(start, start + size).map(d => d.content || '');
  if (part.length === 0) break;
  const file = `content-${i}.json`;
  fs.writeFileSync(path.join(OUT, file), JSON.stringify(part));
  chunks.push({ file, start });
}

fs.writeFileSync(path.join(OUT, 'manifest.json'),
  JSON.stringify({ total: data.length, version: Date.now(), chunks }));

console.log(`完成：${data.length} 個頁面，${chunks.length} 個內文分段 → search-index/`);
