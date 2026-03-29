"""
main.py — 主流程入口

运行方式：
  python main.py              # 完整流程：采集 → 评分 → 写作
  python main.py --fetch-only # 只采集，不写作
  python main.py --write-only # 只写作（使用上次采集结果）
"""

from __future__ import annotations

import os as _os
from pathlib import Path as _Path

# 自动加载 .env 文件
_env = _Path(__file__).parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#") and not line.startswith(" "):
            k, v = line.split("=", 1)
            if v and not _os.environ.get(k.strip()):
                _os.environ[k.strip()] = v.strip()

import json
import sys
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(add_completion=False)
console = Console()

QUEUE_FILE = Path(".cache/today_queue.json")


def load_queue():
    from src.fetchers.rss_fetcher import FeedItem
    if QUEUE_FILE.exists():
        data = json.loads(QUEUE_FILE.read_text())
        return [FeedItem.from_dict(d) for d in data]
    return []


def save_queue(items):
    QUEUE_FILE.parent.mkdir(exist_ok=True)
    QUEUE_FILE.write_text(
        json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2)
    )


@app.command()
def run(
    fetch_only: bool = typer.Option(False, "--fetch-only", help="只采集，不写作"),
    write_only: bool = typer.Option(False, "--write-only", help="只写作（用缓存选题）"),
    dry_run: bool = typer.Option(False, "--dry-run", help="打印选题但不调用 API"),
    skip_x: bool = typer.Option(False, "--skip-x", help="跳过 X/Twitter 采集（Nitter 被墙时使用）"),
):
    """AI 内容机器人 — 每日自动采集 + 写作"""

    console.rule("[bold cyan]AI 内容机器人启动[/bold cyan]")

    # ── 1. 采集 ──────────────────────────────────────────────
    if not write_only:
        console.print("\n[bold]▶ 阶段 1/3：数据采集[/bold]")

        from src.fetchers.rss_fetcher import RSSFetcher
        from src.fetchers.github_fetcher import GitHubFetcher
        from src.fetchers.x_fetcher import XFetcher

        all_items = []
        all_items.extend(RSSFetcher().fetch_all(max_age_days=2))
        all_items.extend(GitHubFetcher().fetch_trending())
        if not skip_x:
            all_items.extend(XFetcher().fetch_all())
        else:
            console.print("[yellow]跳过 X 采集（--skip-x）[/yellow]")

        console.print(f"\n[cyan]采集总计 {len(all_items)} 条原始信号[/cyan]")

        # ── 2. 评分 ────────────────────────────────────────────
        console.print("\n[bold]▶ 阶段 2/3：评分与选题[/bold]")
        from src.scorer.scorer import Scorer
        top_items = Scorer().rank(all_items)
        save_queue(top_items)

        if fetch_only or dry_run:
            console.print("\n[yellow]--fetch-only / --dry-run 模式，跳过写作[/yellow]")
            return

    else:
        console.print("\n[yellow]--write-only 模式，从缓存加载选题[/yellow]")
        top_items = load_queue()
        if not top_items:
            console.print("[red]缓存为空，请先运行采集[/red]")
            sys.exit(1)

    # ── 3. 写作 ────────────────────────────────────────────
    console.print(f"\n[bold]▶ 阶段 3/3：AI 写作（共 {len(top_items)} 篇）[/bold]")
    from src.writer.claude_writer import Writer
    writer = Writer()
    paths = writer.write_batch(top_items)

    console.print(f"\n[bold green]✅ 完成！生成了 {len(paths)} 篇文章：[/bold green]")
    for p in paths:
        console.print(f"  [dim]{p}[/dim]")

    console.print(
        "\n[bold]下一步：[/bold] 在 Claude Code 中运行 [cyan]node scripts/publish.mjs[/cyan] "
        "或直接告诉 Claude Code：\n"
        "[dim]\"请读取 output/articles/ 下所有 .md 文件，用 baoyu-skills 配图并发布到公众号\"[/dim]"
    )


if __name__ == "__main__":
    app()
