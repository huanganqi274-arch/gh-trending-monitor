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


def get_merged_board(conn, since, languages, keywords=None):
    """
    把多个语言榜合并成一份更全的当日榜单。

    为什么需要：GitHub 的全语言日榜单页最多 25 条，今天往往只有十几条。
    各语言的日榜也都是"今天热度最高的"，合起来去重、按今日新增 star 重新排序，
    就得到一份覆盖更广的当日热榜。

    is_new / days_on 的比较也在合并后的集合上做，保证口径一致。
    """
    keywords = [k.lower() for k in (keywords or [])]

    def snapshot(on_date):
        """取某一天、这些语言榜合并去重后的项目字典"""
        merged = {}
        for lang in languages:
            for r in conn.execute(
                "SELECT * FROM snapshots WHERE since=? AND language=? AND date=?",
                (since, lang, on_date),
            ):
                repo = r["repo"]
                # 同一个项目可能同时出现在全语言榜和某语言榜，取新增 star 更大的那条
                if repo not in merged or r["period_stars"] > merged[repo]["period_stars"]:
                    merged[repo] = dict(r)
        return merged

    placeholders = ",".join("?" for _ in languages)
    row = conn.execute(
        f"SELECT MAX(date) AS d FROM snapshots WHERE since=? AND language IN ({placeholders})",
        (since, *languages),
    ).fetchone()
    on_date = row["d"] if row and row["d"] else None
    if not on_date:
        return []

    prev_row = conn.execute(
        f"SELECT MAX(date) AS d FROM snapshots WHERE since=? AND language IN ({placeholders}) AND date < ?",
        (since, *languages, on_date),
    ).fetchone()
    prev_date = prev_row["d"] if prev_row and prev_row["d"] else None

    today = snapshot(on_date)
    prev = snapshot(prev_date) if prev_date else {}

    ordered = sorted(today.values(), key=lambda r: r["period_stars"], reverse=True)

    board = []
    for rank, r in enumerate(ordered, start=1):
        repo = r["repo"]
        days = conn.execute(
            f"SELECT COUNT(DISTINCT date) AS days, MIN(date) AS first_seen FROM snapshots "
            f"WHERE since=? AND language IN ({placeholders}) AND repo=? AND date<=?",
            (since, *languages, repo, on_date),
        ).fetchone()
        p = prev.get(repo)
        source = r.get("source") or "trending"

        board.append({
            "rank": rank,
            "repo": repo,
            "url": f"https://github.com/{repo}",
            "description": r["description"] or "",
            "lang": r["lang"] or "",
            "stars": r["stars"],
            "forks": r["forks"],
            "period_stars": r["period_stars"],
            "gain_is_approx": False,
            "source": source,
            "is_new": p is None and bool(prev_date),
            "days_on": days["days"] if days else 1,
            "first_seen": days["first_seen"] if days else on_date,
            "star_change": (r["period_stars"] - p["period_stars"]) if p else None,
            "matched": match_keywords(f"{repo} {r['description'] or ''}", keywords),
            "_date": on_date,
        })
    return board
