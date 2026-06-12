"""Optional web_search tool with Tavily, Brave, and SearxNG providers."""

from __future__ import annotations

from typing import Any

from pilot_agent.tools.base import Tool
from pilot_agent.tools.search_providers import SearchProvider


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web and return a numbered list of titles, URLs, and snippets."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self, provider: SearchProvider, default_max_results: int = 5):
        self.provider = provider
        self.default_max_results = default_max_results

    def execute(self, **kwargs: Any) -> str:
        query = str(kwargs["query"])
        max_results = int(kwargs.get("max_results", self.default_max_results))
        results = self.provider.search(query, max_results)
        if not results:
            return "No results."
        lines: list[str] = []
        for idx, item in enumerate(results[:max_results], start=1):
            snippet = " ".join(item.snippet.split())[:300]
            lines.append(f"[{idx}] {item.title} — {item.url}\n    {snippet}")
        return "\n".join(lines)
