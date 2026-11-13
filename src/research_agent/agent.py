"""Bounded research loop with citations tied to successfully fetched pages."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from .tools import Page, SearchHit, WebTools


@dataclass
class ResearchResult:
    question: str
    answer: str
    sources: list[Page] = field(default_factory=list)
    steps: int = 0
    notes: list[str] = field(default_factory=list)


class ResearchAgent:
    """An agent with two selectable tools and an enforced maximum call count."""

    def __init__(self, tools: WebTools | None = None, max_steps: int = 6,
                 model: str | None = None, api_key: str | None = None,
                 base_url: str | None = None, timeout: float = 20):
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        self.tools = tools or WebTools()
        self.max_steps = max_steps
        self.model = model or os.getenv("RESEARCH_AGENT_MODEL")
        self.api_key = api_key if api_key is not None else (
            os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY", "")
        )
        default_base_url = "https://openrouter.ai/api/v1" if os.getenv("OPENROUTER_API_KEY") else "https://api.openai.com/v1"
        self.base_url = (base_url or os.getenv("OPENROUTER_BASE_URL") or os.getenv("OPENAI_BASE_URL") or default_base_url).rstrip("/")
        self.timeout = timeout

    def run(self, question: str) -> ResearchResult:
        question = question.strip()
        if not question:
            raise ValueError("Please provide a research question.")
        hits: list[SearchHit] = []
        pages: list[Page] = []
        notes: list[str] = []
        steps = 0

        # Without a configured model, use a simple deterministic policy. Model-backed
        # runs use the same bounded loop and tool allowlist.
        if not self.model or not self.api_key:
            try:
                hits = self.tools.web_search(question)
            except Exception:
                notes.append("Search failed.")
            steps += 1
            if not hits:
                search_error = getattr(self.tools, "last_error", None)
                notes.append(f"Search failed: {search_error}" if search_error else "Search returned no results.")
            for hit in hits:
                if steps >= self.max_steps:
                    break
                try:
                    page = self.tools.fetch_page(hit.url)
                    steps += 1
                    if page and page.text.strip():
                        if not page.title or page.title == page.url:
                            page.title = hit.title or page.url
                        if page.url not in {p.url for p in pages}:
                            pages.append(page)
                except Exception:
                    steps += 1
                    notes.append(f"Could not fetch {hit.url}.")
            answer = self._extractive_answer(question, pages)
            return ResearchResult(question, answer, pages, steps, notes)

        # Model may choose either tool at each turn, but malformed/unsafe actions
        # consume a step and terminate gracefully. Tool calls count toward budget.
        history: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        while steps < self.max_steps:
            action = self._model_action(question, pages, history, seen_urls)
            if action is None:
                notes.append("Planner unavailable or returned an invalid action.")
                break
            kind = action.get("tool")
            if kind == "finish":
                answer = self._model_answer(question, pages)
                if answer:
                    answer = self._validate_citations(answer, pages)
                    return ResearchResult(question, answer, pages, steps, notes)
                break
            steps += 1
            try:
                if kind == "web_search" and isinstance(action.get("query"), str):
                    found = self.tools.web_search(action["query"])
                    hits.extend(found)
                    seen_urls.update(h.url for h in found)
                    history.append({"role": "assistant", "content": f"web_search: {action['query']}"})
                    history.append({"role": "user", "content": json.dumps([h.__dict__ for h in found[:8]])})
                    if not found:
                        search_error = getattr(self.tools, "last_error", None)
                        notes.append(f"Search failed: {search_error}" if search_error else "A search returned no results.")
                elif kind == "fetch_page" and isinstance(action.get("url"), str) and action["url"] in seen_urls:
                    page = self.tools.fetch_page(action["url"])
                    history.append({"role": "assistant", "content": f"fetch_page: {action['url']}"})
                    if page and page.text.strip():
                        if page.url not in {p.url for p in pages}: pages.append(page)
                        history.append({"role": "user", "content": json.dumps({"url": page.url, "title": page.title, "text": page.text[:5000]})})
                    else:
                        history.append({"role": "user", "content": "Fetch failed or page was empty."})
                        notes.append("A page could not be fetched or contained no readable text.")
                else:
                    notes.append("Planner selected an unsupported tool or invalid arguments.")
                    break
            except Exception:
                notes.append("A tool call failed; continuing with available sources.")
        if self.model and self.api_key:
            answer = self._model_answer(question, pages)
            if answer:
                answer = self._validate_citations(answer, pages)
            else:
                answer = self._extractive_answer(question, pages)
        else:
            answer = self._extractive_answer(question, pages)
        if steps >= self.max_steps:
            notes.append(f"Stopped at the hard limit of {self.max_steps} tool calls.")
        return ResearchResult(question, answer, pages, steps, notes)

    def _chat(self, messages: list[dict[str, str]], temperature: float = 0) -> str | None:
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            if "openrouter.ai" in self.base_url:
                site_url = os.getenv("OPENROUTER_SITE_URL")
                app_name = os.getenv("OPENROUTER_APP_NAME")
                if site_url:
                    headers["HTTP-Referer"] = site_url
                if app_name:
                    headers["X-Title"] = app_name
            response = httpx.post(f"{self.base_url}/chat/completions", timeout=self.timeout,
                                  headers=headers,
                                  json={"model": self.model, "messages": messages,
                                        "temperature": temperature, "response_format": {"type": "json_object"}})
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception:
            return None

    def _model_action(self, question: str, pages: list[Page], history: list[dict[str, str]],
                      seen_urls: set[str]) -> dict[str, Any] | None:
        source_state = [{"url": p.url, "title": p.title, "preview": p.text[:1000]} for p in pages]
        prompt = ("You are a research agent. Choose exactly one action as JSON: "
                  '{"tool":"web_search","query":"..."}, {"tool":"fetch_page","url":"..."}, or {"tool":"finish"}. '
                  "Use web_search for discovery, fetch_page only for a URL previously returned by search, and finish when "
                  "enough fetched evidence exists or no useful action remains. Never invent URLs. Keep the question in view.\n"
                  f"Question: {question}\nFetched sources: {json.dumps(source_state)}")
        raw = self._chat([{"role": "system", "content": prompt}, *history])
        try:
            action = json.loads(raw or "")
            if action.get("tool") == "fetch_page" and action.get("url") not in seen_urls:
                return None
            return action if isinstance(action, dict) else None
        except (json.JSONDecodeError, AttributeError):
            return None

    def _model_answer(self, question: str, pages: list[Page]) -> str | None:
        if not pages:
            return self._extractive_answer(question, pages)
        evidence = "\n\n".join(f"[{i}] {p.title}\nURL: {p.url}\n{p.text[:7000]}" for i, p in enumerate(pages, 1))
        prompt = ("Answer the research question using only the supplied fetched-source evidence. "
                  "Put a citation [n] on every factual sentence, with n matching a source below. "
                  "Do not add unsupported facts. If evidence is insufficient, say so plainly. Return JSON {\"answer\": \"...\"}.\n\n"
                  f"Question: {question}\nEvidence:\n{evidence}")
        raw = self._chat([{"role": "user", "content": prompt}])
        try:
            return json.loads(raw or "").get("answer")
        except (json.JSONDecodeError, AttributeError):
            return None

    @staticmethod
    def _validate_citations(answer: str, pages: list[Page]) -> str:
        """Drop any sentence lacking a valid fetched-source citation."""
        if not pages:
            return "I could not fetch any sources, so I can’t provide a source-grounded answer."
        valid = set(range(1, len(pages) + 1))
        kept = []
        for sentence in re.split(r"(?<=[.!?])\s+", answer.strip()):
            citations = {int(n) for n in re.findall(r"\[(\d+)\]", sentence)}
            if citations & valid:
                kept.append(sentence)
        return " ".join(kept) if kept else ResearchAgent._extractive_answer("", pages)

    @staticmethod
    def _extractive_answer(question: str, pages: list[Page]) -> str:
        if not pages:
            return "I could not fetch any sources, so I can’t provide a source-grounded answer."
        terms = {w.lower() for w in re.findall(r"[A-Za-z0-9]{4,}", question)}
        statements = []
        for i, page in enumerate(pages, 1):
            sentences = re.split(r"(?<=[.!?])\s+", page.text)
            ranked = sorted(enumerate(sentences), key=lambda pair: sum(t in pair[1].lower() for t in terms), reverse=True)
            chosen = next((s.strip() for _, s in ranked if len(s.strip()) > 40), "")
            if chosen:
                statements.append(f"{chosen[:420]} [{i}]")
            if len(statements) >= 3: break
        return "\n".join(statements) if statements else "Fetched sources did not contain readable evidence for an answer."
