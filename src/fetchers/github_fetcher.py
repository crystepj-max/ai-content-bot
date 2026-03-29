"""
GitHub 采集器
抓取 AI 相关快速涨星的开源项目
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import yaml
from rich.console import Console

from .rss_fetcher import FeedItem

console = Console()

GITHUB_API = "https://api.github.com"


@dataclass
class GitHubProject:
    repo: str           # owner/name
    full_name: str
    description: str
    stars: int
    stars_7d: int       # 7天涨星（近似值）
    url: str
    topics: list[str]
    language: str
    readme_excerpt: str = ""
    pushed_at: datetime = None


class GitHubFetcher:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.gh_config = self.config["sources"]["github"]
        self.ai_topics: list[str] = self.config["topics"]["github_topics"]
        self.keywords: list[str] = [
            kw.lower() for kw in self.config["topics"]["keywords"]
        ]
        self.token: str = os.environ.get("GITHUB_TOKEN", "")
        self.cache_path = Path(".cache/github_seen.json")
        self.cache_path.parent.mkdir(exist_ok=True)
        self._seen: set[str] = self._load_seen()

    def _load_seen(self) -> set[str]:
        if self.cache_path.exists():
            return set(json.loads(self.cache_path.read_text()))
        return set()

    def _save_seen(self) -> None:
        self.cache_path.write_text(json.dumps(list(self._seen)))

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _is_ai_related(self, repo: dict) -> bool:
        topics = repo.get("topics", [])
        desc = (repo.get("description") or "").lower()
        name = repo.get("name", "").lower()
        text = desc + " " + name + " " + " ".join(topics)

        # 命中 AI 话题标签
        if any(t in topics for t in self.ai_topics):
            return True
        # 命中关键词
        if any(kw in text for kw in self.keywords):
            return True
        return False

    def _fetch_readme(self, full_name: str, client: httpx.Client) -> str:
        try:
            r = client.get(
                f"{GITHUB_API}/repos/{full_name}/readme",
                headers={**self._headers(), "Accept": "application/vnd.github.raw"},
                timeout=10,
            )
            if r.status_code == 200:
                return r.text[:2000]  # 只取前2000字
        except Exception:
            pass
        return ""

    def fetch_trending(self) -> list[FeedItem]:
        """
        通过 GitHub Search API 查询近7天 star 增长最快的 AI 项目
        """
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        min_stars = self.gh_config.get("min_total_stars", 500)
        results: list[FeedItem] = []

        queries = [
            f"topic:llm pushed:>{since} stars:>{min_stars}",
            f"topic:large-language-model pushed:>{since} stars:>{min_stars}",
            f"topic:ai-agent pushed:>{since} stars:>{min_stars}",
            f"llm OR 'language model' OR 'AI agent' in:description pushed:>{since} stars:>{min_stars}",
        ]

        seen_repos: set[str] = set()

        with httpx.Client(timeout=20) as client:
            for query in queries:
                try:
                    console.print(f"[dim]GitHub 搜索: {query[:60]}...[/dim]")
                    r = client.get(
                        f"{GITHUB_API}/search/repositories",
                        params={"q": query, "sort": "stars", "order": "desc", "per_page": 10},
                        headers=self._headers(),
                    )
                    if r.status_code != 200:
                        console.print(f"[yellow]GitHub API 返回 {r.status_code}[/yellow]")
                        continue

                    for repo in r.json().get("items", []):
                        full_name = repo["full_name"]
                        if full_name in seen_repos:
                            continue
                        seen_repos.add(full_name)

                        item_id = hashlib.md5(full_name.encode()).hexdigest()
                        if item_id in self._seen:
                            continue

                        if not self._is_ai_related(repo):
                            continue

                        # 获取 README 摘要
                        readme = self._fetch_readme(full_name, client)

                        desc = repo.get("description") or ""
                        stars = repo.get("stargazers_count", 0)

                        # 用 star 数近似代表热度（无法精确拿7日增量，除非有历史快照）
                        engagement_score = min(stars / 50000, 1.0)

                        item = FeedItem(
                            id=item_id,
                            title=f"【开源】{full_name} — {desc[:60]}",
                            url=repo["html_url"],
                            source="GitHub Trending",
                            summary=f"{desc}\n\nStar: {stars:,} | 语言: {repo.get('language','未知')} | 话题: {', '.join(repo.get('topics',[])[:5])}",
                            published_at=datetime.now(timezone.utc),
                            raw_content=readme,
                            score=0.5 + engagement_score * 0.5,
                            article_type="github_project",
                        )
                        results.append(item)
                        self._seen.add(item_id)

                except Exception as e:
                    console.print(f"[red]GitHub 搜索异常: {e}[/red]")

        self._save_seen()
        console.print(f"[green]GitHub 采集完成，新增 {len(results)} 个项目[/green]")
        return results
