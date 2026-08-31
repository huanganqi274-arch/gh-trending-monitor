"""
飞书群机器人推送。

用的是飞书"自定义机器人"的 webhook，不需要开发者后台、不需要应用审批，
群设置里加一个机器人拿到地址就能用。
"""

import base64
import hashlib
import hmac
import time
import requests


def _sign(secret, timestamp):
    """飞书自定义机器人开启'签名校验'时需要的签名"""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _fmt_row(item, index):
    """把一条榜单数据格式化成飞书卡片里的一行"""
    tags = []
    if item["is_new"]:
        tags.append("🆕 新上榜")
    elif item["days_on"] > 1:
        tags.append(f"在榜 {item['days_on']} 天")
    if item["matched"]:
        tags.append("⭐ 关注")

    if item.get("gain_is_approx"):
        tags.append("备用数据源")

    change = ""
    if item["star_change"] is not None:
        if item["star_change"] > 0:
            change = f"（比上次多 +{item['star_change']}）"
        elif item["star_change"] < 0:
            change = f"（比上次少 {item['star_change']}）"

    desc = item["description"] or "（无描述）"
    if len(desc) > 90:
        desc = desc[:90] + "…"

    tag_line = " · ".join(tags)
    lines = [
        f"**{index}. [{item['repo']}]({item['url']})**",
        f"{desc}",
        f"{'约新增' if item.get('gain_is_approx') else '新增'} "
        f"**+{item['period_stars']}** star{change}　总计 {item['stars']:,}"
        + (f"　{item['lang']}" if item["lang"] else ""),
    ]
    if tag_line:
        lines.append(tag_line)
    return "\n".join(lines)


def build_card(board, since="daily", language="", top_n=10, dashboard_url=""):
    """拼一张飞书交互卡片"""
    period_name = {"daily": "今日", "weekly": "本周", "monthly": "本月"}.get(since, since)
    scope = language or "全部语言"

    shown = board[:top_n]
    new_count = sum(1 for i in board if i["is_new"])
    watch_count = sum(1 for i in board if i["matched"])

    elements = [{
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"共 {len(board)} 个项目在榜　新上榜 **{new_count}** 个　"
                       f"命中关注词 **{watch_count}** 个",
        },
    }, {"tag": "hr"}]

    for index, item in enumerate(shown, start=1):
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": _fmt_row(item, index)},
        })
        if index < len(shown):
            elements.append({"tag": "hr"})

    if dashboard_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看完整面板"},
                "url": dashboard_url,
                "type": "primary",
            }],
        })

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"GitHub Trending · {period_name} · {scope}",
                },
                "template": "blue",
            },
            "elements": elements,
        },
    }


def build_alert(failures, used_fallback=False):
    """
    爬虫失效时发的告警卡片。
    failures: [(榜单名, 错误信息), ...]
    """
    lines = []
    for name, error in failures:
        text = str(error)
        if len(text) > 160:
            text = text[:160] + "…"
        lines.append(f"**{name}**\n{text}")

    tail = (
        "已自动切到官方 Search API 取数，面板还有内容，但排序依据变了"
        "（按总 star，不是热度增速）。"
        if used_fallback else
        "备用数据源也没取到，这一期没有数据。"
    )

    elements = [{
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": "抓取 github.com/trending 失败。"
                       "最常见的原因是 GitHub 改了页面结构，"
                       "需要更新 `scraper.py` 里的 CSS 选择器。",
        },
    }, {"tag": "hr"}]

    for line in lines:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": line}})

    elements.append({"tag": "hr"})
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": tail}})

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "GitHub Trending 监控异常"},
                "template": "red",
            },
            "elements": elements,
        },
    }


def send(webhook, payload, secret=""):
    """发送到飞书。返回 (是否成功, 提示信息)"""
    if not webhook:
        return False, "未配置 webhook，跳过推送"

    if secret:
        timestamp = str(int(time.time()))
        payload = dict(payload)
        payload["timestamp"] = timestamp
        payload["sign"] = _sign(secret, timestamp)

    resp = requests.post(webhook, json=payload, timeout=20)
    try:
        data = resp.json()
    except Exception:
        return False, f"飞书返回了非 JSON 内容：{resp.text[:200]}"

    if data.get("code") in (0, None) and data.get("StatusCode", 0) == 0:
        return True, "推送成功"
    if data.get("code") == 0:
        return True, "推送成功"
    return False, f"推送失败：{data}"
