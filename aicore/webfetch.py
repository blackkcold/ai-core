"""HTTPS-only page reader with pinned DNS/IP and bounded content.

Do not copy a search result's text into model instructions as trusted text.
A hostname must resolve exclusively to public IP addresses. We connect to
the validated IP while retaining the original SNI hostname, defeating the
usual DNS-check/use rebinding gap. Redirects are rejected.
"""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .errors import InvalidRequest, ProviderUnavailable, UnsafeURL

MAX_PAGE_BYTES = 1_000_000
MAX_TEXT_CHARS = 30_000


def validated_target(url: str, resolver=None) -> tuple[str, str, str]:
    if not isinstance(url, str) or len(url) > 4096:
        raise UnsafeURL("invalid URL")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise UnsafeURL("invalid URL") from exc
    if parts.scheme != "https" or not host or parts.username or parts.password or port not in (None, 443):
        raise UnsafeURL("only public HTTPS URLs on port 443 are allowed")
    if host.lower() in {"localhost", "localhost.localdomain"} or host.lower().endswith((".local", ".internal", ".localhost")):
        raise UnsafeURL("local destinations are forbidden")
    try:
        resolved = (resolver or socket.getaddrinfo)(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ProviderUnavailable("hostname resolution failed") from None
    ips = []
    for entry in resolved:
        address = entry[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise UnsafeURL("invalid DNS result") from None
        if not ip.is_global:
            raise UnsafeURL("private, reserved or non-global IP is forbidden")
        ips.append(str(ip))
    if not ips:
        raise ProviderUnavailable("no public IP for requested host")
    path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
    return host, ips[0], path


class _PinnedConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str, timeout: int):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self.pinned_ip, 443), timeout=self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if tag in {"p", "h1", "h2", "h3", "li", "div", "br", "article"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        elif not self.hidden:
            self.parts.append(data)


def fetch_page(url: str, *, timeout: int = 15, resolver=None, connection_factory=None) -> dict:
    host, ip, path = validated_target(url, resolver=resolver)
    conn = (connection_factory or _PinnedConnection)(host, ip, timeout)
    try:
        conn.request("GET", path, headers={
            "Host": host, "User-Agent": "ai-core/1.0 (+https://github.com/blackkcold/ai-core)",
            "Accept": "text/html,text/plain,text/markdown,application/json",
            "Accept-Encoding": "identity", "Connection": "close",
        })
        response = conn.getresponse()
        if response.status in range(300, 400):
            raise UnsafeURL("HTTP redirects are not followed")
        if response.status < 200 or response.status >= 300:
            raise ProviderUnavailable("page returned HTTP " + str(response.status))
        if response.getheader("Content-Encoding", "identity") not in {"identity", ""}:
            raise InvalidRequest("compressed page responses are not supported")
        content_type = response.getheader("Content-Type", "").split(";")[0].strip().lower()
        if content_type not in {"text/html", "text/plain", "text/markdown", "application/json"}:
            raise InvalidRequest("unsupported page Content-Type")
        content = response.read(MAX_PAGE_BYTES + 1)
        if len(content) > MAX_PAGE_BYTES:
            raise InvalidRequest("page exceeds 1 MB limit")
        encoding = "utf-8"
        match = re.search(r"charset=([A-Za-z0-9_-]+)", response.getheader("Content-Type", ""), re.I)
        if match:
            encoding = match.group(1)
        try:
            text = content.decode(encoding, errors="replace")
        except LookupError:
            text = content.decode("utf-8", errors="replace")
        title = ""
        if content_type == "text/html":
            parser = _VisibleText()
            parser.feed(text)
            text = " ".join(parser.parts)
            title = " ".join(parser.title).strip()
        text = re.sub(r"\s+", " ", text).strip()[:MAX_TEXT_CHARS]
        return {"url": url, "title": title[:400], "content_type": content_type,
                "text": text, "truncated": len(text) >= MAX_TEXT_CHARS,
                "fetched_at": datetime.now(timezone.utc).isoformat(), "untrusted": True}
    except (OSError, ssl.SSLError, socket.timeout) as exc:
        raise ProviderUnavailable("page connection failed") from None
    finally:
        conn.close()
