"""
抓取 github.com/trending 页面并解析成结构化数据。

GitHub 没有官方的 Trending API，这里直接解析网页 HTML。
页面结构多年稳定，但万一哪天 GitHub 改版，需要调整的就是本文件里的 CSS 选择器。
"""

import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://github.com/trending"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _to_int(text):
    """把 '24,367' 这种带逗号的字符串转成整数，失败返回 0"""
    if not text:
        return 0
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def fetch_html(since="daily", language="", retries=3, timeout=30):
    """请求 trending 页面，返回 HTML 文本"""
    params = {"since": since}
    url = BASE_URL
    if language:
        # 语言是路径的一部分，不是 query 参数
        url = f"{BASE_URL}/{language}"

    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:  # 网络抖动就重试
            last_error = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"抓取失败 {url} ({since}): {last_error}")


def parse(html, since="daily"):
    """把 HTML 解析成 [{repo, description, lang, stars, forks, period_stars, rank}, ...]"""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("article.Box-row")
    results = []

    for index, row in enumerate(rows, start=1):
        title_link = row.select_one("h2 a")
        if not title_link:
            continue
        repo = title_link.get("href", "").strip("/")
        if not repo:
            continue

        desc_el = row.select_one("p")
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

        lang_el = row.select_one('[itemprop="programmingLanguage"]')
        lang = lang_el.get_text(strip=True) if lang_el else ""

        # 总 star 数和 fork 数：两个指向 /stargazers 和 /forks 的链接
        stars = forks = 0
        for link in row.select("a.Link--muted"):
            href = link.get("href", "")
            value = _to_int(link.get_text(strip=True))
            if href.endswith("/stargazers"):
                stars = value
            elif href.endswith("/forks"):
                forks = value

        # 本周期新增 star：右下角的 "1,370 stars today"
        period_el = row.select_one("span.float-sm-right")
        period_stars = _to_int(period_el.get_text(strip=True)) if period_el else 0

        results.append({
            "rank": index,
            "repo": repo,
            "description": description,
            "lang": lang,
            "stars": stars,
            "forks": forks,
            "period_stars": period_stars,
        })

    return results


def fetch(since="daily", language=""):
    """抓取 + 解析，一步到位"""
    html = fetch_html(since=since, language=language)
    items = parse(html, since=since)
    if not items:
        raise RuntimeError(
            f"解析出 0 条数据（{since}/{language or 'all'}）。"
            "可能是 GitHub 改版了页面结构，需要检查 scraper.py 里的选择器。"
        )
    return items


if __name__ == "__main__":
    # 单独跑这个文件可以快速验证抓取是否正常
    for item in fetch("daily")[:5]:
        print(f"{item['rank']:>2}. {item['repo']:<45} "
              f"+{item['period_stars']:<6} ⭐{item['stars']}")
