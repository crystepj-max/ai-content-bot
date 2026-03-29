"""
选题评分器
三维加权：新鲜度 + 互动量（已在 score 字段体现）+ 话题热度
输出每日 Top N 选题
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

import yaml
from rich.console import Console
from rich.table import Table

from src.fetchers.rss_fetcher import FeedItem

console = Console()

# 话题热度词（出现在标题中额外加分）
HOT_TOPICS = {
    "claude": 0.15,
    "gpt-5": 0.2,
    "gemini": 0.12,
    "llama": 0.10,
    "deepseek": 0.15,
    "o3": 0.12,
    "agent": 0.10,
    "mcp": 0.12,
    "openai": 0.08,
    "anthropic": 0.10,
    "reasoning": 0.08,
    "multimodal": 0.08,
    "benchmark": 0.06,
}


class Scorer:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        sc = self.config["scoring"]
        self.w_freshness = sc["freshness_weight"]
        self.w_engagement = sc["engagement_weight"]
        self.w_relevance = sc["relevance_weight"]
        self.min_score = sc["min_score"]
        self.max_per_day = sc["max_articles_per_day"]

    def _freshness(self, item: FeedItem) -> float:
        """越新分越高，72小时内线性衰减到0"""
        now = datetime.now(timezone.utc)
        pub = item.published_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        age_hours = (now - pub).total_seconds() / 3600
        return max(0.0, 1.0 - age_hours / 72)

    def _relevance_bonus(self, item: FeedItem) -> float:
        """根据标题/摘要命中热点词给额外加分"""
        text = (item.title + " " + item.summary).lower()
        bonus = 0.0
        for word, weight in HOT_TOPICS.items():
            if word in text:
                bonus += weight
        return min(bonus, 0.4)  # 最多加 0.4

    def score(self, item: FeedItem) -> float:
        freshness = self._freshness(item)
        engagement = item.score          # 各采集器已归一化到 0-1
        relevance = self._relevance_bonus(item)

        final = (
            self.w_freshness * freshness
            + self.w_engagement * engagement
            + self.w_relevance * relevance
        )
        return round(final, 4)

    def rank(self, items: Sequence[FeedItem], dedupe: bool = True) -> list[FeedItem]:
        """评分 + 排序 + 去重（同类型不重复选相似内容）"""
        scored = []
        for item in items:
            item.score = self.score(item)
            if item.score >= self.min_score:
                scored.append(item)

        scored.sort(key=lambda x: x.score, reverse=True)

        if dedupe:
            # 同一来源最多保留 2 条，防止某个 RSS 刷屏
            source_count: dict[str, int] = {}
            filtered = []
            for item in scored:
                src = item.source
                if source_count.get(src, 0) < 2:
                    filtered.append(item)
                    source_count[src] = source_count.get(src, 0) + 1
            scored = filtered

        top = scored[: self.max_per_day]
        self._print_table(top)
        return top

    def _print_table(self, items: list[FeedItem]) -> None:
        table = Table(title=f"今日 Top {len(items)} 选题", show_lines=True)
        table.add_column("评分", style="cyan", width=6)
        table.add_column("类型", style="magenta", width=14)
        table.add_column("标题", style="white")
        table.add_column("来源", style="dim", width=20)

        for item in items:
            table.add_row(
                f"{item.score:.2f}",
                item.article_type,
                item.title[:60],
                item.source,
            )
        console.print(table)
