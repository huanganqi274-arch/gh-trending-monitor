# GitHub Trending 监控

每天抓一次 GitHub Trending 榜单，存历史快照，生成一个网页面板，并把结果推到飞书群。

比直接看 github.com/trending 多出来的东西：

- **历史快照** —— 官方页面只有此刻，这里能看到一个项目在榜几天了、热度是在涨还是在退
- **新上榜识别** —— 今天第一次冒出来的项目单独标出来，这才是真正的"新东西"
- **关注方向过滤** —— 按关键词（agent / mcp / rag 等）高亮，从噪音里捞出跟业务相关的
- **主动推送** —— 不用记得去看，每天早上飞书里自己出现

## 快速开始

```bash
pip install -r requirements.txt
python run.py fetch        # 抓一次
python run.py dashboard    # 生成面板
open docs/index.html       # 看结果（Windows 直接双击这个文件）
```

## 命令

| 命令 | 作用 |
|---|---|
| `python run.py fetch` | 抓取榜单并入库 |
| `python run.py dashboard` | 用库里的数据重新生成 HTML 面板 |
| `python run.py push` | 把最新一期榜单推到飞书 |
| `python run.py all` | 以上三步一起做（定时任务用这个） |

## 配置

改 `config.yaml`：

- `targets` —— 抓哪些榜单。可以加语言，比如 `language: rust`
- `keywords` —— 关注方向。命中的项目会在面板上标蓝、在飞书里带 ⭐
- `notify.top_n` —— 飞书里推前几条
- `notify.only_new` —— 设成 `true` 就只在有新项目时才推送

## 接飞书

1. 在目标飞书群里点 **设置 → 群机器人 → 添加机器人 → 自定义机器人**
2. 复制拿到的 webhook 地址
3. 填进 `config.yaml` 的 `notify.feishu_webhook`，或者设环境变量 `FEISHU_WEBHOOK`
4. 如果建机器人时勾了"签名校验"，把密钥也填到 `feishu_secret` / `FEISHU_SECRET`

## 每天自动跑

仓库里已经带了 `.github/workflows/daily.yml`，推到 GitHub 后：

1. 仓库 **Settings → Secrets and variables → Actions** 里加 `FEISHU_WEBHOOK`
2. **Settings → Pages** 里把来源设成 `main` 分支的 `/docs` 目录，面板就有公网地址了
3. 把那个地址存成变量 `DASHBOARD_URL`，飞书卡片上就会出现"查看完整面板"按钮

之后每天北京时间 9 点自动跑，数据和面板会自动提交回仓库。

## 备用数据源

GitHub 没有官方 Trending API，主数据源是解析 `github.com/trending` 的网页 HTML。
如果哪天 GitHub 改版导致抓不到，程序会自动做两件事：

1. **降级到官方 Search API** —— 查"最近创建 + star 最多"的仓库，面板不会开天窗
2. **往飞书发一条红色告警卡片** —— 告诉你抓取失败了，需要去修 `scraper.py` 的选择器

要注意的是，Search API 给的**不是 Trending 榜**。Trending 的排序算法是黑箱，
掺了 star 增速、fork、贡献者等因素；备用源只能做到按总 star 排序，是个近似。
所以降级期间面板顶部会有黄色横幅提示，飞书卡片里也会标"备用数据源"，
新增 star 前面带 `≈`（那是用我们自己的历史快照估算的，不是真实周期增量）。

想关掉降级，把 `config.yaml` 里的 `fallback.enabled` 设成 `false`。

Search API 匿名调用限 10 次/分钟。设一个 `GITHUB_TOKEN` 环境变量
（GitHub 的 Personal Access Token，不需要任何权限勾选）可以提到 30 次/分钟。

## 维护提醒

运行 `python scraper.py` 可以单独验证主数据源是否正常——
它会直接打印前 5 个项目，比跑完整流程更快定位问题。
`python fallback.py` 同理，单独验证备用源。
