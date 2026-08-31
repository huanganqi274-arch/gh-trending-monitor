#!/bin/bash
# 双击这个文件就会：抓取最新榜单 → 生成面板 → 推送飞书 → 打开面板
# 不用打开终端，也不用记命令

cd "$(dirname "$0")"

echo "======================================"
echo "  GitHub Trending 监控"
echo "======================================"
echo ""

python3 run.py all

echo ""
echo "正在打开面板…"
open docs/index.html

echo ""
echo "完成。这个窗口可以直接关掉。"
