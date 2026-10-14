import time
from dataclasses import dataclass, field
from typing import Any, TypedDict

from .kasada import kasada_cd_header


class CloudflareCall(TypedDict, total=False):
    """Keyword arguments of the Cloudflare methods.

    ``response`` is the raw target response: a str, a JSON value, or bytes holding raw JSON.
    ``image_height``, ``image_width`` and ``pat_status`` send an explicit 0; ``None`` omits them.
    """

    html: str
    script: str
    script_url: str
    response: Any
    context: str
    ray_id: str
    bytecode_ray_id: str
    iframe_url: str
    image_height: int | None
    image_width: int | None
    pat_status: int | None
    action: str
    c_data: str


@dataclass
class AkamaiResponse:
    """Akamai sensor, Pixel or BMP result."""

    payload: str = ""
    context: str = ""
    sleep: int = 0
    request_id: str = ""


PixelResponse = AkamaiResponse
BmpResponse = AkamaiResponse


@dataclass
class SbsdResponse:
    payload: str = ""
    context: str = ""
    sleep: int = 0
    request_id: str = ""


@dataclass
class DatadomeResponse:
    """DataDome result: encoded payload and context."""

    payload: str = ""
    context: str = ""
    sleep: int = 0
    request_id: str = ""


DatadomeTagsResponse = DatadomeResponse
DatadomeInterstitialResponse = DatadomeResponse
DatadomeSliderResponse = DatadomeResponse


@dataclass
class KasadaPScriptResponse:
    """Values extracted from p.js."""

    version: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    difficulty: int = 0
    subchallenge_count: int = 0
    seed_suffix: str = ""
    crypto_customer_key: str = ""
    cache_lifetime_seconds: int = 0
    sleep: int = 0
    request_id: str = ""

    def cd_header(self, ct: str, st: int) -> str:
        """Build the desktop x-kpsdk-cd header from the /tl response's ``x-kpsdk-ct`` and ``x-kpsdk-st`` (ms)."""
        return kasada_cd_header(
            st=st,
            rst=max(time.time_ns() // 1_000_000, st),
            ct=ct,
            crypto_customer_key=self.crypto_customer_key,
            seed_suffix=self.seed_suffix,
            difficulty=self.difficulty,
            subchallenge_count=self.subchallenge_count,
        )


@dataclass
class KasadaResponse:
    """Kasada TL result: base64 payload and HTTP headers."""

    payload: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    sleep: int = 0
    request_id: str = ""


@dataclass
class CloudflareHttpRequest:
    """A target request to send; ``purpose`` is challenge, iframe, image, pat or form."""

    purpose: str = ""
    method: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""


@dataclass
class CloudflareResponse:
    """Target requests for one challenge step, the next context and, once solved, the token."""

    requests: list[CloudflareHttpRequest] = field(default_factory=list)
    token: str = ""
    context: str = ""
    sleep: int = 0
    request_id: str = ""
