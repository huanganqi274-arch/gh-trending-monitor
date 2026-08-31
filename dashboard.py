"""
生成一个静态 HTML 面板。

不需要服务器：跑完直接双击 docs/index.html 就能看，
也可以推到 GitHub Pages 变成一个团队内部都能访问的地址。
"""

import html
import json
import os
from datetime import datetime

PERIOD_NAME = {"daily": "日榜", "weekly": "周榜", "monthly": "月榜"}


def _esc(text):
    return html.escape(text or "", quote=True)


def _row_html(item, max_delta):
    width = 0
    if max_delta > 0:
        width = max(2, round(item["period_stars"] / max_delta * 100))

    chips = []
    if item["is_new"]:
        chips.append('<span class="chip chip-new">新</span>')
    if item.get("gain_is_approx"):
        chips.append('<span class="chip">增量为估算</span>')
    elif item["days_on"] > 1:
        chips.append(f'<span class="chip">在榜 {item["days_on"]} 天</span>')
    if item["lang"]:
        chips.append(f'<span class="chip">{_esc(item["lang"])}</span>')

    change = ""
    if item["star_change"] is not None and item["star_change"] != 0:
        rising = item["star_change"] > 0
        cls = "up" if rising else "down"
        arrow = "▲" if rising else "▼"
        change = (f'<span class="delta {cls}">{arrow} 比上次'
                  f'{"多" if rising else "少"} {abs(item["star_change"]):,}</span>')

    watched = " watched" if item["matched"] else ""
    desc = _esc(item["description"]) or "<span class=\"nodesc\">该项目没有写描述</span>"

    return f"""
      <tr class="row{watched}">
        <td class="rank">{item['rank']}</td>
        <td class="repo">
          <a href="{_esc(item['url'])}" target="_blank" rel="noopener">{_esc(item['repo'])}</a>
          <p class="desc">{desc}</p>
          <div class="chips">{''.join(chips)}</div>
        </td>
        <td class="gain">
          <span class="num">{'≈' if item.get('gain_is_approx') else ''}+{item['period_stars']:,}</span>
          {change}
          <div class="bar" style="width:{width}%"></div>
        </td>
        <td class="total">{item['stars']:,}</td>
      </tr>"""


def _board_html(key, board):
    items = board["items"]
    if not items:
        return f'<section class="board" data-board="{key}"><p class="empty">还没有抓到这个榜单的数据。跑一次 <code>python run.py fetch</code> 就有了。</p></section>'

    max_delta = max((i["period_stars"] for i in items), default=0)
    new_count = sum(1 for i in items if i["is_new"])
    watch_count = sum(1 for i in items if i["matched"])

    rows = "".join(_row_html(i, max_delta) for i in items)

    banner = ""
    if any(i.get("source") not in (None, "trending") for i in items):
        banner = (
            '<p class="banner">这一期来自备用数据源（GitHub 官方 Search API），'
            '因为 trending 页面没抓到数据。排序按总 star 数，不是热度增速，'
            '新增量是用历史快照估算的。抓取脚本可能需要检修。</p>'
        )

    return f"""
    <section class="board" data-board="{key}">
      {banner}
      <p class="lede">
        {board['date']} 的榜单上有 <b>{len(items)}</b> 个项目，其中
        <b>{new_count}</b> 个是今天新冒出来的，
        <b>{watch_count}</b> 个命中了你设的关注方向。
      </p>
      <table>
        <thead>
          <tr><th>排名</th><th>项目</th><th>新增 star</th><th>总计</th></tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </section>"""


CSS = """
:root {
  --bg: #f2f3f5;
  --surface: #ffffff;
  --ink: #1f2329;
  --muted: #646a73;
  --line: #dee0e3;
  --rise: #f54a45;
  --fall: #2ea121;
  --accent: #3370ff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
               system-ui, -apple-system, sans-serif;
  font-size: 15px;
  line-height: 1.6;
  font-variant-numeric: tabular-nums;
}
.wrap { max-width: 1000px; margin: 0 auto; padding: 40px 20px 80px; }
header { margin-bottom: 28px; }
h1 { font-size: 22px; font-weight: 600; margin: 0 0 4px; letter-spacing: -0.01em; }
.meta { color: var(--muted); font-size: 13px; margin: 0; }
nav { display: flex; flex-wrap: wrap; gap: 4px; margin: 24px 0 0; }
nav button {
  border: 1px solid transparent; background: none; cursor: pointer;
  font: inherit; font-size: 14px; color: var(--muted);
  padding: 6px 12px; border-radius: 6px;
}
nav button:hover { background: rgba(31,35,41,.05); color: var(--ink); }
nav button[aria-selected="true"] {
  background: var(--surface); color: var(--ink);
  border-color: var(--line); font-weight: 500;
}
nav button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.board { display: none; }
.board.active { display: block; }
.lede { margin: 22px 0 16px; color: var(--muted); font-size: 14px; }
.lede b { color: var(--ink); font-weight: 600; }
table { width: 100%; border-collapse: collapse; background: var(--surface);
        border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
thead th {
  text-align: left; font-size: 12px; font-weight: 500; color: var(--muted);
  padding: 10px 14px; border-bottom: 1px solid var(--line); background: #fafbfc;
  white-space: nowrap;
}
thead th:nth-child(3), thead th:nth-child(4) { text-align: right; }
.row td { padding: 14px; border-bottom: 1px solid var(--line); vertical-align: top; }
.row:last-child td { border-bottom: none; }
.row:hover td { background: #fafbfc; }
.row.watched td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
.rank { width: 62px; color: var(--muted); font-size: 14px; padding-left: 18px !important; }
.repo a { color: var(--ink); text-decoration: none; font-weight: 600; font-size: 15px; }
.repo a:hover { color: var(--accent); text-decoration: underline; }
.desc {
  margin: 3px 0 6px; color: var(--muted); font-size: 13.5px; max-width: 62ch;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.nodesc { color: #a5abb3; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  font-size: 11.5px; color: var(--muted); background: #f2f3f5;
  padding: 1px 7px; border-radius: 4px;
}
.chip-new { background: rgba(245,74,69,.1); color: var(--rise); font-weight: 500; }
.gain { width: 170px; text-align: right; }
.gain .num { font-weight: 600; color: var(--rise); font-size: 15px; }
.gain .bar {
  height: 3px; background: var(--rise); opacity: .3; border-radius: 2px;
  margin: 6px 0 0 auto;
}
.delta { display: block; font-size: 12px; color: var(--muted); margin-top: 1px; }
.delta.up { color: var(--rise); }
.delta.down { color: var(--fall); }
.total { width: 100px; text-align: right; color: var(--muted); font-size: 14px; }
.empty { color: var(--muted); padding: 40px 0; }
.banner {
  margin: 22px 0 0; padding: 11px 14px; font-size: 13.5px;
  background: #fff8e6; border: 1px solid #f5d99b; border-radius: 6px;
  color: #7a5b12; max-width: 70ch;
}
code { background: rgba(31,35,41,.06); padding: 1px 5px; border-radius: 3px; font-size: 13px; }
footer { margin-top: 32px; color: var(--muted); font-size: 12.5px; }
@media (max-width: 640px) {
  .wrap { padding: 24px 14px 60px; }
  thead { display: none; }
  .row td { display: block; border-bottom: none; padding: 4px 14px; }
  .row { display: block; border-bottom: 1px solid var(--line); padding: 10px 0; }
  .rank { color: var(--muted); font-size: 12px; padding-left: 14px !important; }
  .gain, .total { width: auto; text-align: left; }
  .gain .bar { display: none; }
  .total { padding-bottom: 12px !important; }
}
"""

JS = """
const tabs = document.querySelectorAll('nav button');
const boards = document.querySelectorAll('.board');
tabs.forEach(tab => tab.addEventListener('click', () => {
  tabs.forEach(t => t.setAttribute('aria-selected', String(t === tab)));
  boards.forEach(b => b.classList.toggle('active', b.dataset.board === tab.dataset.board));
}));
"""


def render(boards, output_path):
    """
    boards: { key: {"label": "日榜 · 全部语言", "date": "2026-08-30", "items": [...]} }
    """
    keys = list(boards.keys())
    tabs = "".join(
        f'<button data-board="{k}" aria-selected="{"true" if i == 0 else "false"}">'
        f'{_esc(boards[k]["label"])}</button>'
        for i, k in enumerate(keys)
    )
    sections = "".join(
        _board_html(k, boards[k]).replace('class="board"', 'class="board active"', 1)
        if i == 0 else _board_html(k, boards[k])
        for i, k in enumerate(keys)
    )
    updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GitHub Trending 监控</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>GitHub Trending 监控</h1>
    <p class="meta">更新于 {updated}　左侧蓝线标记的是命中关注方向的项目</p>
    <nav>{tabs}</nav>
  </header>
  {sections}
  <footer>数据来自 github.com/trending，每天抓取一次并保留历史快照。</footer>
</div>
<script>{JS}</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return output_path
