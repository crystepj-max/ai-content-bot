"""
RSS 采集器
监控各大 AI 公司官方博客，抓取最新文章
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import feedparser
import httpx
import yaml
from dateutil import parser as dateparser
from rich.console import Console

console = Console()


@dataclass
class FeedItem:
    id: str
    title: str
    url: str
    source: str
    summary: str
    published_at: datetime
    raw_content: str = ""
    score: float = 0.0
    article_type: str = "model_release"  # model_release | kol_insight | github_project

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "summary": self.summary,
            "published_at": self.published_at.isoformat(),
            "raw_content": self.raw_content,
            "score": self.score,
            "article_type": self.article_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FeedItem":
        d["published_at"] = dateparser.parse(d["published_at"])
        return cls(**d)


class RSSFetcher:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.keywords: list[str] = [
            kw.lower() for kw in self.config["topics"]["keywords"]
        ]
        self.feeds: list[dict] = self.config["sources"]["rss_feeds"]
        self.cache_path = Path(".cache/rss_seen.json")
        self.cache_path.parent.mkdir(exist_ok=True)
        self._seen: set[str] = self._load_seen()

    def _load_seen(self) -> set[str]:
        if self.cache_path.exists():
            return set(json.loads(self.cache_path.read_text()))
        return set()

    def _save_seen(self) -> None:
        self.cache_path.write_text(json.dumps(list(self._seen)))

    def _make_id(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _is_relevant(self, title: str, summary: str) -> bool:
        text = (title + " " + summary).lower()
        return any(kw in text for kw in self.keywords)

    def _parse_date(self, entry) -> datetime:
        for attr in ("published_parsed", "updated_parsed"):
            t = getattr(entry, attr, None)
            if t:
                import time
                return datetime(*t[:6], tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

    def fetch_all(self, max_age_days: int = 3) -> list[FeedItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        results: list[FeedItem] = []

        for feed_cfg in self.feeds:
            try:
                console.print(f"[dim]抓取 RSS: {feed_cfg['name']}[/dim]")
                feed = feedparser.parse(feed_cfg["url"])

                for entry in feed.entries:
                    pub = self._parse_date(entry)
                    if pub < cutoff:
                        continue

                    title = entry.get("title", "")
                    summary = entry.get("summary", "")[:500]
                    url = entry.get("link", "")

                    if not url or not self._is_relevant(title, summary):
                        continue

                    item_id = self._make_id(url)
                    if item_id in self._seen:
                        continue

                    item = FeedItem(
                        id=item_id,
                        title=title,
                        url=url,
                        source=feed_cfg["name"],
                        summary=summary,
                        published_at=pub,
                        score=feed_cfg.get("weight", 5) / 10.0,
                        article_type="model_release",
                    )
                    results.append(item)
                    self._seen.add(item_id)

            except Exception as e:
                console.print(f"[red]RSS 抓取失败 {feed_cfg['name']}: {e}[/red]")

        self._save_seen()
        console.print(f"[green]RSS 采集完成，新增 {len(results)} 条[/green]")
        return results
