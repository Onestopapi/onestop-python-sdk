"""Sends the examples' target requests with wreq (Chrome TLS and HTTP/2 fingerprint, one cookie jar) and holds
Chrome's headers for each kind of request."""

from __future__ import annotations

import datetime
import html
import ssl
import sys
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
import wreq
import wreq.blocking

import onestop_antibot as onestop


@dataclass
class Response:
    status: int
    headers: wreq.HeaderMap
    url: str  # final URL, after redirects
    content: bytes

    @property
    def body(self) -> str:
        return self.content.decode("utf-8", "replace")

    def header(self, name: str) -> str:
        """The first value of the named header, or ""."""
        value = self.headers.get(name)
        return "" if value is None else bytes(value).decode("latin-1")

    def resolve(self, ref: str) -> str:
        """A URL found in the body (HTML-escaped, maybe relative) as an absolute URL."""
        return urljoin(self.url, html.unescape(ref))


class Client:
    """Follows redirects. proxy is "" or a proxy URL."""

    def __init__(self, proxy: str) -> None:
        self.jar = wreq.Jar()
        self.follow = True
        options = {
            "emulation": wreq.Emulation(profile=wreq.Profile.Chrome154, platform=wreq.Platform.Windows, headers=False),
            "cookie_provider": self.jar,
            "redirect": wreq.redirect.Policy.limited(10),
            "timeout": datetime.timedelta(seconds=30),
        }
        if proxy:
            options["proxies"] = [wreq.Proxy.all(proxy)]
        self.client = wreq.blocking.Client(**options)

    def get(self, url: str, headers: Headers) -> Response:
        return self.do("GET", url, headers, "")

    def post(self, url: str, headers: Headers, body: str | bytes) -> Response:
        return self.do("POST", url, headers, body)

    def do(self, method: str, url: str, headers: Headers, body: str | bytes) -> Response:
        """Sends one request with the headers in the given order, content-length first and cookie right after
        accept-language. Headers with an empty value are left out. A transport error ends the program."""
        sent = [(name, value) for name, value in headers if value]
        order = ["content-length"]
        for name, _ in sent:
            order.append(name)
            if name == "accept-language":
                order.append("cookie")
        options = {"headers": dict(sent), "orig_headers": order, "default_headers": False}
        if not self.follow:
            options["redirect"] = wreq.redirect.Policy.none()
        if method != "GET":
            options["body"] = body
        try:
            res = self.client.request(getattr(wreq.Method, method), url, **options)
            content = bytes(res.bytes())
        except Exception as e:
            sys.exit(f"FAIL {method} {url}: {e}")
        status = res.status.as_int()
        print(method, url, status)
        return Response(status, res.headers, res.url, content)

    def follow_redirects(self, follow: bool) -> None:
        """Turns redirect following on or off for later requests."""
        self.follow = follow

    def cookie(self, url: str, *names: str) -> str:
        """The first of the named Path=/ cookies the jar would send to url, or ""."""
        labels = urlsplit(url).hostname.split(".")
        for name in names:
            for i in range(len(labels) - 1):
                c = self.jar.get(name, "https://" + ".".join(labels[i:]) + "/")
                if c:
                    return c.value
        return ""

    def set_cookie(self, domain: str, name: str, value: str) -> None:
        """Stores a cookie for domain and its subdomains."""
        self.jar.add(wreq.Cookie(name, value, domain=domain, path="/"), "https://" + domain.lstrip(".") + "/")


def ip_client(proxy: str) -> httpx.Client:
    """The httpx client for onestop.Client.get_ip, through the same proxy, so the API sees the IP the target sees."""
    return httpx.Client(proxy=proxy or None, verify=ssl.create_default_context())


# Chrome 154 on Windows. Every header set below is in Chrome's order.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
_SEC_CH_UA = '"Chromium";v="154", "Google Chrome";v="154", "Not A(Brand";v="99"'
_SEC_CH_UA_FULL = '"Chromium";v="154.0.8037.58", "Google Chrome";v="154.0.8037.58", "Not A(Brand";v="99.0.0.0"'
_SEC_CH_UA_VERSION = '"154.0.8037.58"'
_PLATFORM = '"Windows"'
_ACCEPT_DOCUMENT = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
_ACCEPT_IMAGE = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
_ACCEPT_ENCODING = "gzip, deflate, br, zstd"


class Headers(list):
    """(name, value) pairs, sent in this order."""

    def no_cache(self) -> Headers:
        """Puts pragma and cache-control (no-cache) first."""
        return Headers([("pragma", "no-cache"), ("cache-control", "no-cache"), *self])

    def storage_access(self) -> Headers:
        """Adds sec-fetch-storage-access after sec-fetch-dest, as Chrome sends it for requests to a cross-site
        frame's host."""
        i = [name for name, _ in self].index("sec-fetch-dest") + 1
        return Headers([*self[:i], ("sec-fetch-storage-access", "active"), *self[i:]])

    def with_(self, extra: dict[str, str]) -> Headers:
        """Sets each extra header: a name already here keeps its place, new names follow in name order."""
        out = Headers(self)
        for name in sorted(extra):
            names = [n for n, _ in out]
            if name.lower() in names:
                out[names.index(name.lower())] = (name.lower(), extra[name])
            else:
                out.append((name.lower(), extra[name]))
        return out


def navigate(accept_language: str, referer: str) -> Headers:
    """A top-level page load: referer "" for a typed URL, else a same-origin link."""
    return Headers([
        ("sec-ch-ua", _SEC_CH_UA),
        ("sec-ch-ua-mobile", "?0"),
        ("sec-ch-ua-platform", _PLATFORM),
        ("upgrade-insecure-requests", "1"),
        ("user-agent", USER_AGENT),
        ("accept", _ACCEPT_DOCUMENT),
        ("sec-fetch-site", "same-origin" if referer else "none"),
        ("sec-fetch-mode", "navigate"),
        ("sec-fetch-user", "?1"),
        ("sec-fetch-dest", "document"),
        ("referer", referer),
        ("accept-encoding", _ACCEPT_ENCODING),
        ("accept-language", accept_language),
        ("priority", "u=0, i"),
    ])


def frame(accept_language: str, site: str, referer: str) -> Headers:
    """An iframe document load."""
    return Headers([
        ("sec-ch-ua", _SEC_CH_UA),
        ("sec-ch-ua-mobile", "?0"),
        ("sec-ch-ua-platform", _PLATFORM),
        ("upgrade-insecure-requests", "1"),
        ("user-agent", USER_AGENT),
        ("accept", _ACCEPT_DOCUMENT),
        ("sec-fetch-site", site),
        ("sec-fetch-mode", "navigate"),
        ("sec-fetch-dest", "iframe"),
        ("referer", referer),
        ("accept-encoding", _ACCEPT_ENCODING),
        ("accept-language", accept_language),
        ("priority", "u=0, i"),
    ])


def script(accept_language: str, site: str, referer: str) -> Headers:
    """A <script src> load."""
    return Headers([
        ("sec-ch-ua-platform", _PLATFORM),
        ("user-agent", USER_AGENT),
        ("sec-ch-ua", _SEC_CH_UA),
        ("sec-ch-ua-mobile", "?0"),
        ("accept", "*/*"),
        ("sec-fetch-site", site),
        ("sec-fetch-mode", "no-cors"),
        ("sec-fetch-dest", "script"),
        ("referer", referer),
        ("accept-encoding", _ACCEPT_ENCODING),
        ("accept-language", accept_language),
        ("priority", "u=1"),
    ])


def post(accept_language: str, content_type: str, origin: str, referer: str) -> Headers:
    """A same-origin fetch from the page; a GET fetch has no origin."""
    return Headers([
        ("sec-ch-ua-platform", _PLATFORM),
        ("user-agent", USER_AGENT),
        ("sec-ch-ua", _SEC_CH_UA),
        ("content-type", content_type),
        ("sec-ch-ua-mobile", "?0"),
        ("accept", "*/*"),
        ("origin", origin),
        ("sec-fetch-site", "same-origin"),
        ("sec-fetch-mode", "cors"),
        ("sec-fetch-dest", "empty"),
        ("referer", referer),
        ("accept-encoding", _ACCEPT_ENCODING),
        ("accept-language", accept_language),
        ("priority", "u=1, i"),
    ])


def image(accept_language: str, origin: str, site: str, referer: str) -> Headers:
    """An <img> load; with an origin it is a CORS image."""
    return Headers([
        ("origin", origin),
        ("sec-ch-ua-platform", _PLATFORM),
        ("user-agent", USER_AGENT),
        ("sec-ch-ua", _SEC_CH_UA),
        ("sec-ch-ua-mobile", "?0"),
        ("accept", _ACCEPT_IMAGE),
        ("sec-fetch-site", site),
        ("sec-fetch-mode", "cors" if origin else "no-cors"),
        ("sec-fetch-dest", "image"),
        ("referer", referer),
        ("accept-encoding", _ACCEPT_ENCODING),
        ("accept-language", accept_language),
        ("priority", "i"),
    ])


def kasada_mfc(accept_language: str, version: str, referer: str) -> Headers:
    """The mfc fetch; version is x-kpsdk-v from the p.js result."""
    return Headers([
        ("x-kpsdk-v", version),
        ("sec-ch-ua-platform", _PLATFORM),
        ("user-agent", USER_AGENT),
        ("x-kpsdk-h", "01"),
        ("sec-ch-ua", _SEC_CH_UA),
        ("sec-ch-ua-mobile", "?0"),
        ("accept", "*/*"),
        ("sec-fetch-site", "same-origin"),
        ("sec-fetch-mode", "cors"),
        ("sec-fetch-dest", "empty"),
        ("referer", referer),
        ("accept-encoding", _ACCEPT_ENCODING),
        ("accept-language", accept_language),
        ("priority", "u=1, i"),
    ])


def kasada_tl(accept_language: str, kasada: dict[str, str], origin: str, referer: str) -> Headers:
    """The /tl POST with the x-kpsdk-* headers from the API."""
    return Headers([
        ("x-kpsdk-ct", kasada.get("x-kpsdk-ct", "")),
        ("sec-ch-ua-platform", _PLATFORM),
        ("x-kpsdk-dt", kasada.get("x-kpsdk-dt", "")),
        ("sec-ch-ua", _SEC_CH_UA),
        ("x-kpsdk-im", kasada.get("x-kpsdk-im", "")),
        ("sec-ch-ua-mobile", "?0"),
        ("x-kpsdk-v", kasada.get("x-kpsdk-v", "")),
        ("user-agent", USER_AGENT),
        ("content-type", "application/octet-stream"),
        ("accept", "*/*"),
        ("origin", origin),
        ("sec-fetch-site", "same-origin"),
        ("sec-fetch-mode", "cors"),
        ("sec-fetch-dest", "empty"),
        ("referer", referer),
        ("accept-encoding", _ACCEPT_ENCODING),
        ("accept-language", accept_language),
        ("priority", "u=1, i"),
    ]).with_(kasada)


def challenge_script(accept_language: str, referer: str) -> Headers:
    """The Cloudflare challenge script. The challenge page asks for every client hint (Accept-CH), so the full set is
    sent."""
    return Headers([
        ("sec-ch-ua-full-version-list", _SEC_CH_UA_FULL),
        ("sec-ch-ua-platform", _PLATFORM),
        ("sec-ch-ua", _SEC_CH_UA),
        ("sec-ch-ua-bitness", '"64"'),
        ("sec-ch-ua-model", '""'),
        ("sec-ch-ua-mobile", "?0"),
        ("sec-ch-ua-arch", '"x86"'),
        ("sec-ch-ua-full-version", _SEC_CH_UA_VERSION),
        ("user-agent", USER_AGENT),
        ("sec-ch-ua-platform-version", '"19.0.0"'),
        ("accept", "*/*"),
        ("sec-fetch-site", "same-origin"),
        ("sec-fetch-mode", "no-cors"),
        ("sec-fetch-dest", "script"),
        ("referer", referer),
        ("accept-encoding", _ACCEPT_ENCODING),
        ("accept-language", accept_language),
    ])


def cloudflare(r: onestop.CloudflareHttpRequest, accept_language: str, page_url: str, frame_url: str) -> Headers:
    """One request of a Cloudflare step, by its purpose, with the request's own headers (cf-chl, the form's origin and
    referer, and the like) set on top. frame_url is the challenge iframe's URL."""
    page = urlsplit(page_url)
    target = urlsplit(r.url)
    if r.purpose == "form":
        h = Headers([
            ("sec-ch-ua", _SEC_CH_UA),
            ("sec-ch-ua-mobile", "?0"),
            ("sec-ch-ua-full-version", _SEC_CH_UA_VERSION),
            ("sec-ch-ua-arch", '"x86"'),
            ("sec-ch-ua-full-version-list", _SEC_CH_UA_FULL),
            ("sec-ch-ua-platform", _PLATFORM),
            ("sec-ch-ua-platform-version", '"19.0.0"'),
            ("sec-ch-ua-bitness", '"64"'),
            ("sec-ch-ua-model", '""'),
            ("origin", ""),
            ("content-type", "application/x-www-form-urlencoded"),
            ("upgrade-insecure-requests", "1"),
            ("user-agent", USER_AGENT),
            ("referer", ""),
        ])
    elif r.purpose == "iframe":
        h = frame(accept_language, "cross-site", "").storage_access()
    elif r.purpose == "image":
        h = image(accept_language, "", "same-origin", frame_url).storage_access()
    elif r.purpose == "pat":
        h = Headers([
            ("cache-control", "max-age=0"),
            ("sec-ch-ua-platform", _PLATFORM),
            ("user-agent", USER_AGENT),
            ("sec-ch-ua", _SEC_CH_UA),
            ("sec-ch-ua-mobile", "?0"),
            ("accept", "*/*"),
            ("sec-fetch-site", "same-origin"),
            ("sec-fetch-mode", "cors"),
            ("sec-fetch-dest", "empty"),
            ("sec-fetch-storage-access", "active"),
            ("referer", frame_url),
            ("accept-encoding", _ACCEPT_ENCODING),
            ("accept-language", accept_language),
            ("priority", "u=1, i"),
        ])
    elif target.netloc == page.netloc:  # challenge POST from the page
        h = Headers([
            ("sec-ch-ua-full-version-list", _SEC_CH_UA_FULL),
            ("sec-ch-ua-platform", _PLATFORM),
            ("sec-ch-ua", _SEC_CH_UA),
            ("sec-ch-ua-bitness", '"64"'),
            ("cf-chl-ra", "0"),
            ("sec-ch-ua-mobile", "?0"),
            ("sec-ch-ua-model", '""'),
            ("sec-ch-ua-arch", '"x86"'),
            ("sec-ch-ua-full-version", _SEC_CH_UA_VERSION),
            ("user-agent", USER_AGENT),
            ("content-type", "text/plain;charset=UTF-8"),
            ("cf-chl", r.headers.get("cf-chl", "")),
            ("sec-ch-ua-platform-version", '"19.0.0"'),
            ("accept", "*/*"),
            ("origin", f"{page.scheme}://{page.netloc}"),
            ("sec-fetch-site", "same-origin"),
            ("sec-fetch-mode", "cors"),
            ("sec-fetch-dest", "empty"),
            ("referer", page_url),
            ("accept-encoding", _ACCEPT_ENCODING),
            ("accept-language", accept_language),
            ("priority", "u=1, i"),
        ])
    else:  # challenge POST from the challenge iframe
        h = Headers([
            ("sec-ch-ua-platform", _PLATFORM),
            ("user-agent", USER_AGENT),
            ("sec-ch-ua", _SEC_CH_UA),
            ("content-type", "text/plain;charset=UTF-8"),
            ("cf-chl", r.headers.get("cf-chl", "")),
            ("cf-chl-ra", "0"),
            ("sec-ch-ua-mobile", "?0"),
            ("accept", "*/*"),
            ("origin", f"{target.scheme}://{target.netloc}"),
            ("sec-fetch-site", "same-origin"),
            ("sec-fetch-mode", "cors"),
            ("sec-fetch-dest", "empty"),
            ("sec-fetch-storage-access", "active"),
            ("referer", frame_url),
            ("accept-encoding", _ACCEPT_ENCODING),
            ("accept-language", accept_language),
            ("priority", "u=1, i"),
        ])
    return h.with_(r.headers)
