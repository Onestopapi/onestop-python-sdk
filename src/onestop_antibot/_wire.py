import gzip
import json
import sys
import zlib
from collections.abc import Mapping
from typing import Any, Callable

import zstandard

from .errors import OneStopError
from .types import (
    AkamaiResponse,
    CloudflareHttpRequest,
    CloudflareResponse,
    DatadomeResponse,
    KasadaPScriptResponse,
    KasadaResponse,
    SbsdResponse,
)

if sys.version_info >= (3, 11):
    from typing import NotRequired, TypedDict
else:
    from typing_extensions import NotRequired, TypedDict


class Identity(TypedDict):
    site: NotRequired[str]
    userAgent: NotRequired[str]
    referer: NotRequired[str]
    acceptLanguage: NotRequired[str]
    ip: NotRequired[str]


class DatadomeIdentity(TypedDict):
    site: NotRequired[str]
    userAgent: NotRequired[str]
    acceptLanguage: NotRequired[str]
    ip: NotRequired[str]
    referer: NotRequired[str]


class RefererIdentity(TypedDict):
    referer: NotRequired[str]
    site: NotRequired[str]
    userAgent: NotRequired[str]
    acceptLanguage: NotRequired[str]
    ip: NotRequired[str]


class AkamaiWire(TypedDict):
    referer: NotRequired[str]
    site: NotRequired[str]
    abck: str
    bmsz: str
    userAgent: NotRequired[str]
    acceptLanguage: NotRequired[str]
    ip: NotRequired[str]
    script: NotRequired[str]
    scriptUrl: str
    context: NotRequired[str]


class SbsdWire(RefererIdentity):
    uuid: str
    sbsdCookie: str
    script: NotRequired[str]
    mode: str
    context: NotRequired[str]


class PixelWire(Identity):
    html: str
    script: str
    context: NotRequired[str]


class BmpWire(TypedDict):
    bundleId: str
    version: str
    device: str
    nonce: NotRequired[str]
    checksum: NotRequired[str]
    serverSideSignal: NotRequired[str]
    token: NotRequired[str]
    difficulty: NotRequired[int | None]
    iosVersion: NotRequired[str]
    uuid: NotRequired[str]
    realValues: NotRequired[dict[str, str] | None]
    script: NotRequired[str]


class DatadomeTagsWire(DatadomeIdentity):
    event: str
    siteKey: str
    version: str
    cookie: str
    context: NotRequired[str]


class DatadomeInterstitialWire(DatadomeIdentity):
    script: str
    html: str
    pageResponse: str
    context: NotRequired[str]


class DatadomeSliderWire(DatadomeIdentity):
    script: str
    html: str
    pageResponse: str
    backgroundImage: str
    puzzlePiece: str
    context: NotRequired[str]


class CloudflareWire(Identity):
    html: NotRequired[str]
    script: NotRequired[str]
    scriptUrl: NotRequired[str]
    response: NotRequired[Any]
    context: NotRequired[str]
    rayId: NotRequired[str]
    bytecodeRayId: NotRequired[str]
    iframeUrl: NotRequired[str]
    imageHeight: NotRequired[int | None]
    imageWidth: NotRequired[int | None]
    patStatus: NotRequired[int | None]
    action: NotRequired[str]
    cData: NotRequired[str]


class KasadaPScriptWire(TypedDict):
    referer: str
    site: str
    userAgent: str
    acceptLanguage: str
    ip: str
    script: str


class KasadaTlWire(RefererIdentity):
    ipsUrl: str
    script: str


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, (str, dict)) and not value)


def body(kind: type, request: Mapping[str, Any], keep: tuple[str, ...] = ()) -> dict[str, Any]:
    """``request`` in ``kind``'s field order; empty ``NotRequired`` fields are left out."""
    required = kind.__required_keys__  # type: ignore[attr-defined]
    return {
        key: request[key] for key in kind.__annotations__ if key in required or key in keep or not _empty(request[key])
    }


def encode(body: dict[str, Any], compression: str) -> bytes:
    text = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    data = (text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029") + "\n").encode()
    if compression == "zstd":
        return zstandard.ZstdCompressor(level=7, write_checksum=True).compress(data)
    if compression == "gzip":
        return gzip.compress(data, compresslevel=6, mtime=0)
    return data


def decompress(encoding: str, raw: bytes) -> bytes:
    try:
        if encoding == "gzip":
            return gzip.decompress(raw)
        if encoding == "zstd":
            return zstandard.ZstdDecompressor().stream_reader(raw, read_across_frames=True).read()
    except (EOFError, OSError, zlib.error, zstandard.ZstdError) as e:
        raise OneStopError(0, "", f"onestop: decompress response: {e}") from None
    return raw


def _get(obj: dict[str, Any], name: str) -> Any:
    value = None
    folded = name.lower()
    for key, item in obj.items():
        if key == name or key.lower() == folded:
            value = item
    return value


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise ValueError


def _int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int) and not isinstance(value, bool) and -(1 << 63) <= value < (1 << 63):
        return value
    raise ValueError


def _bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    raise ValueError


def _obj(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise ValueError


def _map(value: Any) -> dict[str, str]:
    return {key: _str(item) for key, item in _obj(value).items()}


def _sleep(o: dict[str, Any]) -> int:
    return _int(_get(o, "sleep"))


def _akamai(o: dict[str, Any]) -> AkamaiResponse:
    return AkamaiResponse(payload=_str(_get(o, "payload")), context=_str(_get(o, "context")), sleep=_sleep(o))


def _sbsd(o: dict[str, Any]) -> SbsdResponse:
    return SbsdResponse(payload=_str(_get(o, "payload")), context=_str(_get(o, "context")), sleep=_sleep(o))


def _datadome(o: dict[str, Any]) -> DatadomeResponse:
    return DatadomeResponse(payload=_str(_get(o, "payload")), context=_str(_get(o, "context")), sleep=_sleep(o))


def _pscript(o: dict[str, Any]) -> KasadaPScriptResponse:
    return KasadaPScriptResponse(
        version=_str(_get(o, "version")),
        headers=_map(_get(o, "headers")),
        difficulty=_int(_get(o, "difficulty")),
        subchallenge_count=_int(_get(o, "subchallengeCount")),
        seed_suffix=_str(_get(o, "seedSuffix")),
        crypto_customer_key=_str(_get(o, "cryptoCustomerKey")),
        cache_lifetime_seconds=_int(_get(o, "cacheLifetimeSeconds")),
        sleep=_sleep(o),
    )


def _kasada(o: dict[str, Any]) -> KasadaResponse:
    return KasadaResponse(payload=_str(_get(o, "payload")), headers=_map(_get(o, "headers")), sleep=_sleep(o))


def _cf_request(o: dict[str, Any]) -> CloudflareHttpRequest:
    return CloudflareHttpRequest(
        purpose=_str(_get(o, "purpose")),
        method=_str(_get(o, "method")),
        url=_str(_get(o, "url")),
        headers=_map(_get(o, "headers")),
        body=_str(_get(o, "body")),
    )


def _requests(value: Any) -> list[CloudflareHttpRequest]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError
    return [_cf_request(_obj(item)) for item in value]


def _cloudflare(o: dict[str, Any]) -> CloudflareResponse:
    return CloudflareResponse(
        requests=_requests(_get(o, "requests")),
        token=_str(_get(o, "token")),
        context=_str(_get(o, "context")),
        sleep=_sleep(o),
    )


SECTIONS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "akamaiResponse": _akamai,
    "sbsdResponse": _sbsd,
    "pixelResponse": _akamai,
    "bmpResponse": _akamai,
    "datadomeTagsResponse": _datadome,
    "datadomeInterstitialResponse": _datadome,
    "datadomeSliderResponse": _datadome,
    "kasadaPscriptResponse": _pscript,
    "kasadaResponse": _kasada,
    "cloudflareResponse": _cloudflare,
}


def _reject_constant(name: str) -> Any:
    raise ValueError(name)


def parse(data: bytes, key: str) -> tuple[bool, str, Any]:
    top = _obj(json.loads(data.decode("utf-8", "replace"), parse_constant=_reject_constant))
    success = _bool(_get(top, "success"))
    error = _str(_get(top, "error"))
    return success, error, SECTIONS[key](_obj(top.get(key)))
