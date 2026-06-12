"""Small web-search provider registry used by the `web_search` tool."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query: str, max_results: int) -> list[SearchResult]: ...


class TavilySearchProvider(SearchProvider):
    name = "tavily"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        response = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": self.api_key, "query": query, "max_results": max_results},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return [
            SearchResult(
                title=str(item.get("title", "Untitled")),
                url=str(item.get("url", "")),
                snippet=str(item.get("content", "")),
            )
            for item in data.get("results", [])
            if isinstance(item, dict) and item.get("url")
        ]


class BraveSearchProvider(SearchProvider):
    name = "brave"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": str(max_results)},
            headers={"X-Subscription-Token": self.api_key},
            timeout=10,
        )
        response.raise_for_status()
        items = response.json().get("web", {}).get("results", [])
        return [
            SearchResult(
                title=str(item.get("title", "Untitled")),
                url=str(item.get("url", "")),
                snippet=str(item.get("description", "")),
            )
            for item in items
            if isinstance(item, dict) and item.get("url")
        ]


class SearxngSearchProvider(SearchProvider):
    name = "searxng"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        response = requests.get(
            f"{self.base_url}/search",
            params={"q": query, "format": "json"},
            timeout=10,
        )
        response.raise_for_status()
        items = response.json().get("results", [])[:max_results]
        return [
            SearchResult(
                title=str(item.get("title", "Untitled")),
                url=str(item.get("url", "")),
                snippet=str(item.get("content", "")),
            )
            for item in items
            if isinstance(item, dict) and item.get("url")
        ]


def provider_from_config(
    name: str,
    *,
    api_key: str | None,
    searxng_url: str | None,
) -> SearchProvider:
    registry: dict[str, type[SearchProvider]] = {
        "tavily": TavilySearchProvider,
        "brave": BraveSearchProvider,
        "searxng": SearxngSearchProvider,
    }
    if name == "searxng":
        if not searxng_url:
            raise ValueError("searxng_url is required for searxng search")
        return SearxngSearchProvider(searxng_url)
    if not api_key:
        raise ValueError(f"{name} API key is not configured")
    provider_cls = registry[name]
    return provider_cls(api_key)  # type: ignore[call-arg]


def result_from_mapping(data: dict[str, Any]) -> SearchResult:
    return SearchResult(
        title=str(data.get("title", "Untitled")),
        url=str(data.get("url", "")),
        snippet=str(data.get("snippet", "")),
    )
