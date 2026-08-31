"""
备用数据源：GitHub 官方 Search API。

爬虫解析不到数据时（通常是 GitHub 改版了页面结构）自动降级到这里。

要说清楚的是：Search API 给的不是 Trending 榜。
Trending 的排序算法是黑箱，掺了 star 增速、fork、贡献者等因素；
这里只能做到"最近创建 + 按总 star 排序"，是个近似。

但它是官方接口、有正式文档、有明确的速率限制，
所以爬虫失效时它能保证你不会完全瞎掉。
"""

import os
from datetime import date, timedelta

import requests

SEARCH_URL = "https://api.github.com/search/repositories"

# 各周期对应"最近多久创建的仓库"
WINDOW_DAYS = {"daily": 14, "weekly": 30, "monthly": 90}


def _headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # 匿名调用限 10 次/分钟，带 token 是 30 次/分钟
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch(since="daily", language="", limit=25, timeout=30):
    """按"最近 N 天创建、star 最多"查询，返回和 scraper.fetch 一样的数据结构"""
    days = WINDOW_DAYS.get(since, 14)
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    query = f"created:>{cutoff}"
    if language:
        query += f" language:{language}"

    resp = requests.get(
        SEARCH_URL,
        params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
        headers=_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    items = []
    for index, repo in enumerate(data.get("items", []), start=1):
        items.append({
            "rank": index,
            "repo": repo["full_name"],
            "description": repo.get("description") or "",
            "lang": repo.get("language") or "",
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            # Search API 不提供"周期内新增 star"，留 0；
            # store 层会拿我们自己的历史快照算出近似增量
            "period_stars": 0,
        })
    return items


if __name__ == "__main__":
    for item in fetch("daily")[:5]:
        print(f"{item['rank']:>2}. {item['repo']:<45} ⭐{item['stars']:,}")
