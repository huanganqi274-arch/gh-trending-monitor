"""
SQLite 存储层。

每天抓一次，把榜单存成一张"快照"。
有了历史快照，就能算出 GitHub 官方页面给不了的东西：
  - 哪些是今天新上榜的
  - 在榜多少天了
  - 相比昨天，star 涨得更快还是在降温
"""

import os
import re
import sqlite3
from datetime import date, timedelta


def match_keywords(text, keywords):
    """
    关键词匹配，按词边界。

    为什么不用简单的"包含"判断：
      java  会匹配到 javascript
      ai    会匹配到 OpenMAIC
      rag   会匹配到 storage
    都是误判。所以要求关键词前后不能紧挨着字母，
    但允许紧挨数字和符号（crawl4ai 应该算命中 ai）。

    多词关键词（如 "agent framework"）同样适用。
    """
    text = (text or "").lower()
    hits = []
    for kw in keywords:
        kw = kw.lower().strip()
        if not kw:
            continue
        pattern = rf"(?<![a-z]){re.escape(kw)}(?![a-z])"
        if re.search(pattern, text):
            hits.append(kw)
    return hits

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    date         TEXT NOT NULL,
    since        TEXT NOT NULL,
    language     TEXT NOT NULL,
    rank         INTEGER,
    repo         TEXT NOT NULL,
    description  TEXT,
    lang         TEXT,
    stars        INTEGER,
    forks        INTEGER,
    period_stars INTEGER,
    source       TEXT DEFAULT 'trending',
    PRIMARY KEY (date, since, language, repo)
);
CREATE INDEX IF NOT EXISTS idx_repo ON snapshots(repo);
CREATE INDEX IF NOT EXISTS idx_board ON snapshots(since, language, date);
"""


def connect(db_path):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # 老版本的库没有 source 字段，补上
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(snapshots)")}
    if "source" not in columns:
        conn.execute("ALTER TABLE snapshots ADD COLUMN source TEXT DEFAULT 'trending'")
        conn.commit()
    return conn


def save(conn, items, since, language, on_date=None, source="trending"):
    """
    保存一次快照。

    一次快照 = 当天这个榜单的完整内容，所以先清掉当天旧记录再整体写入。
    否则同一天里既跑过正常抓取又跑过降级抓取时，两批数据会混在一起，
    榜单会出现重复排名。
    """
    on_date = on_date or date.today().isoformat()
    conn.execute(
        "DELETE FROM snapshots WHERE date=? AND since=? AND language=?",
        (on_date, since, language),
    )
    rows = [
        (on_date, since, language, i["rank"], i["repo"], i["description"],
         i["lang"], i["stars"], i["forks"], i["period_stars"], source)
        for i in items
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO snapshots "
        "(date, since, language, rank, repo, description, lang, stars, forks, "
        "period_stars, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return len(rows)


def latest_date(conn, since, language):
    row = conn.execute(
        "SELECT MAX(date) AS d FROM snapshots WHERE since=? AND language=?",
        (since, language),
    ).fetchone()
    return row["d"] if row and row["d"] else None


def get_board(conn, since, language, on_date=None, keywords=None):
    """
    取某一天的完整榜单，并补上历史维度：
      is_new       今天第一次出现在这个榜上
      days_on      累计在榜天数
      star_change  今日新增 star 相比上一次抓取的变化量
      matched      命中的关注关键词列表
    """
    on_date = on_date or latest_date(conn, since, language)
    if not on_date:
        return []

    keywords = [k.lower() for k in (keywords or [])]

    rows = conn.execute(
        "SELECT * FROM snapshots WHERE since=? AND language=? AND date=? ORDER BY rank",
        (since, language, on_date),
    ).fetchall()

    # 上一次抓取的日期（不一定是昨天，可能中间跳过了）
    prev_row = conn.execute(
        "SELECT MAX(date) AS d FROM snapshots WHERE since=? AND language=? AND date < ?",
        (since, language, on_date),
    ).fetchone()
    prev_date = prev_row["d"] if prev_row and prev_row["d"] else None

    prev_map = {}
    if prev_date:
        for r in conn.execute(
            "SELECT repo, period_stars, stars FROM snapshots "
            "WHERE since=? AND language=? AND date=?",
            (since, language, prev_date),
        ):
            prev_map[r["repo"]] = {"period_stars": r["period_stars"], "stars": r["stars"]}

    board = []
    for r in rows:
        repo = r["repo"]

        history = conn.execute(
            "SELECT COUNT(DISTINCT date) AS days, MIN(date) AS first_seen "
            "FROM snapshots WHERE since=? AND language=? AND repo=? AND date<=?",
            (since, language, repo, on_date),
        ).fetchone()

        prev = prev_map.get(repo)
        matched = match_keywords(f"{repo} {r['description'] or ''}", keywords)

        source = r["source"] or "trending"
        period_stars = r["period_stars"]
        gain_is_approx = False
        if source != "trending" and not period_stars and prev:
            # Search API 不给周期增量，用我们自己两次快照的总 star 差值近似
            period_stars = max(0, r["stars"] - prev["stars"])
            gain_is_approx = True

        board.append({
            "rank": r["rank"],
            "repo": repo,
            "url": f"https://github.com/{repo}",
            "description": r["description"] or "",
            "lang": r["lang"] or "",
            "stars": r["stars"],
            "forks": r["forks"],
            "period_stars": period_stars,
            "gain_is_approx": gain_is_approx,
            "source": source,
            "is_new": prev is None and bool(prev_date),
            "days_on": history["days"] if history else 1,
            "first_seen": history["first_seen"] if history else on_date,
            "star_change": (
                (r["period_stars"] - prev["period_stars"])
                if prev and source == "trending" and not gain_is_approx
                else None
            ),
            "matched": matched,
        })

    return board


def board_dates(conn, since, language, limit=30):
    rows = conn.execute(
        "SELECT DISTINCT date FROM snapshots WHERE since=? AND language=? "
        "ORDER BY date DESC LIMIT ?",
        (since, language, limit),
    ).fetchall()
    return [r["date"] for r in rows]


def prune(conn, keep_days=180):
    """清理超过保留期的老快照，避免库无限增长"""
    cutoff = (date.today() - timedelta(days=keep_days)).isoformat()
    cur = conn.execute("DELETE FROM snapshots WHERE date < ?", (cutoff,))
    conn.commit()
    return cur.rowcount
