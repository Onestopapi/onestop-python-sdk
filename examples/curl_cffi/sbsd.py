# SBSD block: POST one mode f payload to the block script with ?t=<token>
# (bm_sc 2~ clears the block), load the page again, then send the passive
# SBSD payloads (mode f, then t) for the real page's script.
import json
import re
import sys
from typing import TypedDict
from urllib.parse import SplitResult, parse_qs, urlsplit

import httpclient
import onestop_antibot as onestop

api_key = "YOUR_API_KEY"
identifier = ""  # your identifier or account name
page_url = "https://www.example.com/"
accept_language = "de-DE,de;q=0.9"

proxy = ""  # your proxy, in the site's country

sbsd_script = re.compile(r'<script[^>]*src="([^"]*\?v=[^"]*)"')
block_token = re.compile(r'\{"cpr_chlge":"true","t":"([^"]*)"')


class SbsdBody(TypedDict):
    """The JSON body of an SBSD POST."""

    body: str


def main() -> None:
    hc = httpclient.Client(proxy)
    client, ip = new_client()
    page = get_block_page(hc)
    block_url, token = find_block_script(page)
    session = new_session(client, ip, page.url)
    solve_block(hc, session, page, block_url, token)
    loaded, sbsd_url = reload_page(hc, page)
    solve_passive(hc, session, loaded, sbsd_url)
    site_firewall(hc, page_url)
    print("PASS SBSD block cleared (bm_sc 2~), real page loaded, passive f+t 200")


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


def get_block_page(hc: httpclient.Client) -> httpclient.Response:
    return hc.get(page_url, httpclient.navigate(accept_language, ""))


def find_block_script(page: httpclient.Response) -> tuple[SplitResult, str]:
    match = sbsd_script.search(page.body)
    if not match:
        sys.exit("FAIL not a block page")
    block_url = urlsplit(page.resolve(match[1]))
    # The block token is the script URL's t= value, else the page's
    # {"cpr_chlge":"true","t":"<token>"}.
    token = parse_qs(block_url.query).get("t", [""])[0]
    token_match = block_token.search(page.body)
    if not token and token_match:
        token = token_match[1]
    if not token:
        sys.exit("FAIL not a block page")
    return block_url, token


def solve_block(
    hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, block_url: SplitResult, token: str
) -> None:
    origin = f"{block_url.scheme}://{block_url.netloc}"
    block = hc.get(block_url.geturl(), httpclient.script(accept_language, "same-origin", page.url))
    try:
        res = session.sbsd_payload(
            uuid=parse_qs(block_url.query)["v"][0],  # v= value of the script URL
            sbsd_cookie=hc.cookie(page.url, "bm_so", "sbsd_o"),  # cookie set by the page
            script=block.body,
            mode="f",
        )
    except onestop.OneStopError as e:
        sys.exit(f"FAIL SBSD block: {e}")
    body = json.dumps(SbsdBody(body=res.payload), separators=(",", ":"))
    post = hc.post(origin + block_url.path + "?t=" + token, httpclient.post(accept_language, "application/json", origin, page.url), body)
    if post.status != 200:
        sys.exit(f"FAIL SBSD block POST returned {post.status}")
    # bm_sc 2~ passed, 3~ failed.
    verdict = hc.cookie(page.url, "bm_sc")
    if not verdict.startswith("2~"):
        sys.exit(f"FAIL SBSD block verdict bm_sc={verdict}")


def reload_page(hc: httpclient.Client, page: httpclient.Response) -> tuple[httpclient.Response, SplitResult]:
    loaded = hc.get(page.url, httpclient.navigate(accept_language, ""))
    if loaded.status != 200:
        sys.exit(f"FAIL page re-GET returned {loaded.status}")
    match = sbsd_script.search(loaded.body)
    if not match:
        sys.exit("FAIL real page has no SBSD script")
    sbsd_url = urlsplit(loaded.resolve(match[1]))
    if parse_qs(sbsd_url.query).get("t"):
        sys.exit("FAIL page re-GET is still a block page")
    return loaded, sbsd_url


def solve_passive(
    hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, sbsd_url: SplitResult
) -> None:
    origin = f"{sbsd_url.scheme}://{sbsd_url.netloc}"
    sbsd = hc.get(sbsd_url.geturl(), httpclient.script(accept_language, "same-origin", page.url).no_cache())
    # uuid is the v= value of the new script URL; mode t sends f's context.
    uuid = parse_qs(sbsd_url.query)["v"][0]
    script, context = sbsd.body, ""
    for mode in ("f", "t"):
        try:
            res = session.sbsd_payload(
                uuid=uuid,
                sbsd_cookie=hc.cookie(page.url, "bm_so", "sbsd_o"),
                script=script,
                mode=mode,
                context=context,
            )
        except onestop.OneStopError as e:
            sys.exit(f"FAIL SBSD {mode}: {e}")
        body = json.dumps(SbsdBody(body=res.payload), separators=(",", ":"))
        post = hc.post(origin + sbsd_url.path, httpclient.post(accept_language, "application/json", origin, page.url).no_cache(), body)
        if post.status != 200:
            sys.exit(f"FAIL SBSD {mode} POST returned {post.status}")
        script, context = "", res.context


def site_firewall(hc: httpclient.Client, page_url: str) -> None:
    # Insert the relevant requests for your site's firewall. This is up to you and your agent to experiment with.
    # Some sites (DataDome, Akamai) are strict on flow: you might need additional requests here.
    pass


if __name__ == "__main__":
    main()
