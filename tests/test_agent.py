from research_agent.agent import ResearchAgent
from research_agent.tools import Page, SearchHit


class FakeTools:
    def __init__(self, hits=None, pages=None):
        self.hits = hits or []
        self.pages = pages or {}
        self.fetches = []
    def web_search(self, query):
        return self.hits
    def fetch_page(self, url):
        self.fetches.append(url)
        return self.pages.get(url)


def test_default_run_fetches_and_cites_only_fetched_pages():
    hit = SearchHit("NASA", "https://example.org/nasa", "NASA facts")
    page = Page(hit.url, hit.title, "NASA reports the mission launched in 2024. This is a sufficiently long sentence for extraction.")
    tools = FakeTools([hit], {hit.url: page})
    result = ResearchAgent(tools, max_steps=2).run("When did the mission launch?")
    assert result.steps == 2
    assert len(result.sources) == 1
    assert "[1]" in result.answer


def test_empty_search_is_graceful():
    result = ResearchAgent(FakeTools(), max_steps=2).run("Anything?")
    assert result.steps == 1
    assert "could not fetch" in result.answer
    assert result.notes


def test_fetch_failure_is_graceful_and_budget_is_hard():
    hits = [SearchHit(str(i), f"https://example.org/{i}") for i in range(10)]
    tools = FakeTools(hits, {})
    result = ResearchAgent(tools, max_steps=3).run("Find facts")
    assert result.steps == 3
    assert len(tools.fetches) == 2
    assert "could not fetch" in result.answer


def test_invalid_question_and_budget():
    import pytest
    with pytest.raises(ValueError):
        ResearchAgent(FakeTools(), max_steps=0)
    with pytest.raises(ValueError):
        ResearchAgent(FakeTools()).run("   ")


def test_bad_citations_are_removed():
    pages = [Page("https://example.org", "Example", "Evidence sentence is present in this fetched source.")]
    text = ResearchAgent._validate_citations("Unsupported statement. Supported statement [1]. Fake citation [7].", pages)
    assert "Unsupported" not in text
    assert "Supported" in text
    assert "Fake citation" not in text


def test_openrouter_environment_config(monkeypatch):
    import research_agent.agent as agent_module

    monkeypatch.setenv("RESEARCH_AGENT_MODEL", "provider/example-model")
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://example.org")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "Research Demo")
    captured = {}

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "{}"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(agent_module.httpx, "post", fake_post)
    agent = ResearchAgent(FakeTools())
    agent._chat([])
    assert agent.model == "provider/example-model"
    assert agent.api_key == "router-key"
    assert agent.base_url == "https://openrouter.ai/api/v1"
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["HTTP-Referer"] == "https://example.org"
    assert captured["headers"]["X-Title"] == "Research Demo"
