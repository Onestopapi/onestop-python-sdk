# AGENTS.md

Guidance for AI coding assistants using the OneStop Antibot SDK. Working programs for the main flows are in `examples/`; copy their flow.

## Rules

1. **Headers and header order matter.** Send exactly the headers a real browser sends for each request type (page, script, XHR/POST), in the same order. Don't let your HTTP client add, drop or reorder headers. The examples show the order for each request (`examples/<client>/httpclient.py`).
2. **Match the site's region.** Use a proxy in the site's country and an `accept_language` for that country, the way an ordinary visitor would. A `.de` site gets a German proxy and `de-DE,de;q=0.9`.
3. **`sec-ch-ua` headers must be accurate.** When you present as Chromium, `sec-ch-ua`, `sec-ch-ua-mobile`, `sec-ch-ua-platform` (and the full-version hints when sent) must match the User-Agent's browser, version and platform exactly.
4. **One identity per session.** Create one `client.session(...)` per browser identity. Use the same `user_agent`, `accept_language`, `site` and `referer` for every call in it. Set `ip` to the proxy's exit IP (`client.get_ip()` with `ip_http_client` going through the same proxy).
5. **Pass context back.** Send the `context` from the previous response on the next call of the same flow, and never share it across sessions. Akamai sends the `script` only on the first call. DataDome uses one context for tags, interstitial and slider in the same session.
6. **Use a TLS client that impersonates the browser** (as in `examples/`). A default HTTP client's TLS/HTTP2 fingerprint gets blocked.
7. **Errors fail loud.** Don't retry blindly or invent fallback values. Log the error, including its `request_id` (`onestop.OneStopError`), which support needs.
8. **Some sites (DataDome, Akamai) are strict on flow.** Make the requests a real browser makes, in order; you may need extra requests beyond the solve. Put your site's own requests in `site_firewall` in the examples.

## API reference

You fetch the site's pages and scripts yourself, send them to the API, and send the payload you get back to the site yourself. The API never contacts the site. Names below are this SDK's names. Working programs are in `examples/<client>/` (clients: `curl_cffi`, `tls_client`, `wreq`). Each client folder has the HTTP request wrapper `httpclient` (`examples/<client>/httpclient.py`), which sends every request with Chrome's headers in order. In each example the `main()` function runs the flow, one function per step, and ends with `site_firewall`, the place for your own requests to the site. A product without an `Example:` line has none yet.

### Setup

Client: `client = onestop.Client(api_key=..., identifier=..., ...)` (`import onestop_antibot as onestop`). One per app, safe for concurrent calls.

| Config | Value |
|---|---|
| `api_key` | Required. Your key (dashboard Settings > Keys), sent as `x-key`. With a program, the program's key. |
| `identifier` | Required. Your identifier or account name, sent as the API `User-Agent`. Not the browser's user agent. |
| `sub_key` | Optional. The member's own key, sent as `x-sub-key`. Only with a program key. |
| `ip_http_client` | An `httpx.Client` through your target proxy. `client.get_ip()` uses it and returns the proxy's exit IP, the address the site sees. |
| `debug_proxy` | Optional proxy URL such as `http://127.0.0.1:8888`. API calls go through it on the SDK's own connection and its certificate is accepted. `get_ip` is not affected. |

Also optional: `endpoint`, `compression` (`zstd` default, `gzip`, `identity`), `timeout` (seconds per call, default 60), `http_client` (API transport), `defaults` (session values merged into every session).

Session: `session = client.session(site=..., referer=..., user_agent=..., accept_language=..., ip=...)` (product methods take their fields as keyword arguments). One per browser identity. Every call sends these; keep them the same for the whole session.

| Session | Value from |
|---|---|
| `site` | The page URL, after redirects. |
| `referer` | The page's referer. The page URL for a direct visit. |
| `user_agent` | The browser user agent you send to the site. |
| `accept_language` | The `Accept-Language` you send to the site, for the proxy's country. |
| `ip` | `client.get_ip()` with `ip_http_client` set. |

Scripts, HTML and cookies go in exactly as the site sent them. Don't base64 or re-escape them (only the DataDome slider images are base64).

Errors: methods raise `onestop.OneStopError`, with `status_code`, `request_id` and `message`. `str(e)` reads `onestop: HTTP <status> (<request_id>): <message>`, or `onestop: HTTP <status>: <message>` when there is no request ID. Network and local errors have `status_code` 0 and the full reason in `message`; their text is just that message. The SDK never retries.

| Status | Meaning |
|---|---|
| 400 | Bad input. The message names the field. |
| 401 | Refused: wrong or missing key, service not enabled for the key, IP not on your allowlist, no balance, spending cap or rate limit. |
| 500 | Generation failed. Report it with the request ID. |
| 503 | Busy or restarting. Retry after a short wait. |

Every API result has `request_id`; the local helpers (sec-cpt and the Kasada CD header) return a plain string. Put the request ID in any report. Only a successful call is charged; Cloudflare charges once per solved challenge, not per step.

Every API result also has `sleep`: a wait in milliseconds, 0 when there is none. The SDK waits it before the call returns, so don't wait it again. Browser-like pauses between your own site requests, as some examples make, are separate and fine.

Context: most results return `context`. Send it back unchanged on the next call of the same flow. Never send it to another session or another product.

### Akamai

#### Akamai sensor

`session.akamai_sensor(...)` returns `onestop.AkamaiResponse`.

1. GET the page. The sensor script is the `<script type="text/javascript" src="...">` whose `src` is a bare path: letters, digits, `/`, `-` and `_`, no dots or query. GET it.
2. First call: `abck`, `bmsz`, `script_url`, `script`. No `context`.
3. POST `{"sensor_data": payload}` to the script URL as `text/plain;charset=UTF-8`. The site sets a new `_abck`.
4. Every later call: fresh `abck` and `bmsz`, `script_url`, and `context` from the last response. No `script`.
5. Repeat until `_abck` contains `~0~` or the POST reply is the 17-byte `{"success": true}`. Some sites keep `~-1~`; there the protected request passing is the proof.
6. A later request can reset `_abck`. Then send one more sensor with the saved `context` and fresh cookies, and POST it.

If the page also loads an SBSD script (`?v=`), run SBSD passive first, in the same session.

| Field | When | Value from |
|---|---|---|
| `abck` | Every call | The `_abck` cookie, read fresh before each call. |
| `bmsz` | Every call | The `bm_sz` cookie, read fresh before each call. |
| `script_url` | Every call | The sensor script's full URL. |
| `script` | First call | The sensor script's source. |
| `context` | Later calls | `context` from the previous sensor response. |

Returns `payload` (POST it as `sensor_data`) and `context` (send it on the next sensor call, in place of the script).

Context: one chain per sensor flow, sensor calls only.

Example: `examples/<client>/akamai.py` (SBSD passive, then the sensor loop).

#### SBSD (block and passive)

`session.sbsd_payload(...)` returns `onestop.SbsdResponse`.

The SBSD script is the `<script src="...?v=...">` on the page (it can carry a `nonce`). HTML-unescape its URL (`&amp;` to `&`) and resolve it against the page URL. A block page has `t=` on that URL, or holds `{"cpr_chlge":"true","t":"..."}`. Otherwise it is passive.

Block:

1. GET the page and find the SBSD script. The token is the script URL's `t=`, else `t` from the `cpr_chlge` marker.
2. GET the script. Call once: `mode` `f`, `script`, no `context`.
3. POST `{"body": payload}` as `application/json` to the script path plus `?t=<token>`.
4. Read `bm_sc` straight away: `2~` passed, `3~` failed.
5. GET the page again. It is now the real page: run passive on its new script, in the same session.

Passive:

1. GET the page, find the SBSD script (only `?v=`), GET it.
2. Mode `f`: `script`, no `context`. POST `{"body": payload}` as `application/json` to the script path, no query.
3. Mode `t`: `context` from the f response, no `script`. POST it the same way.
4. Both POSTs answer 200. No verdict cookie comes back.

| Field | When | Value from |
|---|---|---|
| `uuid` | Every call | The `v=` value of the SBSD script URL. |
| `sbsd_cookie` | Every call | The `bm_so` cookie (`sbsd_o` on sites that use that name), read fresh before each call. |
| `mode` | Every call | Block: `f`. Passive: `f`, then `t`. |
| `script` | Mode `f` | The SBSD script's source. |
| `context` | Passive mode `t` | `context` from the f response. |

Returns `payload` (POST it as `{"body": payload}`) and `context` (passive: send it on the t call; block: not needed). The block token is not an API field; it only goes on your POST URL.

Context: the f context goes only to the t call for the same script. The block takes one call and no context.

Example: `examples/<client>/sbsd.py` (block, then passive), `examples/<client>/akamai.py` (passive).

#### Pixel

`session.pixel(...)` returns `onestop.AkamaiResponse`.

1. GET the page. The Pixel script is the `<script src>` at `/akam/13/<key>` (not the one starting `pixel_`). GET it.
2. Call with the page HTML and the script, unchanged.
3. POST `payload` to `/akam/13/pixel_<key>` as `application/x-www-form-urlencoded`.

| Field | When | Value from |
|---|---|---|
| `html` | Every call | The page HTML, unchanged. The API reads the Pixel values from it and the script. |
| `script` | Every call | The Pixel script's source, unchanged. |
| `context` | If returned | `context` from the previous Pixel response, when it had one. |

Returns `payload` (the whole form body, already encoded; POST it as is) and `context` (usually empty). A page or script without the Pixel values gets a 400 naming what's missing.

Context: send a non-empty `context` back on the next Pixel call only.

#### sec-cpt (crypto and adaptive challenge)

`onestop.akamai_sec_cpt_payload(cookie=..., token=..., nonce=..., timestamp=..., difficulty=..., count=...)` returns `str`.

A blocked page can come back as a challenge page with `<iframe id="sec-cpt-if" provider="crypto" challenge="…" data-duration=N src="/_sec/cp_challenge/ak-challenge-4-3.htm">`, or an API call as a 429 JSON with `"sec-cp-challenge":"true"` and `"provider":"crypto"`. The helper solves it locally. `provider` is `crypto` or `adaptive`; both are the same work. `provider="behavioral"` (press and hold) is not supported.

1. Read the challenge: the iframe's `challenge` attribute, base64-decoded, is a JSON object with `token`, `timestamp`, `nonce`, `difficulty`, `timeout`, `cpu` and sometimes `count`; the 429 variant carries the same fields in its body.
2. Call with the `sec_cpt` cookie value and those fields. `count` is the number of answers; use 10 when the challenge has none.
3. Let the challenge's countdown run out (`data-duration` seconds on the iframe, `chlg_duration` in the 429 JSON, counted from when the challenge arrived; solving can overlap it). Then POST the returned body to `/_sec/verify?provider=<provider>` on the page's origin, with the page's cookies, the challenge page as referer and no content type set by you (the browser sends it as `text/plain;charset=UTF-8`). It answers 200 with `{"sec-cp-challenge":"true","status":"success"}`; the `sec_cpt` cookie is then accepted. If the reply carries a new `token` instead, it is another round: solve again with the new values and the current `sec_cpt` cookie. `verify_url` and `cca_verify_url` in the challenge are not used.
4. GET the page again.

| Field | When | Value from |
|---|---|---|
| `cookie` | Every call | The `sec_cpt` cookie value. Only the part before its first `~` is used. |
| `token` | Every call | `token` from the challenge JSON. |
| `nonce` | Every call | `nonce` from the challenge JSON. |
| `timestamp` | Every call | `timestamp` from the challenge JSON (seconds). |
| `difficulty` | Every call | `difficulty` from the challenge JSON. |
| `count` | Every call | `count` from the challenge JSON, or 10. |

Returns the verify POST body `{"token": "<token>", "answers": ["…"]}`, built as the challenge script builds it. Runs locally: no API call, no charge. Bad inputs fail with an `akamai:` error.

Context: none. This is not the SBSD block (`sec-if-cpt-container` with a `?v=` script); that one is an SBSD call.

### DataDome

All three methods return `onestop.DatadomeResponse`:

- `payload`: already encoded. Send it as is.
- `context`: send it on the next DataDome call in this session.

A blocked page answers 403 with `var dd={...}` in the HTML (spacing around `=` varies; a JSON block gives the challenge URL in `url`). `rt` `i` is the interstitial, `c` the slider.

#### DataDome tags

`session.datadome_tags(...)` returns `onestop.DatadomeResponse`.

1. `ch`: `event` `ch`, `site_key`, `version`, `cookie`. No `context` on the session's first DataDome call.
2. POST `payload` to the `/js/` endpoint tags.js posts to, usually `https://api-js.datadome.co/js/`, as `application/x-www-form-urlencoded`. The JSON reply has the new cookie in `cookie`.
3. `le`: `event` `le`, the new `cookie` and `context` from ch. POST it the same way.

| Field | When | Value from |
|---|---|---|
| `event` | Every call | `ch` first, then `le`. |
| `site_key` | Every call | The site's DataDome key, sent as `ddk` in the tags POST (the page sets it as `ddjskey`). Fixed per site. |
| `version` | Every call | The tags.js version (`ddv`), e.g. `5.1.0`. |
| `cookie` | Every call | The current `datadome` cookie. Update it from each `/js/` reply. |
| `context` | If the session has one | The latest DataDome context in this session, from tags, interstitial or slider. |

Returns `payload` (the `/js/` form body) and `context`.

Context: one DataDome context per session, shared by tags, interstitial and slider. Always send the most recent one.

#### DataDome interstitial

`session.datadome_interstitial(...)` returns `onestop.DatadomeResponse`.

1. GET the page: 403 with the `dd` object, `rt` `i`. `t` equal to `bv` is a hard block: stop.
2. Build `https://geo.captcha-delivery.com/interstitial/?initialCid=<cid>&hash=<hsh>&cid=<cookie>&referer=<page URL>&s=<s>&e=<e>&b=<b>&dm=cd` from it, in this order. URL-encode each value; leave out `&e=` when `e` is empty.
3. GET it (as an iframe), then its script: the `src` containing `interstitial.`. Some pages inline the script and have no such `src`; then skip the GET.
4. Call with the script (empty when inlined), that page's HTML and the 403 body.
5. POST `payload` to `https://geo.captcha-delivery.com/interstitial/` as `application/x-www-form-urlencoded; charset=UTF-8`.
6. The JSON reply has `view: "redirect"` and a `datadome` cookie in `cookie`. Store it on its `Domain` and GET the page again (200 or 302).

| Field | When | Value from |
|---|---|---|
| `script` | If the page has the script tag | The interstitial script's source. Empty when the page inlines it; the API reads it from `html`. |
| `html` | Every call | The interstitial page HTML from geo.captcha-delivery.com. |
| `page_response` | Every call | The body of the blocked (403) response that sent you there. |
| `context` | If the session has one | The latest DataDome context in this session, from tags, interstitial or slider. |

Returns `payload` (the form body) and `context`.

Context: one DataDome context per session, shared by tags, interstitial and slider. Always send the most recent one.

Example: `examples/<client>/datadome_interstitial.py`

#### DataDome slider

`session.datadome_slider(...)` returns `onestop.DatadomeResponse`.

1. GET the page: 403 with the `dd` object, `rt` `c`. `t` equal to `bv` is a hard block: stop.
2. Build `https://geo.captcha-delivery.com/captcha/?initialCid=<cid>&hash=<hsh>&cid=<cookie>&t=<t>&referer=<page URL>&s=<s>&e=<e>&dm=cd` from it, in this order. URL-encode each value; leave out `&e=` when `e` is empty.
3. GET it, its script (the `captcha...js` `src`; some pages inline it, then skip the GET) and both images: `captchaChallengePath` in the page is the background `.jpg`; the same path ending `.frag.png` is the piece. A relative path is on `https://geo.captcha-delivery.com`.
4. Call with the script (empty when inlined), page HTML, the 403 body and both images in base64.
5. GET `https://geo.captcha-delivery.com/captcha/check` with `payload` appended as is.
6. The JSON reply has a `datadome` cookie in `cookie`. Store it on its `Domain` and GET the page again (200 or 302).

| Field | When | Value from |
|---|---|---|
| `script` | If the page has the script tag | The captcha script's source. Empty when the page inlines it; the API reads it from `html`. |
| `html` | Every call | The captcha page HTML from geo.captcha-delivery.com. |
| `page_response` | Every call | The body of the blocked (403) response that sent you there. |
| `background_image` | Every call | The image at `captchaChallengePath`, base64. |
| `puzzle_piece` | Every call | The same path with `.jpg` changed to `.frag.png`, base64. |
| `context` | If the session has one | The latest DataDome context in this session, from tags, interstitial or slider. |

Returns `payload` (the check request's query string) and `context`.

Context: one DataDome context per session, shared by tags, interstitial and slider. Always send the most recent one.

Example: `examples/<client>/datadome_slider.py`

### Cloudflare

Every Cloudflare method takes keyword arguments (`onestop.CloudflareCall`) and returns `onestop.CloudflareResponse`:

- `requests`: the target requests to make, in order. Each has `purpose`, `method`, `url`, `headers`, `body`.
- `context`: send it on the next call.
- `token`: the Turnstile token, once solved.

The loop (WAF, Turnstile, precursor interstitial): make each entry in `requests` in order with your client and cookies, sending every header it lists, then call again with `context` plus what each request returned:

| `purpose` | Send back on the next call |
|---|---|
| `challenge` | Its response body as `response` (a `str`). |
| `iframe` | Its HTML as `html`, its final URL as `iframe_url`, its `cf-ray` header as `bytecode_ray_id`. |
| `image` | The image size as `image_width` and `image_height` (`int`). |
| `pat` | Its HTTP status as `pat_status` (`int`). A 4xx is normal. |
| `form` | Nothing. POST it without following redirects, with the origin and referer it carries: its response is the cleared page and sets `cf_clearance`. |

#### Cloudflare step

`session.cloudflare_step(...)` returns `onestop.CloudflareResponse`.

Use it in place of the specific method when you don't know which Cloudflare challenge it is. The API works it out from what you send. Fetch what the challenge needs and send its first call as in its section below, then keep calling this method for the rest of the flow. Fields and returns are the matching method's.

Context: each step returns the context for the next. A Cloudflare context only goes back to Cloudflare.

#### Cloudflare WAF (managed challenge)

`session.cloudflare_waf(...)` returns `onestop.CloudflareResponse`.

1. GET the page. The challenge answers 403 with `_cf_chl_opt` and `__cf_chl_rt_tk=` in the HTML (a `cType` of `precursor_interstitial` is the precursor interstitial below). The script is the path in `src = '...'`, on the page's origin. GET it.
2. First call: `html`, `script`, `script_url`.
3. Run the loop.
4. Stop at the `form` request: POST it without following redirects. `cf_clearance` is set.

| Field | When | Value from |
|---|---|---|
| `html` | First call | The challenge page HTML. |
| `script` | First call | The challenge script's source. |
| `script_url` | First call | The challenge script's full URL. |
| `context` + loop fields | Later calls | `context` from the previous response, plus the fields from the loop table. |

Returns `requests` and `context`.

Context: each step returns the context for the next. A Cloudflare context only goes back to Cloudflare.

Example: `examples/<client>/cloudflare_waf.py`

#### Cloudflare Turnstile

`session.cloudflare_turnstile(...)` returns `onestop.CloudflareResponse`.

1. GET `https://challenges.cloudflare.com/turnstile/v0/api.js` and follow its redirect. The final URL is `/turnstile/v0/<g or b>/<hash>/api.js`.
2. GET the iframe: `https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/<g or b>/turnstile/f/av0/rch/<5 random a-z0-9>/<sitekey>/light/fbE/new/normal?lang=auto`. The sitekey is in the page's `turnstile.render` options or `data-sitekey`.
3. First call: the iframe HTML, its final URL, its `cf-ray`, the api.js URL, and the widget's `action` and `cData`.
4. Run the loop.
5. Stop when a response has `token`.

| Field | When | Value from |
|---|---|---|
| `html` | First call | The iframe HTML. |
| `iframe_url` | First call | The iframe's final URL, after redirects. |
| `bytecode_ray_id` | First call | The iframe response's `cf-ray` header. |
| `script_url` | First call | The api.js URL after its redirect. |
| `action` | Every call, if set | The widget's `action` from the page. |
| `c_data` | Every call, if set | The widget's `cData` from the page. |
| `context` + loop fields | Later calls | `context` from the previous response, plus the fields from the loop table. |

Returns `requests`, `context`, and `token` once solved. Use the token where the site expects the Turnstile response.

Context: each step returns the context for the next. A Cloudflare context only goes back to Cloudflare.

Example: `examples/<client>/cloudflare_turnstile.py`

#### Cloudflare JSD

`session.cloudflare_jsd(...)` returns `onestop.CloudflareResponse`.

1. GET the page (a normal page, no challenge shown). Keep its `cf-ray` response header.
2. GET `/cdn-cgi/challenge-platform/scripts/jsd/main.js` on the site's own host, with the page's cookies (it redirects to a versioned script).
3. Call with the script and the page's `cf-ray`.
4. Make the one `challenge` POST in `requests`. That finishes it.

| Field | When | Value from |
|---|---|---|
| `script` | Every call | The `main.js` source. |
| `ray_id` | Every call | The page response's `cf-ray` header, not the script's. |

Returns `requests` (one `challenge` POST).

Context: none. One call per page.

#### Cloudflare precursor interstitial

`session.cloudflare_precursor(...)` returns `onestop.CloudflareResponse`.

1. GET the page. It answers 403 with a challenge page like WAF's, but its `cType` is `precursor_interstitial`. The script is the path in `src = '...'`, on the page's origin. GET it.
2. First call: `html`, `script`, `script_url`.
3. Run the loop.
4. Stop at the `form` request: POST it without following redirects.

| Field | When | Value from |
|---|---|---|
| `html` | First call | The challenge page HTML. |
| `script` | First call | The challenge script's source. |
| `script_url` | First call | The challenge script's full URL. |
| `context` + loop fields | Later calls | `context` from the previous response, plus the fields from the loop table. |

Returns `requests` and `context`.

Context: each step returns the context for the next. A Cloudflare context only goes back to Cloudflare.

#### Cloudflare precursor minimal

`session.cloudflare_precursor(...)` returns `onestop.CloudflareResponse`.

1. GET the page (200, a normal page). The script is the `src` containing `/scripts/precursor/`. GET it from the same origin.
2. First call: `html`, `script`, `script_url` (the script's final URL).
3. POST each request as `text/plain;charset=UTF-8` with its headers. Each reply is JSON like `{"i":60,"n":false}`.
4. Stop when `n` is true, or after five POSTs. A long `i` comes back as the next result's `sleep`, which the SDK waits.
5. Otherwise call again with `context` and the reply as `response`, as a JSON object, not a string (the raw reply `bytes` or the parsed `dict`).

| Field | When | Value from |
|---|---|---|
| `html` | First call | The page HTML. |
| `script` | First call | The precursor script's source. |
| `script_url` | First call | The precursor script's final URL. |
| `context` | Later calls | `context` from the previous response. |
| `response` | Later calls | The last POST's JSON reply, e.g. `{"i":60,"n":false}`. |

Returns `requests` and `context`. Every POST answering 2xx is the pass.

Context: each step returns the context for the next. A Cloudflare context only goes back to Cloudflare.

Example: `examples/<client>/cloudflare_precursor.py`

### Kasada

Three steps: p.js, then /tl, then the CD header. `<base>` is `<origin>/<id>/<id>/`, from the p.js path.

#### Kasada p.js

`session.kasada_pscript(script)` returns `onestop.KasadaPScriptResponse`.

1. GET the page. p.js is at `/<id>/<id>/p.js` on its origin (two 36-character ids; some pages write the path JSON-escaped, so replace `\/` and `\u002f` with `/` first). GET it.
2. Call with its source.
3. Send `x-kpsdk-v` from `headers` on your Kasada requests. Keep the result (`ps` below) for the CD header; reuse it until `cache_lifetime_seconds` runs out.

| Field | When | Value from |
|---|---|---|
| `script` | Every call | The p.js source. |

Returns `version` (the Kasada SDK version), `headers` (`x-kpsdk-v`, the full header value), `difficulty`, `subchallenge_count`, `seed_suffix`, `crypto_customer_key` (CD header inputs, used by `cd_header`), and `cache_lifetime_seconds` (seconds until these values expire). No charge.

Context: none. Reuse the result in the same session until it expires.

Example: `examples/<client>/kasada.py` (p.js and /tl, or the 429 block page).

#### Kasada /tl

`session.kasada_tl(script_url, script)` returns `onestop.KasadaResponse`.

1. GET `<base>mfc` with `x-kpsdk-v` and `x-kpsdk-h: 01`.
2. GET `<base>fp?x-kpsdk-v=<v>`. It answers 429 and its body links ips.js: take that `<script src>`, HTML-unescape it (`&amp;` to `&`) and resolve it against the fp URL. No ips.js `src` in the fp body is a failure.
3. GET that ips.js URL, with the fp URL as referer.
4. Call with that full URL and the ips.js source.
5. Base64-decode `payload` and POST it to `<base>tl` as `application/octet-stream`, with every header in `headers` (`x-kpsdk-ct`, `x-kpsdk-dt`, `x-kpsdk-im`, `x-kpsdk-v`; mobile apps also get `x-kpsdk-dv`), the page's origin as `origin` and the fp URL as referer. It answers 200 with `"reload":true`.
6. Keep `x-kpsdk-ct` and `x-kpsdk-st` from the /tl response for the CD header.

| Field | When | Value from |
|---|---|---|
| `script_url` | Every call | The full ips.js URL you fetched, query string included. |
| `script` | Every call | The ips.js source. |

If the page itself answers 429 with an ips.js `<script src>`, it is the block page: take its ips.js URL the same way, resolved against the page URL. Skip p.js, mfc and fp, and send the page URL as referer for ips.js and /tl. `<base>` is then the ips.js URL's directory. The CD header still needs a p.js result.

Returns `payload` (the /tl body, base64; decode it before sending) and `headers` (the `x-kpsdk-*` headers for the /tl POST; send them all).

Context: none. Each /tl call stands alone.

Example: `examples/<client>/kasada.py`

#### Kasada CD header

`ps.cd_header(ct, st)` returns `str`, where `ps` is the `session.kasada_pscript` result.

1. After the /tl POST, take `x-kpsdk-ct` and `x-kpsdk-st` from its response.
2. Call it on `ps`, the p.js result, with them. The SDK fills in the current time.
3. Send the value as `x-kpsdk-cd`, with `x-kpsdk-ct`, on the protected request.

| Field | When | Value from |
|---|---|---|
| `ct` | Every call | The `x-kpsdk-ct` header from the /tl response. |
| `st` | Every call | The `x-kpsdk-st` header from the /tl response, in ms (`int`). |

Returns the header value. Runs locally: no API call, no charge. Bad inputs fail with a `kasada:` error. For mobile apps, `onestop.kasada_cd_header(...)` takes every input.

Context: none. Use a p.js result from this session that hasn't expired.
