"""Tests for real web retrieval backing explicit research mode."""

from __future__ import annotations

import pytest


class _FakeResponse:
    def __init__(self, text: str):
        self._payload = text.encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_web_research_service_parses_search_results_and_fetches_excerpts():
    from saxoflow.services.web_research_service import WebResearchService

    search_html = """
    <html>
      <body>
        <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fopenroad">Example OpenROAD</a>
        <div class="result__snippet">OpenROAD is an RTL-to-GDS flow.</div>
        <a class="result__a" href="https://example.com/nextpnr">Example nextpnr</a>
        <div class="result__snippet">nextpnr is a fast FPGA place-and-route tool.</div>
      </body>
    </html>
    """
    page_map = {
        "https://html.duckduckgo.com/html/?q=compare+pnr+flows": search_html,
        "https://example.com/openroad": "<html><body><p>OpenROAD detailed article text.</p></body></html>",
        "https://example.com/nextpnr": "<html><body><p>nextpnr detailed article text.</p></body></html>",
    }

    def fake_opener(request, timeout=10.0):
        return _FakeResponse(page_map[request.full_url])

    service = WebResearchService(opener=fake_opener, provider="duckduckgo_html")
    results = service.search(
        "compare pnr flows",
        max_results=2,
        fetch_pages=True,
        max_fetched_pages=2,
    )

    assert len(results) == 2
    assert results[0].source_id == "1"
    assert results[0].title == "Example OpenROAD"
    assert results[0].url == "https://example.com/openroad"
    assert results[0].snippet == "OpenROAD is an RTL-to-GDS flow."
    assert results[0].fetched_excerpt is not None
    assert "OpenROAD detailed article text." in results[0].fetched_excerpt
    assert results[1].url == "https://example.com/nextpnr"


def test_web_research_service_returns_empty_results_without_failure():
    from saxoflow.services.web_research_service import WebResearchService

    def fake_opener(request, timeout=10.0):
        return _FakeResponse("<html><body>No results</body></html>")

    service = WebResearchService(opener=fake_opener, provider="duckduckgo_html")
    results = service.search("compare pnr flows", max_results=3, fetch_pages=False)

    assert results == []


def test_web_research_service_surfaces_duckduckgo_challenge_page():
    from saxoflow.services.web_research_service import WebResearchError, WebResearchService

    def fake_opener(request, timeout=10.0):
        return _FakeResponse("<html><body><script src='/anomaly.js'></script></body></html>")

    service = WebResearchService(opener=fake_opener, provider="duckduckgo_html")
    with pytest.raises(WebResearchError, match="challenge page"):
        service.search("openroad timing closure", max_results=3, fetch_pages=False)


def test_web_research_service_prefers_serper_when_key_is_present(monkeypatch):
    from saxoflow.services.web_research_service import WebResearchService

    monkeypatch.setenv("WEB_RESEARCH_PROVIDER", "auto")
    monkeypatch.delenv("SEARXNG_BASE_URL", raising=False)
    monkeypatch.delenv("SEARXNG_FALLBACK_URLS", raising=False)
    monkeypatch.setenv("SERPER_API_KEY", "test-serper-key")

    def fake_opener(request, timeout=10.0):
        if request.full_url == "https://google.serper.dev/search":
            return _FakeResponse(
                """
                {
                    "organic": [
                        {
                            "title": "OpenROAD Docs",
                            "link": "https://openroad.readthedocs.io/en/latest/",
                            "snippet": "OpenROAD documentation"
                        }
                    ]
                }
                """
            )
        raise AssertionError(f"Unexpected URL requested: {request.full_url}")

    service = WebResearchService(opener=fake_opener)
    results = service.search("openroad docs", max_results=3, fetch_pages=False)

    assert service.provider_name == "serper_google"
    assert len(results) == 1
    assert results[0].url == "https://openroad.readthedocs.io/en/latest/"
    assert results[0].provider == "serper_google"


def test_web_research_service_prefers_searxng_when_base_url_is_set(monkeypatch):
    from saxoflow.services.web_research_service import WebResearchService

    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.setenv("SEARXNG_BASE_URL", "https://search.example.org")

    def fake_opener(request, timeout=10.0):
        if request.full_url.startswith("https://search.example.org/search?"):
            return _FakeResponse(
                """
                {
                    "results": [
                        {
                            "title": "OpenROAD project",
                            "url": "https://github.com/The-OpenROAD-Project/OpenROAD",
                            "content": "OpenROAD repository and docs"
                        }
                    ]
                }
                """
            )
        raise AssertionError(f"Unexpected URL requested: {request.full_url}")

    service = WebResearchService(opener=fake_opener)
    results = service.search("openroad", max_results=3, fetch_pages=False)

    assert service.provider_name == "searxng"
    assert len(results) == 1
    assert results[0].provider == "searxng"
    assert results[0].url == "https://github.com/The-OpenROAD-Project/OpenROAD"


def test_web_research_service_searxng_fallbacks_to_secondary_endpoint(monkeypatch):
    from saxoflow.services.web_research_service import WebResearchService

    monkeypatch.setenv("SEARXNG_BASE_URL", "https://blocked.example.org")
    monkeypatch.setenv("SEARXNG_FALLBACK_URLS", "https://ok.example.org")

    def fake_opener(request, timeout=10.0):
        if request.full_url.startswith("https://blocked.example.org/search?"):
            raise Exception("HTTP Error 403: Forbidden")
        if request.full_url.startswith("https://ok.example.org/search?"):
            return _FakeResponse(
                """
                {
                    "results": [
                        {
                            "title": "OpenSTA docs",
                            "url": "https://openroad.readthedocs.io/en/latest/main/src/sta/README.html",
                            "content": "OpenSTA integration docs"
                        }
                    ]
                }
                """
            )
        raise AssertionError(f"Unexpected URL requested: {request.full_url}")

    service = WebResearchService(opener=fake_opener)
    results = service.search("opensta docs", max_results=3, fetch_pages=False)

    assert len(results) == 1
    assert results[0].url == "https://openroad.readthedocs.io/en/latest/main/src/sta/README.html"