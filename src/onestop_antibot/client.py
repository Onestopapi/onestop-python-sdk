from __future__ import annotations

import json
import time
from typing import Any, Literal

import httpx

from . import _wire
from .errors import OneStopError
from .session import Session

DEFAULT_ENDPOINT = "https://onestopantibot.com/generate"
IP_ENDPOINT = "https://ip.onestopantibot.com/"


def _http_client(**kwargs: Any) -> httpx.Client:
    client = httpx.Client(trust_env=False, **kwargs)
    client.headers.clear()
    return client


class Client:
    """OneStop API client. Reuse one client across threads and calls."""

    def __init__(
        self,
        *,
        api_key: str,
        identifier: str,
        sub_key: str | None = None,
        endpoint: str | None = None,
        compression: Literal["zstd", "gzip", "identity"] = "zstd",
        timeout: float = 60.0,
        http_client: httpx.Client | None = None,
        ip_http_client: httpx.Client | None = None,
        defaults: Session | None = None,
        debug_proxy: str = "",
    ) -> None:
        """``identifier`` is sent as User-Agent; ``timeout`` bounds each whole call in seconds.

        ``debug_proxy`` (e.g. ``http://127.0.0.1:8888``) sends every /generate call through that proxy on the
        SDK's own client (``http_client`` is not used) and accepts its certificate.
        """
        if not (api_key or "").strip() or not (identifier or "").strip():
            raise OneStopError(0, "", "onestop: APIKey and Identifier are required")
        compression = compression or "zstd"
        if compression not in ("zstd", "gzip", "identity"):
            raise OneStopError(0, "", "onestop: compression must be zstd, gzip or identity")
        self._api_key = api_key
        self._identifier = identifier
        self._sub_key = sub_key or ""
        self._endpoint = endpoint or DEFAULT_ENDPOINT
        self._compression = compression
        self._timeout = timeout if timeout > 0 else 60.0
        self._owned: list[httpx.Client] = []
        if http_client is None:
            http_client = _http_client()
            self._owned.append(http_client)
        self._http = http_client
        self._ip_http = ip_http_client or http_client
        if debug_proxy:
            try:
                self._http = _http_client(proxy=debug_proxy, verify=False)
            except (ValueError, httpx.InvalidURL) as e:
                raise OneStopError(0, "", f"onestop: request: {e}") from None
            self._owned.append(self._http)
        self._defaults = defaults or Session()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close HTTP connections the SDK opened."""
        for client in self._owned:
            client.close()

    def session(
        self,
        *,
        site: str = "",
        referer: str = "",
        user_agent: str = "",
        accept_language: str = "",
        ip: str = "",
    ) -> Session:
        """Non-empty values override the client defaults."""
        d = self._defaults
        session = Session(
            site=site or d.site,
            referer=referer or d.referer,
            user_agent=user_agent or d.user_agent,
            accept_language=accept_language or d.accept_language,
            ip=ip or d.ip,
        )
        object.__setattr__(session, "_client", self)
        return session

    def get_ip(self) -> str:
        """Return the public IP seen by ip.onestopantibot.com through ``ip_http_client``."""
        http = self._ip_http
        try:
            request = http.build_request("GET", IP_ENDPOINT, headers=self._auth_headers(), timeout=self._timeout)
            response = http.send(request, stream=True)
        except httpx.HTTPError as e:
            raise OneStopError(0, "", f"onestop: request: {str(e) or type(e).__name__}") from None
        try:
            if response.status_code != 200:
                raise OneStopError(response.status_code, "", "IP lookup failed")
            body = response.read()
        except httpx.HTTPError as e:
            raise OneStopError(0, "", f"onestop: read response: {str(e) or type(e).__name__}") from None
        finally:
            response.close()
        return body.decode("utf-8", "replace").strip()

    def _auth_headers(self) -> dict[str, str | bytes]:
        headers: dict[str, str | bytes] = {"x-key": self._api_key.encode(), "User-Agent": self._identifier.encode()}
        if self._sub_key:
            headers["x-sub-key"] = self._sub_key.encode()
        return headers

    def _generate(self, mode: str, body: dict[str, Any], key: str) -> Any:
        try:
            data = _wire.encode(body, self._compression)
        except (TypeError, ValueError) as e:
            raise OneStopError(0, "", f"onestop: encode request: {e}") from None
        headers = self._auth_headers()
        headers["Content-Type"] = "application/json; charset=utf-8"
        if self._compression != "identity":
            headers["Content-Encoding"] = self._compression
        headers["Accept-Encoding"] = "zstd, gzip"
        headers["x-mode"] = mode
        http = self._http
        deadline = time.monotonic() + self._timeout
        try:
            request = http.build_request("POST", self._endpoint, content=data, headers=headers, timeout=self._timeout)
            response = http.send(request, stream=True)
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            raise OneStopError(0, "", f"onestop: request: {str(e) or type(e).__name__}") from None
        status = response.status_code
        request_id = response.headers.get("RequestID", "")
        raw_encoding = response.headers.get("Content-Encoding", "")
        encoding = raw_encoding.strip().lower()
        try:
            if encoding not in ("", "identity", "gzip", "zstd"):
                message = json.dumps(raw_encoding, ensure_ascii=False)
                raise OneStopError(0, "", f"onestop: unsupported response compression {message}")
            raw = bytearray()
            for chunk in response.iter_raw():
                raw += chunk
                if time.monotonic() > deadline:
                    raise OneStopError(0, "", f"onestop: read response: timeout after {self._timeout:g}s")
        except httpx.HTTPError as e:
            raise OneStopError(0, "", f"onestop: read response: {str(e) or type(e).__name__}") from None
        finally:
            response.close()
        data = _wire.decompress(encoding, bytes(raw))
        try:
            success, error, result = _wire.parse(data, key)
        except ValueError:
            raise OneStopError(status, request_id, "invalid JSON response") from None
        if status != 200 or not success or error:
            raise OneStopError(status, request_id, error or "request failed")
        result.request_id = request_id
        if result.sleep > 0:
            time.sleep(result.sleep / 1000)
        return result
