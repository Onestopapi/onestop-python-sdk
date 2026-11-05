# Kasada: load the page and its p.js, then mfc, fp (200 or 429) and ips.js, and
# POST the generated /tl body. A page that is already the 429 block page
# links ips.js itself. /tl answers 200 with reload:true. Then build the
# x-kpsdk-cd header locally and make one protected POST.
import base64
import re
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpclient
import onestop_antibot as onestop

api_key = "YOUR_API_KEY"
identifier = "YOUR_IDENTIFIER"  # your identifier or account name
page_url = "https://www.example.com/"
protected_url = "https://www.example.com/api/protected"  # a request Kasada protects
protected_body = "{}"  # its JSON body
accept_language = "en-US,en;q=0.9"

proxy = ""  # your proxy, in the site's country

pjs_path = re.compile(r"/[0-9a-f-]{36}/[0-9a-f-]{36}/p\.js")
ips_script = re.compile(r'src="([^"]*/ips\.js[^"]*)"')


@dataclass
class Ips:
    """The loaded ips.js: its URL, its source and the page that loaded it."""

    url: str
    source: str
    referer: str


def main() -> None:
    hc = httpclient.Client(proxy)
    client, ip = new_client()
    page = get_page(hc)
    session = new_session(client, ip, page.url)
    base = find_base(page)
    ps = get_pscript(hc, session, page, base)
    script, h = get_ips(hc, page, base, ps)
    tl = post_tl(hc, session, page, script)
    cd = build_cd_header(ps, tl)
    post_protected(hc, page, ps, tl, h, cd)
    site_firewall(hc, page_url)
    print("PASS /tl 200 reload:true, protected request 200")


def new_client() -> tuple[onestop.Client, str]:
    try:
        client = onestop.Client(
            api_key=api_key,
            identifier=identifier,
            ip_http_client=httpclient.ip_client(proxy),
        )
        ip = client.get_ip()  # through the proxy: the IP the site sees
    except onestop.OneStopError as e:
        sys.exit(f"FAIL {e}")
    return client, ip


def new_session(client: onestop.Client, ip: str, site: str) -> onestop.Session:
    return client.session(
        site=site,
        referer=site,
        user_agent=httpclient.USER_AGENT,
        accept_language=accept_language,
        ip=ip,
    )


def get_page(hc: httpclient.Client) -> httpclient.Response:
    return hc.get(page_url, httpclient.navigate(accept_language, ""))


def is_block_page(page: httpclient.Response) -> bool:
    return page.status == 429 and bool(ips_script.search(page.body))


def find_base(page: httpclient.Response) -> str:
    """Returns the script directory: p.js, mfc, fp, ips.js and tl sit in it. A block page links ips.js there; any
    other page links p.js."""
    if is_block_page(page):
        return ips_url_from(page).partition("ips.js")[0]
    # p.js lives at /<uuid>/<uuid>/p.js.
    # Some pages write the path JSON-escaped (`\/` or `\u002f` for `/`).
    match = pjs_path.search(page.body.replace("\\/", "/").replace("\\u002f", "/"))
    if not match:
        sys.exit(f"FAIL page returned {page.status} without a Kasada p.js")
    u = urlsplit(page.url)
    return f"{u.scheme}://{u.netloc}" + match[0].removesuffix("p.js")


def get_pscript(
    hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, base: str
) -> onestop.KasadaPScriptResponse:
    """Loads p.js. Keep the result: x-kpsdk-v goes on the Kasada requests and the CD header is built from it."""
    pjs = hc.get(base + "p.js", httpclient.script(accept_language, "same-origin", page.url))
    try:
        return session.kasada_pscript(pjs.body)
    except onestop.OneStopError as e:
        sys.exit(f"FAIL p.js: {e}")


def get_ips(
    hc: httpclient.Client, page: httpclient.Response, base: str, ps: onestop.KasadaPScriptResponse
) -> tuple[Ips, str]:
    """Loads ips.js and returns it with the x-kpsdk-h from mfc. A block page links it directly (no mfc); otherwise mfc
    and fp lead to it."""
    from_, h = page, ""
    if not is_block_page(page):
        from_, h = get_fp(hc, page, base, ps.headers["x-kpsdk-v"])
    ips_url = ips_url_from(from_)
    res = hc.get(ips_url, httpclient.script(accept_language, "same-origin", from_.url))
    if res.status != 200:
        sys.exit(f"FAIL ips.js returned {res.status}")
    return Ips(ips_url, res.body, from_.url), h


def get_fp(
    hc: httpclient.Client, page: httpclient.Response, base: str, version: str
) -> tuple[httpclient.Response, str]:
    """Loads mfc and fp and returns fp with mfc's x-kpsdk-h, which the protected requests carry. fp can answer 200 or 429;
    require an ips.js link in its body, not a particular status."""
    mfc = hc.get(base + "mfc", httpclient.kasada_mfc(accept_language, version, page.url))
    if mfc.status != 200:
        sys.exit(f"FAIL mfc returned {mfc.status}")
    fp = hc.get(base + "fp?x-kpsdk-v=" + version, httpclient.frame(accept_language, "same-origin", page.url))
    if not ips_script.search(fp.body):
        sys.exit("FAIL fp returned no ips.js")
    return fp, mfc.header("x-kpsdk-h")


def ips_url_from(res: httpclient.Response) -> str:
    """Returns the ips.js src a Kasada response body links, HTML-unescaped and resolved against the response URL."""
    return res.resolve(ips_script.search(res.body)[1])


def post_tl(
    hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, script: Ips
) -> httpclient.Response:
    try:
        tl = session.kasada_tl(script.url, script.source)
    except onestop.OneStopError as e:
        sys.exit(f"FAIL tl: {e}")
    u = urlsplit(page.url)
    origin = f"{u.scheme}://{u.netloc}"
    base = script.url.partition("ips.js")[0]
    body = base64.b64decode(tl.payload)  # payload is the /tl body in base64
    res = hc.post(base + "tl", httpclient.kasada_tl(accept_language, tl.headers, origin, script.referer), body)
    if res.status != 200 or '"reload":true' not in res.body:
        sys.exit(f"FAIL /tl returned {res.status}: {res.body}")
    return res


def build_cd_header(ps: onestop.KasadaPScriptResponse, tl: httpclient.Response) -> str:
    """Builds x-kpsdk-cd locally (no API call) from the p.js result and the /tl response's x-kpsdk-ct and
    x-kpsdk-st."""
    try:
        st = int(tl.header("x-kpsdk-st"))  # ms
    except ValueError as e:
        sys.exit(f"FAIL /tl x-kpsdk-st: {e}")
    try:
        return ps.cd_header(tl.header("x-kpsdk-ct"), st)
    except onestop.OneStopError as e:
        sys.exit(f"FAIL cd header: {e}")


def post_protected(
    hc: httpclient.Client,
    page: httpclient.Response,
    ps: onestop.KasadaPScriptResponse,
    tl: httpclient.Response,
    h: str,
    cd: str,
) -> None:
    """The request Kasada protects, a POST as most are: x-kpsdk-ct (the newest one seen, here from /tl), x-kpsdk-v
    from p.js, x-kpsdk-h from mfc and the CD header just built. Each protected POST gets a fresh CD header."""
    u = urlsplit(page.url)
    headers = httpclient.post(accept_language, "application/json", f"{u.scheme}://{u.netloc}", page.url).with_({
        "x-kpsdk-ct": tl.header("x-kpsdk-ct"),
        "x-kpsdk-cd": cd,
        "x-kpsdk-h": h,
        "x-kpsdk-v": ps.headers["x-kpsdk-v"],
    })
    res = hc.post(protected_url, headers, protected_body)
    if res.status != 200:
        sys.exit(f"FAIL protected request returned {res.status}")


def site_firewall(hc: httpclient.Client, page_url: str) -> None:
    # Insert the relevant requests for your site's firewall. This is up to you and your agent to experiment with.
    # Some sites (DataDome, Akamai) are strict on flow: you might need additional requests here.
    pass


if __name__ == "__main__":
    main()
