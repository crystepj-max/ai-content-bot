"""
AI 写作引擎 — MiniMax 适配版
调用 MiniMax API（OpenAI-compatible），根据文章类型套用不同 prompt 模板
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
import httpx
from rich.console import Console

from src.fetchers.rss_fetcher import FeedItem

console = Console()

MINIMAX_BASE = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M2.7"

SYSTEM_PROMPT = """你是一位专注 AI / 大模型领域的中文科技内容创作者。

写作风格要求：
- 专业、准确，但不晦涩；适合有技术背景但非专家的读者
- 有独立判断和观点，不只是信息转述
- 结构清晰，每段有核心句，逻辑递进
- 中文写作，专有名词保留英文（如 GPT-4、Claude 3.5 Sonnet）
- 不使用"首先""其次""总结"等套话开头
- 标题吸引眼球但不标题党

输出格式：
- 纯 Markdown，包含 YAML frontmatter
- frontmatter 字段：title, slug, summary（100字以内摘要）, tags, date（格式：YYYY-MM-DD，使用今天日期）
- 正文长度 800-1500 字
- 适当使用二级标题（##）划分结构
- 不要在文章末尾写"结语"或"总结"大标题
"""

TEMPLATES: dict[str, str] = {
    "model_release": """
请根据以下信息，写一篇关于 AI 大模型发布 / 更新的深度分析文章。

【信息来源】
标题：{title}
来源：{source}
原文摘要：
{summary}

【原文内容（如有）】
{raw_content}

【文章结构要求】
1. 开篇：一句话点出核心变化或突破（不要用"近日"开头）
2. 核心能力：这次更新最重要的 2-3 个能力变化，对比上一版本
3. 数据解读：如有 benchmark 数据，用通俗语言解释其含义
4. 影响分析：对开发者、企业用户、AI 应用生态意味着什么
5. 作者判断：你的独立判断 — 这个发布真正重要还是营销噱头？为什么？

【注意】
- 如果原文信息不足，可基于已有知识合理补充，但需注明推断
- 不要捏造具体数据
""",

    "github_project": """
请根据以下信息，写一篇 GitHub 开源项目介绍文章，帮助读者快速判断是否值得关注和使用。

【项目信息】
项目名：{title}
来源：{source}
描述：{summary}

【README 摘录】
{raw_content}

【文章结构要求】
1. 一句话说明：这个项目解决什么具体问题
2. 技术原理：核心实现思路（不需要细节，让读者理解"为什么它能做到"）
3. 与现有方案对比：比 LangChain / LlamaIndex / 其他同类工具强在哪，弱在哪
4. 快速上手：最简单的安装和使用示例（如果 README 有，提炼出来）
5. 适合谁：明确指出目标用户 — 个人开发者 / 企业 / 研究人员？什么场景最合适？
6. 作者判断：这个项目值得 star 和持续关注吗？为什么？

【注意】
- 代码示例用 markdown 代码块
- 项目链接放在文章末尾：[GitHub 仓库]({url})
""",

    "kol_insight": """
请根据以下 AI 领域重要人物的观点，写一篇深度解读文章。

【原始内容】
来源账号：{source}
原文内容：
{summary}

【补充内容（如有）】
{raw_content}

【文章结构要求】
1. 核心论点：用 1-2 句话提炼出对方的核心主张
2. 背景补充：为什么这个观点在当下值得关注？背景是什么？
3. 深度分析：
   - 这个观点的支撑论据是什么？
   - 哪些地方值得认同？
   - 哪些地方存在争议或局限？
4. 延伸思考：这个观点对 AI 发展方向、开发者实践有什么启示？
5. 作者立场：你同意还是不同意？为什么？

【注意】
- 要有独立判断，不能只是复述
- 如果观点来自 X/Twitter，注意推文可能有上下文缺失，要说明
- 原始内容链接放文章末尾：[原文链接]({url})
""",
}


class Writer:
    def __init__(self, config_path: str = "config.yaml", api_key: str = None):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("需要设置 MINIMAX_API_KEY 或 ANTHROPIC_API_KEY 环境变量")
        
        self.model = DEFAULT_MODEL
        self.output_dir = Path("output/articles")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _call_llm(self, user_prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        """调用 MiniMax OpenAI-compatible API"""
        client = httpx.Client(timeout=60)
        try:
            resp = client.post(
                f"{MINIMAX_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 4096,
                    "temperature": 0.7
                }
            )
            if resp.status_code != 200:
                raise RuntimeError(f"MiniMax API 错误 {resp.status_code}: {resp.text[:200]}")
            
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        finally:
            client.close()

    def write(self, item: FeedItem) -> Path:
        template = TEMPLATES.get(item.article_type, TEMPLATES["model_release"])
        user_prompt = template.format(
            title=item.title,
            source=item.source,
            summary=item.summary,
            raw_content=item.raw_content[:3000] if item.raw_content else "（无额外原文）",
            url=item.url,
        )

        from datetime import date
        today = date.today().isoformat()
        system_with_date = SYSTEM_PROMPT + f"\n\n[重要] 今天是 {today}，所有日期字段必须使用此日期，不要写任何更早或更晚的日期。"

        console.print(f"[cyan]正在写作: {item.title[:50]}...[/cyan]")

        content = self._call_llm(user_prompt, system_prompt=system_with_date)

        # 保存文章
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in item.id[:16])
        out_path = self.output_dir / f"{safe_name}.md"
        out_path.write_text(content, encoding="utf-8")

        # 同时保存元数据
        meta_path = self.output_dir / f"{safe_name}.meta.json"
        import json
        meta_path.write_text(json.dumps(item.to_dict(), ensure_ascii=False, indent=2))

        console.print(f"[green]文章已生成: {out_path}[/green]")
        return out_path

    def write_batch(self, items: list[FeedItem]) -> list[Path]:
        paths = []
        for item in items:
            try:
                p = self.write(item)
                paths.append(p)
            except Exception as e:
                console.print(f"[red]写作失败 {item.title[:40]}: {e}[/red]")
        return paths
