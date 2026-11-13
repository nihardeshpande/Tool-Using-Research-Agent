"""Small, replaceable web tools. Network failures are returned as data."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from ddgs import DDGS


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str = ""


@dataclass
class Page:
    url: str
    title: str
    text: str


class WebTools:
    def __init__(self, timeout: float = 15, search_results: int = 5):
        self.timeout = timeout
        self.search_results = search_results
        self.last_error: str | None = None

    def web_search(self, query: str) -> list[SearchHit]:
        """Search the public web through DuckDuckGo; an empty list is valid."""
        self.last_error = None
        try:
            with DDGS(timeout=self.timeout) as ddgs:
                rows = ddgs.text(query, max_results=self.search_results)
                return [SearchHit(str(x.get("title", "")), str(x.get("href", "")), str(x.get("body", "")))
                        for x in rows if x.get("href")]
        except Exception as exc:  # network/provider errors should not crash the run
            self.last_error = f"{type(exc).__name__}: {exc}"
            return []

    def fetch_page(self, url: str) -> Page | None:
        """Fetch and lightly clean an HTML page. Only http(s) URLs are accepted."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        try:
            response = httpx.get(url, timeout=self.timeout, follow_redirects=True,
                                 headers={"User-Agent": "ResearchAgent/0.1 (source-grounded research)"})
            response.raise_for_status()
            html = response.text
            from html.parser import HTMLParser

            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__(); self.parts = []; self.title_parts = []; self.in_title = False
                    self.skip = 0
                def handle_starttag(self, tag, attrs):
                    if tag in {"script", "style", "noscript", "svg"}: self.skip += 1
                    if tag == "title": self.in_title = True
                    if tag in {"p", "li", "h1", "h2", "h3", "br", "div"}: self.parts.append(" ")
                def handle_endtag(self, tag):
                    if tag in {"script", "style", "noscript", "svg"} and self.skip: self.skip -= 1
                    if tag == "title": self.in_title = False
                    if tag in {"p", "li", "h1", "h2", "h3", "br", "div"}: self.parts.append(" ")
                def handle_data(self, data):
                    if self.skip: return
                    clean = " ".join(data.split())
                    if clean:
                        self.parts.append(clean)
                        if self.in_title: self.title_parts.append(clean)
            parser = TextExtractor(); parser.feed(html)
            text = " ".join(" ".join(parser.parts).split())
            if not text:
                return None
            return Page(str(response.url), " ".join(parser.title_parts) or str(response.url), text[:30000])
        except Exception:
            return None
