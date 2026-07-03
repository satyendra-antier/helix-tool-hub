"""Website crawler — same-origin BFS with configurable page limit."""

from __future__ import annotations

import re
from collections import deque
from typing import Callable
from urllib.parse import urljoin, urlparse, urldefrag

import httpx
from bs4 import BeautifulSoup

from config import settings

SKIP_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".zip",
    ".mp4", ".mp3", ".css", ".js", ".ico", ".woff", ".woff2",
}


def _normalize_url(url: str) -> str:
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _is_same_origin(base: str, url: str) -> bool:
    b = urlparse(base)
    u = urlparse(url)
    return u.netloc == b.netloc and u.scheme in ("http", "https")


def _should_skip(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in SKIP_EXTENSIONS)


def _extract_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title else ""
    main = soup.find("main") or soup.find("article") or soup.body
    if not main:
        return title, ""
    text = re.sub(r"\s+", " ", main.get_text(separator=" ", strip=True))
    return title, text.strip()


def _discover_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if _is_same_origin(base_url, href) and not _should_skip(href):
            links.append(_normalize_url(href))
    return links


def crawl_website(
    start_url: str,
    max_pages: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict]:
    max_pages = max_pages or settings.max_crawl_pages
    start_url = _normalize_url(start_url)
    visited: set[str] = set()
    queue: deque[str] = deque([start_url])
    pages: list[dict] = []

    headers = {
        "User-Agent": "ToolHub-BuildReadiness/1.0 (+company capability indexer)",
        "Accept": "text/html,application/xhtml+xml",
    }

    with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
        while queue and len(pages) < max_pages:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    continue
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue
                title, text = _extract_text(resp.text)
                if len(text) < 80:
                    continue
                pages.append({"url": url, "title": title, "text": text})
                if on_progress and len(pages) % 5 == 0:
                    on_progress(len(pages), len(visited))
                for link in _discover_links(url, resp.text):
                    if link not in visited:
                        queue.append(link)
            except Exception:
                continue

    if on_progress:
        on_progress(len(pages), len(visited))
    return pages
