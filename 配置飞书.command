#!/bin/bash
# 双击这个文件，按提示粘贴飞书 webhook 地址即可完成配置
# 不用手动改配置文件

cd "$(dirname "$0")"

echo "======================================"
echo "  配置飞书推送"
echo "======================================"
echo ""
echo "请在飞书群里创建「自定义机器人」，复制它给你的 webhook 地址。"
echo "地址长这样：https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"
echo ""
read -p "粘贴 webhook 地址后按回车：" WEBHOOK

if [ -z "$WEBHOOK" ]; then
  echo ""
  echo "没有输入地址，已取消。"
  read -p "按回车关闭窗口"
  exit 1
fi

echo ""
echo "如果创建机器人时勾选了「签名校验」，把密钥也粘进来。"
echo "没勾选的话，直接按回车跳过。"
read -p "签名密钥（可留空）：" SECRET

python3 - "$WEBHOOK" "$SECRET" <<'PYEOF'
import re, sys

webhook = sys.argv[1].strip()
secret = sys.argv[2].strip() if len(sys.argv) > 2 else ""

if not webhook.startswith("http"):
    print("\n地址看起来不对，应该以 http 开头。请重新运行本脚本。")
    sys.exit(1)

with open("config.yaml", encoding="utf-8") as f:
    text = f.read()

text = re.sub(r'(\n\s*feishu_webhook:\s*).*', rf'\g<1>"{webhook}"', text, count=1)
text = re.sub(r'(\n\s*feishu_secret:\s*).*', rf'\g<1>"{secret}"', text, count=1)

with open("config.yaml", "w", encoding="utf-8") as f:
    f.write(text)

print("\n配置已写入。")
PYEOF

if [ $? -ne 0 ]; then
  read -p "按回车关闭窗口"
  exit 1
fi

echo ""
echo "正在发送测试消息…"
echo ""

# 库里没数据的话先抓一次，否则没内容可推
python3 - <<'PYEOF'
import os, sys, yaml
cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
if not os.path.exists(cfg["db_path"]):
    print("还没有榜单数据，先抓取一次…")
    sys.exit(3)
PYEOF
if [ $? -eq 3 ]; then
  python3 run.py fetch
fi

python3 run.py push

echo ""
echo "======================================"
echo "如果飞书群里收到了卡片，就配好了。"
echo "以后每天双击「每天点我.command」即可。"
echo "======================================"
echo ""
read -p "按回车关闭窗口"
