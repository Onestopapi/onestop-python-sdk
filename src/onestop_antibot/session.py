from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import _wire
from .errors import OneStopError
from .types import (
    AkamaiResponse,
    CloudflareCall,
    CloudflareResponse,
    DatadomeResponse,
    KasadaPScriptResponse,
    KasadaResponse,
    SbsdResponse,
)

if TYPE_CHECKING:
    from typing_extensions import Unpack

    from .client import Client


def _sorted(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sorted(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sorted(item) for item in value]
    return value


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


@dataclass(frozen=True, kw_only=True)
class Session:
    """Browser identity for challenge calls. Create it with ``Client.session``; an unbound one only serves as client defaults.

    Every result's ``sleep`` is the wait in ms the API asked for; the SDK has already waited it before returning.
    """

    site: str = ""
    referer: str = ""
    user_agent: str = ""
    accept_language: str = ""
    ip: str = ""
    _client: Client | None = field(default=None, init=False, repr=False, compare=False)

    def _identity(self) -> _wire.Identity:
        return _wire.Identity(
            site=self.site,
            userAgent=self.user_agent,
            referer=self.referer,
            acceptLanguage=self.accept_language,
            ip=self.ip,
        )

    def _call(
        self, mode: str, provider: str, request: Mapping[str, Any], kind: type, keep: tuple[str, ...] = ()
    ) -> Any:
        if self._client is None:
            raise OneStopError(0, "", "onestop: use Client.session(...) before challenge calls")
        body = _wire.body(kind, request, keep)
        return self._client._generate(mode, {provider + "Request": body}, provider + "Response")

    def akamai_sensor(
        self, *, abck: str = "", bmsz: str = "", script: str = "", script_url: str = "", context: str = ""
    ) -> AkamaiResponse:
        """Send ``script`` on the first call and ``context``, without ``script``, on every later call."""
        request = _wire.AkamaiWire(
            referer=self.referer,
            site=self.site,
            abck=abck,
            bmsz=bmsz,
            userAgent=self.user_agent,
            acceptLanguage=self.accept_language,
            ip=self.ip,
            script=script,
            scriptUrl=script_url,
            context=context,
        )
        return self._call("Akamai", "akamai", request, _wire.AkamaiWire)

    def sbsd_payload(
        self, *, uuid: str = "", sbsd_cookie: str = "", script: str = "", mode: str = "", context: str = ""
    ) -> SbsdResponse:
        """``mode`` is ``f`` (fingerprint, with ``script``) or ``t`` (event, with ``context``)."""
        request = _wire.SbsdWire(
            **self._identity(), uuid=uuid, sbsdCookie=sbsd_cookie, script=script, mode=mode, context=context
        )
        return self._call("Sbsd", "sbsd", request, _wire.SbsdWire)

    def pixel(self, *, html: str = "", script: str = "", context: str = "") -> AkamaiResponse:
        """``payload`` is the complete form body for the Pixel POST."""
        request = _wire.PixelWire(**self._identity(), html=html, script=script, context=context)
        return self._call("Akamai", "pixel", request, _wire.PixelWire)

    def bmp(
        self,
        *,
        bundle_id: str = "",
        version: str = "",
        device: str = "",
        nonce: str = "",
        checksum: str = "",
        server_side_signal: str = "",
        token: str = "",
        difficulty: int | None = None,
        ios_version: str = "",
        uuid: str = "",
        real_values: dict[str, str] | None = None,
        script: str = "",
    ) -> AkamaiResponse:
        """Generate Akamai BMP (mobile SDK) data. Session identity is not sent."""
        request = _wire.BmpWire(
            bundleId=bundle_id,
            version=version,
            device=device,
            nonce=nonce,
            checksum=checksum,
            serverSideSignal=server_side_signal,
            token=token,
            difficulty=difficulty,
            iosVersion=ios_version,
            uuid=uuid,
            realValues=_sorted(real_values),
            script=script,
        )
        return self._call("Akamai", "bmp", request, _wire.BmpWire)

    def datadome_tags(
        self,
        *,
        event: str = "",
        site_key: str = "",
        version: str = "",
        cookie: str = "",
        context: str = "",
    ) -> DatadomeResponse:
        """``event`` is ``ch`` or ``le``."""
        request = _wire.DatadomeTagsWire(
            **self._identity(), event=event, siteKey=site_key, version=version, cookie=cookie, context=context
        )
        return self._call("DatadomeTags", "datadomeTags", request, _wire.DatadomeTagsWire)

    def datadome_interstitial(
        self,
        *,
        script: str = "",
        html: str = "",
        page_response: str = "",
        context: str = "",
    ) -> DatadomeResponse:
        request = _wire.DatadomeInterstitialWire(
            **self._identity(), script=script, html=html, pageResponse=page_response, context=context
        )
        return self._call("DatadomeInterstitial", "datadomeInterstitial", request, _wire.DatadomeInterstitialWire)

    def datadome_slider(
        self,
        *,
        script: str = "",
        html: str = "",
        page_response: str = "",
        background_image: str = "",
        puzzle_piece: str = "",
        context: str = "",
    ) -> DatadomeResponse:
        """``background_image`` and ``puzzle_piece`` are base64; ``payload`` is the check request's query string."""
        request = _wire.DatadomeSliderWire(
            **self._identity(),
            script=script,
            html=html,
            pageResponse=page_response,
            backgroundImage=background_image,
            puzzlePiece=puzzle_piece,
            context=context,
        )
        return self._call("DatadomeSlider", "datadomeSlider", request, _wire.DatadomeSliderWire)

    def cloudflare_step(self, **call: Unpack[CloudflareCall]) -> CloudflareResponse:
        """Run one Cloudflare step; the API detects the challenge type."""
        return self._cloudflare("Cloudflare", **call)

    def cloudflare_turnstile(self, **call: Unpack[CloudflareCall]) -> CloudflareResponse:
        return self._cloudflare("CloudflareTurnstile", **call)

    def cloudflare_waf(self, **call: Unpack[CloudflareCall]) -> CloudflareResponse:
        return self._cloudflare("CloudflareWaf", **call)

    def cloudflare_jsd(self, **call: Unpack[CloudflareCall]) -> CloudflareResponse:
        return self._cloudflare("CloudflareJsd", **call)

    def cloudflare_precursor(self, **call: Unpack[CloudflareCall]) -> CloudflareResponse:
        return self._cloudflare("CloudflarePrecursor", **call)

    def _cloudflare(self, mode: str, **call: Any) -> CloudflareResponse:
        unknown = call.keys() - CloudflareCall.__annotations__.keys()
        if unknown:
            raise TypeError(f"unexpected keyword argument {min(unknown)!r}")
        if isinstance(call.get("response"), (bytes, bytearray)):
            try:
                call["response"] = json.loads(call["response"])
            except ValueError as e:
                raise OneStopError(0, "", f"onestop: encode request: {e}") from None
        fields = {_camel(name): _sorted(call.get(name)) for name in CloudflareCall.__annotations__}
        request = _wire.CloudflareWire(**self._identity(), **fields)
        keep = () if call.get("response") is None else ("response",)
        return self._call(mode, "cloudflare", request, _wire.CloudflareWire, keep)

    def kasada_pscript(self, script: str) -> KasadaPScriptResponse:
        """Extract version and crypto inputs from raw p.js."""
        request = _wire.KasadaPScriptWire(**self._identity(), script=script)
        return self._call("Kasada", "kasadaPscript", request, _wire.KasadaPScriptWire)

    def kasada_tl(self, script_url: str, script: str) -> KasadaResponse:
        """Generate the Kasada /tl body (base64) and headers from the ips.js URL and source."""
        request = _wire.KasadaTlWire(**self._identity(), ipsUrl=script_url, script=script)
        return self._call("Kasada", "kasada", request, _wire.KasadaTlWire)
