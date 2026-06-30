"""Lightweight web research service for explicit research-mode retrieval.

This module prefers API-based search providers for reliability and falls back
to DuckDuckGo HTML parsing when API keys are unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
import json
import os
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen
import re


class WebResearchError(ValueError):
    """Raised when web research cannot be completed."""


_RESULT_LINK_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_RESULT_SNIPPET_RE = re.compile(
    r'<(?:a|div)[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</(?:a|div)>',
    re.IGNORECASE | re.DOTALL,
)
_DDG_CHALLENGE_RE = re.compile(
    r"anomaly\.js|javascript required|enable javascript|human verification|automated requests",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_PROVIDER_AUTO = "auto"
_PROVIDER_DDG = "duckduckgo_html"
_PROVIDER_SERPER = "serper_google"
_PROVIDER_BRAVE = "brave_search"
_PROVIDER_SEARXNG = "searxng"

_VALID_PROVIDERS = {
    _PROVIDER_AUTO,
    _PROVIDER_DDG,
    _PROVIDER_SERPER,
    _PROVIDER_BRAVE,
    _PROVIDER_SEARXNG,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _strip_html(text: str) -> str:
    stripped = _TAG_RE.sub(" ", unescape(text or ""))
    return _WS_RE.sub(" ", stripped).strip()


def _normalize_result_url(raw_href: str) -> str:
    href = unescape((raw_href or "").strip())
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path == "/l/":
        uddg = parse_qs(parsed.query).get("uddg", [])
        if uddg:
            return unescape(uddg[0]).strip()
    return href


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


@dataclass(frozen=True)
class WebResearchSource:
    """One web-search result with provenance and optional fetched excerpt."""

    source_id: str
    provider: str
    query: str
    title: str
    url: str
    snippet: str
    retrieved_at: str
    fetched_excerpt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "source_id": self.source_id,
            "provider": self.provider,
            "query": self.query,
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "retrieved_at": self.retrieved_at,
        }
        if self.fetched_excerpt is not None:
            data["fetched_excerpt"] = self.fetched_excerpt
        return data


class WebResearchService:
    """Perform real web search and normalize source provenance.

    Provider selection:
    - explicit provider via WEB_RESEARCH_PROVIDER
    - ``auto`` prefers API-backed engines for better reliability:
            1) SearXNG (SEARXNG_BASE_URL, free/self-hosted)
            2) Serper (SERPER_API_KEY)
            3) Brave Search (BRAVE_SEARCH_API_KEY)
            4) DuckDuckGo HTML fallback
    """

    def __init__(
        self,
        *,
        opener: Optional[Callable[..., Any]] = None,
        timeout_seconds: float = 10.0,
        user_agent: str = "SaxoFlowResearchBot/1.0",
        provider: Optional[str] = None,
    ) -> None:
        self._opener = opener or urlopen
        self._timeout_seconds = float(timeout_seconds)
        self._user_agent = user_agent
        configured = str(provider or os.getenv("WEB_RESEARCH_PROVIDER") or _PROVIDER_AUTO).strip().lower()
        if configured not in _VALID_PROVIDERS:
            allowed = ", ".join(sorted(_VALID_PROVIDERS))
            raise WebResearchError(f"Unsupported web provider `{configured}`. Allowed: {allowed}.")
        self._configured_provider = configured
        self.provider_name = configured if configured != _PROVIDER_AUTO else _PROVIDER_DDG

    def search(
        self,
        query: str,
        *,
        max_results: int = 3,
        fetch_pages: bool = False,
        max_fetched_pages: int = 2,
        excerpt_chars: int = 1200,
    ) -> List[WebResearchSource]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            raise WebResearchError("Web research query cannot be empty.")

        selected_provider = self._resolve_provider()
        self.provider_name = selected_provider

        if selected_provider == _PROVIDER_SERPER:
            sources = self._search_serper(normalized_query, max_results=max_results)
        elif selected_provider == _PROVIDER_BRAVE:
            sources = self._search_brave(normalized_query, max_results=max_results)
        elif selected_provider == _PROVIDER_SEARXNG:
            sources = self._search_searxng(normalized_query, max_results=max_results)
        else:
            sources = self._search_duckduckgo(normalized_query, max_results=max_results)

        if fetch_pages:
            capped = min(max_fetched_pages, len(sources))
            for index in range(capped):
                item = sources[index]
                sources[index] = WebResearchSource(
                    source_id=item.source_id,
                    provider=item.provider,
                    query=item.query,
                    title=item.title,
                    url=item.url,
                    snippet=item.snippet,
                    retrieved_at=item.retrieved_at,
                    fetched_excerpt=self._fetch_excerpt(item.url, excerpt_chars=excerpt_chars),
                )

        return sources

    def _resolve_provider(self) -> str:
        if self._configured_provider != _PROVIDER_AUTO:
            if self._configured_provider == _PROVIDER_SERPER and not os.getenv("SERPER_API_KEY"):
                raise WebResearchError("SERPER_API_KEY is required for provider `serper_google`.")
            if self._configured_provider == _PROVIDER_BRAVE and not os.getenv("BRAVE_SEARCH_API_KEY"):
                raise WebResearchError("BRAVE_SEARCH_API_KEY is required for provider `brave_search`.")
            if self._configured_provider == _PROVIDER_SEARXNG and not os.getenv("SEARXNG_BASE_URL"):
                raise WebResearchError("SEARXNG_BASE_URL is required for provider `searxng`.")
            return self._configured_provider

        if os.getenv("SEARXNG_BASE_URL"):
            return _PROVIDER_SEARXNG
        if os.getenv("SERPER_API_KEY"):
            return _PROVIDER_SERPER
        if os.getenv("BRAVE_SEARCH_API_KEY"):
            return _PROVIDER_BRAVE
        return _PROVIDER_DDG

    def _search_searxng(self, query: str, *, max_results: int) -> List[WebResearchSource]:
        base_urls: List[str] = []
        base_urls.extend(_split_csv(str(os.getenv("SEARXNG_BASE_URL") or "")))
        base_urls.extend(_split_csv(str(os.getenv("SEARXNG_FALLBACK_URLS") or "")))
        base_urls = [item.rstrip("/") for item in base_urls]
        base_urls = list(dict.fromkeys(base_urls))

        if not base_urls:
            raise WebResearchError("SEARXNG_BASE_URL is required for provider `searxng`.")

        errors: List[str] = []
        for base_url in base_urls:
            url = (
                f"{base_url}/search"
                f"?q={quote_plus(query)}&format=json&language=en&safesearch=1"
            )
            try:
                raw = self._request_text(url, extra_headers={"Accept": "application/json"})
            except WebResearchError as exc:
                errors.append(f"{base_url}: {exc}")
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"{base_url}: invalid JSON")
                continue

            results = data.get("results") or []
            sources: List[WebResearchSource] = []
            seen_urls = set()
            for item in results:
                if len(sources) >= max_results or not isinstance(item, dict):
                    break
                link = str(item.get("url") or item.get("link") or "").strip()
                if not link or link in seen_urls:
                    continue
                title = str(item.get("title") or link).strip() or link
                snippet = _strip_html(str(item.get("content") or item.get("snippet") or "").strip())
                sources.append(
                    WebResearchSource(
                        source_id=str(len(sources) + 1),
                        provider=self.provider_name,
                        query=query,
                        title=title,
                        url=link,
                        snippet=snippet,
                        retrieved_at=_utc_now_iso(),
                    )
                )
                seen_urls.add(link)
            return sources

        raise WebResearchError(
            "All SearXNG endpoints failed. " + " | ".join(errors[-3:])
        )

    def _search_duckduckgo(self, query: str, *, max_results: int) -> List[WebResearchSource]:
        search_html = self._read_text(
            f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        )
        if _DDG_CHALLENGE_RE.search(search_html):
            raise WebResearchError(
                "DuckDuckGo challenge page returned; provider blocked automated search requests."
            )
        links = list(_RESULT_LINK_RE.finditer(search_html))
        snippets = [
            _strip_html(match.group("snippet"))
            for match in _RESULT_SNIPPET_RE.finditer(search_html)
        ]
        if not links:
            return []

        sources: List[WebResearchSource] = []
        seen_urls = set()
        for index, match in enumerate(links):
            if len(sources) >= max_results:
                break
            url = _normalize_result_url(match.group("href"))
            if not url or url in seen_urls:
                continue
            title = _strip_html(match.group("title")) or url
            snippet = snippets[index] if index < len(snippets) else ""
            sources.append(
                WebResearchSource(
                    source_id=str(len(sources) + 1),
                    provider=self.provider_name,
                    query=query,
                    title=title,
                    url=url,
                    snippet=snippet,
                    retrieved_at=_utc_now_iso(),
                )
            )
            seen_urls.add(url)
        return sources

    def _search_serper(self, query: str, *, max_results: int) -> List[WebResearchSource]:
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            raise WebResearchError("SERPER_API_KEY is required for provider `serper_google`.")

        payload = json.dumps({"q": query, "num": max_results}).encode("utf-8")
        raw = self._request_text(
            "https://google.serper.dev/search",
            method="POST",
            data=payload,
            extra_headers={
                "Content-Type": "application/json",
                "X-API-KEY": api_key,
            },
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WebResearchError("Serper returned invalid JSON.") from exc

        organic = data.get("organic") or []
        sources: List[WebResearchSource] = []
        seen_urls = set()
        for item in organic:
            if len(sources) >= max_results or not isinstance(item, dict):
                break
            url = str(item.get("link") or "").strip()
            if not url or url in seen_urls:
                continue
            title = str(item.get("title") or url).strip() or url
            snippet = str(item.get("snippet") or "").strip()
            sources.append(
                WebResearchSource(
                    source_id=str(len(sources) + 1),
                    provider=self.provider_name,
                    query=query,
                    title=title,
                    url=url,
                    snippet=snippet,
                    retrieved_at=_utc_now_iso(),
                )
            )
            seen_urls.add(url)
        return sources

    def _search_brave(self, query: str, *, max_results: int) -> List[WebResearchSource]:
        api_key = os.getenv("BRAVE_SEARCH_API_KEY")
        if not api_key:
            raise WebResearchError("BRAVE_SEARCH_API_KEY is required for provider `brave_search`.")

        raw = self._request_text(
            f"https://api.search.brave.com/res/v1/web/search?q={quote_plus(query)}&count={int(max_results)}",
            extra_headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WebResearchError("Brave Search returned invalid JSON.") from exc

        results = ((data.get("web") or {}).get("results") or [])
        sources: List[WebResearchSource] = []
        seen_urls = set()
        for item in results:
            if len(sources) >= max_results or not isinstance(item, dict):
                break
            url = str(item.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            title = str(item.get("title") or url).strip() or url
            snippet = _strip_html(str(item.get("description") or "").strip())
            sources.append(
                WebResearchSource(
                    source_id=str(len(sources) + 1),
                    provider=self.provider_name,
                    query=query,
                    title=title,
                    url=url,
                    snippet=snippet,
                    retrieved_at=_utc_now_iso(),
                )
            )
            seen_urls.add(url)
        return sources

    def _fetch_excerpt(self, url: str, *, excerpt_chars: int) -> Optional[str]:
        try:
            page_html = self._read_text(url)
        except WebResearchError:
            return None
        excerpt = _strip_html(page_html)
        if not excerpt:
            return None
        return excerpt[:excerpt_chars]

    def _read_text(self, url: str) -> str:
        return self._request_text(url)

    def _request_text(
        self,
        url: str,
        *,
        method: str = "GET",
        data: Optional[bytes] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str:
        headers = {"User-Agent": self._user_agent}
        if extra_headers:
            headers.update(extra_headers)
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            raise WebResearchError(f"Could not retrieve `{url}`: {exc}") from exc