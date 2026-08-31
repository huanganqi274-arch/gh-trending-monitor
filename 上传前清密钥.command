#!/bin/bash
# 上传 GitHub 之前跑一次，清掉配置文件里的飞书地址
# 公开仓库谁都能看，webhook 地址泄露后别人可以往你们群里发垃圾消息

cd "$(dirname "$0")"

echo "======================================"
echo "  上传 GitHub 前的安全检查"
echo "======================================"
echo ""

python3 - <<'PYEOF'
import re

with open("config.yaml", encoding="utf-8") as f:
    text = f.read()

found = re.search(r'\n\s*feishu_webhook:\s*"?([^"\n]*)"?', text)
current = (found.group(1).strip() if found else "")

if not current:
    print("配置文件里没有飞书地址，本来就是干净的，可以直接上传。")
else:
    print(f"发现飞书地址：{current[:45]}…")
    text = re.sub(r'(\n\s*feishu_webhook:\s*).*', r'\g<1>""', text, count=1)
    text = re.sub(r'(\n\s*feishu_secret:\s*).*', r'\g<1>""', text, count=1)
    with open("config.yaml", "w", encoding="utf-8") as f:
        f.write(text)
    print("已清除。现在可以安全上传了。")
    print("")
    print("记得把这个地址填到 GitHub 仓库的 Secrets 里：")
    print("  Settings → Secrets and variables → Actions → New repository secret")
    print("  名称填 FEISHU_WEBHOOK，值填上面那个完整地址")
    print("")
    print("完整地址（复制这行）：")
    print(current)
PYEOF

echo ""
echo "======================================"
echo "注意：清除后本地双击「每天点我」就不再推飞书了。"
echo "推送改由 GitHub 每天自动完成。"
echo "======================================"
echo ""
read -p "按回车关闭窗口"
