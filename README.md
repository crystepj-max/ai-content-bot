# AI 内容机器人

专注 AI 大模型 + AI 工程领域的中文内容自动化系统。
每天自动采集 → 评分选题 → Claude 写作 → baoyu-skills 配图发布。

## 架构

```
数据采集层
  ├── RSS Monitor      官方博客（Anthropic/OpenAI/Google/Meta/Mistral…）
  ├── GitHub Fetcher   AI 项目涨星监控
  └── X Fetcher        KOL 高互动推文

评分层
  └── Scorer           新鲜度 × 互动量 × 话题热度 → 每日 Top 3

写作层
  └── MiniMax API     OpenAI-compatible，3种模板：大模型评测/GitHub项目/KOL解读

发布层（Claude Code + baoyu-skills）
  ├── baoyu-format-markdown     格式规范化
  ├── baoyu-cover-image         封面图生成
  ├── baoyu-article-illustrator 文章内配图
  └── baoyu-post-to-wechat      发布到公众号
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
npx skills add jimliu/baoyu-skills

# 加载环境变量（必须）
set -a && source .env && set +a
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入以下 key（MINIMAX_API_KEY 必须）：
#   ANTHROPIC_API_KEY      Claude API key（必须）
#   GITHUB_TOKEN           GitHub Personal Token（可选，提高频率限制）
#   TWITTER_BEARER_TOKEN   Twitter API Bearer Token（可选）
#   WECHAT_APP_ID          微信公众号 AppID（发布用）
#   WECHAT_APP_SECRET      微信公众号 AppSecret
```

微信公众号配置参考 [baoyu-skills 文档](https://github.com/JimLiu/baoyu-skills#baoyu-post-to-wechat)。

### 3. 本地运行

```bash
# 完整流程（采集 + 评分 + 写作）
python main.py

# 只采集查看今日选题
python main.py --fetch-only

# 只写作（用上次采集结果）
python main.py --write-only

# 查看选题但不调用 API
python main.py --dry-run
```

### 4. 配图 + 发布（Claude Code 环境）

文章生成在 `output/articles/` 后，打开 Claude Code 说：

> 请读取 output/articles/ 下所有 .md 文件，
> 依次用 baoyu-format-markdown 格式化，
> 用 baoyu-cover-image 生成封面（--type conceptual --palette cool --quick），
> 用 baoyu-article-illustrator 配图（--style blueprint），
> 最后用 baoyu-post-to-wechat 发布到公众号。

### 5. 部署自动化（GitHub Actions）

在仓库 Settings → Secrets 添加：

| Secret                | 说明                    |
|-----------------------|-------------------------|
| `ANTHROPIC_API_KEY`   | Claude API key          |
| `GITHUB_TOKEN`        | 自动注入，无需手动添加  |
| `TWITTER_BEARER_TOKEN`| X API Token（可选）     |
| `WECHAT_APP_ID`       | 公众号 AppID            |
| `WECHAT_APP_SECRET`   | 公众号 AppSecret        |

每天北京时间 06:00 自动运行，文章会自动发布到公众号。

## 自定义配置

编辑 `config.yaml`：

- `topics.keywords` — 添加关注的关键词
- `sources.rss_feeds` — 添加/删除监控的博客
- `sources.x_accounts` — 添加关注的 KOL
- `scoring.max_articles_per_day` — 每日最多发几篇
- `writing.templates` — 调整文章结构

## 成本估算

| 项目              | 费用              |
|-------------------|-------------------|
| Claude API        | ~¥50-150/月       |
| GitHub Actions    | 免费（2000分钟）  |
| 服务器            | ¥0                |
| baoyu-skills      | 免费开源          |

## 与 baoyu-skills 的关系

本项目负责"内容的发现和生产"，baoyu-skills 负责"内容的美化和分发"。

- `baoyu-url-to-markdown` — 抓取原文完整内容供深度写作
- `baoyu-danger-x-to-markdown` — 获取推文完整线程
- `baoyu-format-markdown` — 文章格式规范化
- `baoyu-cover-image` — 封面图（editorial + cool 风格适合 AI 内容）
- `baoyu-article-illustrator` — 文章内配图（blueprint 风格）
- `baoyu-post-to-wechat` — 发布到公众号

## License

MIT
