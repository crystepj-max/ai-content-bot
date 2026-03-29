"""
X (Twitter) KOL 采集器
抓取 AI 领域头部人物高互动推文
复用 baoyu-skills 的 baoyu-danger-x-to-markdown 能力做深度抓取
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import yaml
from rich.console import Console

from .rss_fetcher import FeedItem

console = Console()

# Twitter API v2 端点
TWITTER_API = "https://api.twitter.com/2"


class XFetcher:
    """
    两种模式：
    1. 有 Bearer Token → 走官方 API（稳定，有频率限制）
    2. 没有 Token → 抓 nitter 实例（免费，但不稳定）

    抓到 URL 后，正式写作时由 Claude Code 调用
    baoyu-danger-x-to-markdown 获取完整内容
    """

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.accounts: list[dict] = self.config["sources"]["x_accounts"]
        self.keywords: list[str] = [
            kw.lower() for kw in self.config["topics"]["keywords"]
        ]
        self.bearer_token: str = os.environ.get("TWITTER_BEARER_TOKEN", "")
        self.cache_path = Path(".cache/x_seen.json")
        self.cache_path.parent.mkdir(exist_ok=True)
        self._seen: set[str] = self._load_seen()

    def _load_seen(self) -> set[str]:
        if self.cache_path.exists():
            return set(json.loads(self.cache_path.read_text()))
        return set()

    def _save_seen(self) -> None:
        self.cache_path.write_text(json.dumps(list(self._seen)))

    def _is_relevant(self, text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in self.keywords)

    def _fetch_via_api(self, handle: str, weight: int, client: httpx.Client) -> list[FeedItem]:
        """使用官方 Twitter API v2"""
        results = []
        try:
            # 先获取 user_id
            r = client.get(
                f"{TWITTER_API}/users/by/username/{handle}",
                headers={"Authorization": f"Bearer {self.bearer_token}"},
                params={"user.fields": "id,name"},
                timeout=10,
            )
            if r.status_code != 200:
                return []
            user_id = r.json()["data"]["id"]

            # 获取最近推文
            since = (datetime.now(timezone.utc) - timedelta(days=3)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            r2 = client.get(
                f"{TWITTER_API}/users/{user_id}/tweets",
                headers={"Authorization": f"Bearer {self.bearer_token}"},
                params={
                    "max_results": 10,
                    "start_time": since,
                    "tweet.fields": "public_metrics,created_at,text",
                    "exclude": "retweets,replies",
                },
                timeout=10,
            )
            if r2.status_code != 200:
                return []

            for tweet in r2.json().get("data", []):
                text = tweet.get("text", "")
                if not self._is_relevant(text):
                    continue

                metrics = tweet.get("public_metrics", {})
                likes = metrics.get("like_count", 0)
                retweets = metrics.get("retweet_count", 0)

                # 过滤低互动（KOL 低于 200 likes 的不抓）
                if likes + retweets * 3 < 200:
                    continue

                tweet_id = tweet["id"]
                item_id = hashlib.md5(tweet_id.encode()).hexdigest()
                if item_id in self._seen:
                    continue

                url = f"https://x.com/{handle}/status/{tweet_id}"
                engagement = min((likes + retweets * 3) / 5000, 1.0)

                item = FeedItem(
                    id=item_id,
                    title=f"@{handle}: {text[:80]}...",
                    url=url,
                    source=f"X/@{handle}",
                    summary=text[:300],
                    published_at=datetime.fromisoformat(
                        tweet["created_at"].replace("Z", "+00:00")
                    ),
                    score=weight / 10 * 0.5 + engagement * 0.5,
                    article_type="kol_insight",
                )
                results.append(item)
                self._seen.add(item_id)

        except Exception as e:
            console.print(f"[yellow]X API 抓取 @{handle} 失败: {e}[/yellow]")
        return results

    def _fetch_via_nitter(self, handle: str, weight: int, client: httpx.Client) -> list[FeedItem]:
        """
        无 Token 时的降级方案：
        抓取 Nitter RSS（nitter.net 已关，用可用实例）
        """
        nitter_instances = [
            "https://nitter.privacyredirect.com",
            "https://nitter.poast.org",
        ]
        results = []

        import feedparser
        for instance in nitter_instances:
            try:
                rss_url = f"{instance}/{handle}/rss"
                feed = feedparser.parse(rss_url)
                if not feed.entries:
                    continue

                for entry in feed.entries[:10]:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")[:300]
                    url = entry.get("link", "").replace(instance, "https://x.com")

                    if not self._is_relevant(title + summary):
                        continue

                    item_id = hashlib.md5(url.encode()).hexdigest()
                    if item_id in self._seen:
                        continue

                    item = FeedItem(
                        id=item_id,
                        title=f"@{handle}: {title[:80]}",
                        url=url,
                        source=f"X/@{handle}",
                        summary=summary,
                        published_at=datetime.now(timezone.utc),
                        score=weight / 10 * 0.6,
                        article_type="kol_insight",
                    )
                    results.append(item)
                    self._seen.add(item_id)
                break  # 第一个成功的实例就够了

            except Exception:
                continue
        return results

    def fetch_all(self) -> list[FeedItem]:
        results: list[FeedItem] = []
        use_api = bool(self.bearer_token)

        with httpx.Client(timeout=15) as client:
            for account in self.accounts:
                handle = account["handle"]
                weight = account.get("weight", 5)
                console.print(f"[dim]抓取 X @{handle}...[/dim]")

                if use_api:
                    items = self._fetch_via_api(handle, weight, client)
                else:
                    items = self._fetch_via_nitter(handle, weight, client)
                results.extend(items)

        self._save_seen()
        console.print(f"[green]X 采集完成，新增 {len(results)} 条[/green]")
        return results
