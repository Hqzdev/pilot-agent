"""Optional web_fetch tool with SSRF checks before any HTTP request."""

from __future__ import annotations

import html
import ipaddress
import re
import socket
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import requests

from pilot_agent.tools.base import Tool


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        self._skip = tag in {"script", "style", "noscript"}

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self.parts))


class WebFetchTool(Tool):
    name = "web_fetch"
    parallel_safe = True
    description = "Fetch an HTTP(S) page, reject private IP targets, and return extracted text."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
        "additionalProperties": False,
    }

    def execute(self, **kwargs: Any) -> str:
        url = str(kwargs["url"])
        _validate_public_http_url(url)
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return _extract_text(response.text)


def _validate_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("web_fetch accepts only http/https URLs")
    for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError(f"blocked private or local address: {ip}")


def _extract_text(raw_html: str) -> str:
    try:
        import trafilatura

        extracted = trafilatura.extract(raw_html, output_format="markdown")
        if extracted:
            return extracted
    except Exception:
        pass
    parser = _TextExtractor()
    parser.feed(raw_html)
    return html.unescape(parser.text())
