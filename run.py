"""
入口脚本。

用法：
    python run.py fetch       只抓取并入库
    python run.py push        把最新一期榜单推到飞书
    python run.py dashboard   重新生成 HTML 面板
    python run.py all         抓取 + 生成面板 + 推送（定时任务用这个）
"""

import os
import sys
import yaml

import dashboard
import fallback
import notify
import scraper
import store

PERIOD_NAME = {"daily": "日榜", "weekly": "周榜", "monthly": "月榜"}


def load_config(path="config.yaml"):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 环境变量优先，方便在 GitHub Actions 里用 Secrets 传敏感信息
    cfg.setdefault("notify", {})
    if os.getenv("FEISHU_WEBHOOK"):
        cfg["notify"]["feishu_webhook"] = os.getenv("FEISHU_WEBHOOK")
    if os.getenv("FEISHU_SECRET"):
        cfg["notify"]["feishu_secret"] = os.getenv("FEISHU_SECRET")
    if os.getenv("DASHBOARD_URL"):
        cfg["dashboard_url"] = os.getenv("DASHBOARD_URL")
    return cfg


def board_key(since, language):
    return f"{since}-{language or 'all'}"


def board_label(since, language):
    return f"{PERIOD_NAME.get(since, since)} · {language or '全部语言'}"


def cmd_fetch(cfg):
    """
    抓取。爬虫失效时自动降级到官方 Search API，并记录失败信息用于告警。
    返回 (失败列表, 是否用了备用源)
    """
    conn = store.connect(cfg["db_path"])
    use_fallback = cfg.get("fallback", {}).get("enabled", True)
    failures = []
    used_fallback = False

    for target in cfg["targets"]:
        since = target["since"]
        language = target.get("language", "") or ""
        label = board_label(since, language)

        try:
            items = scraper.fetch(since=since, language=language)
            count = store.save(conn, items, since, language, source="trending")
            print(f"  ✓ {label}：入库 {count} 条")
            continue
        except Exception as exc:
            print(f"  ✗ {label}：{exc}")
            failures.append((label, exc))

        if not use_fallback:
            continue

        # 降级：官方 Search API
        try:
            items = fallback.fetch(since=since, language=language)
            if not items:
                raise RuntimeError("Search API 返回空结果")
            count = store.save(conn, items, since, language, source="search")
            used_fallback = True
            print(f"    ↳ 已降级到 Search API，入库 {count} 条")
        except Exception as exc:
            print(f"    ↳ 备用数据源也失败：{exc}")

    store.prune(conn)
    conn.close()
    return failures, used_fallback


def alert(cfg, failures, used_fallback):
    """把抓取失败的情况推到飞书"""
    conf = cfg.get("notify", {})
    webhook = conf.get("feishu_webhook", "")
    if not webhook or not failures:
        return
    payload = notify.build_alert(failures, used_fallback=used_fallback)
    ok, message = notify.send(webhook, payload, secret=conf.get("feishu_secret", ""))
    print(f"  {'✓' if ok else '✗'} 告警：{message}")


def cmd_dashboard(cfg):
    conn = store.connect(cfg["db_path"])
    keywords = cfg.get("keywords", [])
    boards = {}
    for target in cfg["targets"]:
        since = target["since"]
        language = target.get("language", "") or ""
        on_date = store.latest_date(conn, since, language)
        items = store.get_board(conn, since, language, keywords=keywords)
        boards[board_key(since, language)] = {
            "label": board_label(since, language),
            "date": on_date or "暂无数据",
            "items": items,
        }
    conn.close()

    path = dashboard.render(boards, cfg["dashboard_path"])
    print(f"  ✓ 面板已生成：{os.path.abspath(path)}")


def cmd_push(cfg):
    conf = cfg.get("notify", {})
    webhook = conf.get("feishu_webhook", "")
    if not webhook:
        print("  · 没有配置飞书 webhook，跳过推送")
        return

    since = conf.get("since", "daily")
    language = conf.get("language", "") or ""

    conn = store.connect(cfg["db_path"])
    board = store.get_board(conn, since, language, keywords=cfg.get("keywords", []))
    conn.close()

    if not board:
        print("  · 库里还没有数据，先跑 fetch")
        return

    if conf.get("only_new"):
        board = [i for i in board if i["is_new"]]
        if not board:
            print("  · 今天没有新上榜的项目，不打扰了")
            return

    payload = notify.build_card(
        board, since=since, language=language,
        top_n=conf.get("top_n", 10),
        dashboard_url=cfg.get("dashboard_url", ""),
    )
    ok, message = notify.send(webhook, payload, secret=conf.get("feishu_secret", ""))
    print(f"  {'✓' if ok else '✗'} {message}")


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "all"
    cfg = load_config()

    failures, used_fallback = [], False
    if command in ("fetch", "all"):
        print("抓取榜单…")
        failures, used_fallback = cmd_fetch(cfg)
    if command in ("dashboard", "all"):
        print("生成面板…")
        cmd_dashboard(cfg)
    if command in ("push", "all"):
        print("推送飞书…")
        cmd_push(cfg)
        if failures:
            alert(cfg, failures, used_fallback)
    if command not in ("fetch", "push", "dashboard", "all"):
        print(__doc__)


if __name__ == "__main__":
    main()
