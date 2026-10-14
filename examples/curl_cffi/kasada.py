# Kasada: load the page and its p.js, then mfc, fp (429) and ips.js, and
# POST the generated /tl body. A page that is already the 429 block page
# links ips.js itself. /tl answers 200 with reload:true.
import base64
import re
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpclient
import onestop_antibot as onestop

api_key = "YOUR_API_KEY"
identifier = ""  # your identifier or account name
page_url = "https://www.example.com/"
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
    session = new_session(client, ip, page_url)
    page = get_page(hc)
    script = get_ips(hc, session, page)
    post_tl(hc, session, page, script)
    site_firewall(hc, page_url)
    print("PASS /tl 200 reload:true")


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


def get_ips(hc: httpclient.Client, session: onestop.Session, page: httpclient.Response) -> Ips:
    """Loads ips.js. When the page itself is the 429 block page it links ips.js directly; otherwise p.js, mfc and fp
    lead to it."""
    from_ = page
    if page.status != 429 or not ips_script.search(page.body):
        base, version = get_pscript(hc, session, page)
        from_ = get_fp(hc, page, base, version)
    ips_url = ips_url_from(from_)
    res = hc.get(ips_url, httpclient.script(accept_language, "same-origin", from_.url))
    if res.status != 200:
        sys.exit(f"FAIL ips.js returned {res.status}")
    return Ips(ips_url, res.body, from_.url)


def get_pscript(hc: httpclient.Client, session: onestop.Session, page: httpclient.Response) -> tuple[str, str]:
    """Returns the script directory and x-kpsdk-v from the p.js result."""
    # p.js lives at /<uuid>/<uuid>/p.js; mfc, fp, ips.js and tl sit next to it.
    # Some pages write the path JSON-escaped (\/ or \u002f for /).
    match = pjs_path.search(page.body.replace("\\/", "/").replace("\\u002f", "/"))
    if not match:
        sys.exit(f"FAIL page returned {page.status} without a Kasada p.js")
    u = urlsplit(page.url)
    base = f"{u.scheme}://{u.netloc}" + match[0].removesuffix("p.js")
    pjs = hc.get(base + "p.js", httpclient.script(accept_language, "same-origin", page.url))
    try:
        ps = session.kasada_pscript(pjs.body)
    except onestop.OneStopError as e:
        sys.exit(f"FAIL p.js: {e}")
    return base, ps.headers["x-kpsdk-v"]


def get_fp(hc: httpclient.Client, page: httpclient.Response, base: str, version: str) -> httpclient.Response:
    """Loads mfc and fp. fp answers 429 with a body that links ips.js."""
    mfc = hc.get(base + "mfc", httpclient.kasada_mfc(accept_language, version, page.url))
    if mfc.status != 200:
        sys.exit(f"FAIL mfc returned {mfc.status}")
    fp = hc.get(base + "fp?x-kpsdk-v=" + version, httpclient.frame(accept_language, "same-origin", page.url))
    if not ips_script.search(fp.body):
        sys.exit("FAIL fp returned no ips.js")
    return fp


def ips_url_from(res: httpclient.Response) -> str:
    """Returns the ips.js src a Kasada 429 body links, HTML-unescaped and resolved against the response URL."""
    return res.resolve(ips_script.search(res.body)[1])


def post_tl(hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, script: Ips) -> None:
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


def site_firewall(hc: httpclient.Client, page_url: str) -> None:
    # Insert the relevant requests for your site's firewall. This is up to you and your agent to experiment with.
    # Some sites (DataDome, Akamai) are strict on flow: you might need additional requests here.
    pass


if __name__ == "__main__":
    main()
