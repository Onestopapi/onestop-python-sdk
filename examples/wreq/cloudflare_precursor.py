# Cloudflare precursor: the page loads a /scripts/precursor/ script that
# makes up to five small POSTs. Each reply is {"i": seconds, "n": done}:
# n true stops; the API turns a long i into its sleep.
import json
import re
import sys
from typing import TypedDict
from urllib.parse import urlsplit

import httpclient
import onestop_antibot as onestop

api_key = "YOUR_API_KEY"
identifier = ""  # your identifier or account name
page_url = "https://www.example.com/"
accept_language = "en-US,en;q=0.9"

proxy = ""  # your proxy, in the site's country

# The precursor script's path wherever the page writes it: a script tag or an
# inline loader that adds one, quoted either way.
precursor_script = re.compile(r"(?:https://[A-Za-z0-9.-]+)?/cdn-cgi/challenge-platform/scripts/precursor/[A-Za-z0-9._/-]+")


class PrecursorReply(TypedDict, total=False):
    """A precursor POST's JSON reply: n is true when done."""

    n: bool


def main() -> None:
    hc = httpclient.Client(proxy)
    client, ip = new_client()
    page, first = get_challenge_page(hc)
    session = new_session(client, ip, page.url)
    result = run_challenge_loop(hc, session, page, first)
    site_firewall(hc, page_url)
    print("PASS " + result)


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


def get_challenge_page(hc: httpclient.Client) -> tuple[httpclient.Response, onestop.CloudflareCall]:
    """Returns the page and the first call: the page and the precursor script."""
    page = hc.get(page_url, httpclient.navigate(accept_language, ""))
    match = precursor_script.search(page.body)
    if page.status != 200 or not match:
        sys.exit(f"FAIL page returned {page.status} without a precursor script")
    script = hc.get(page.resolve(match[0]), httpclient.script(accept_language, "same-origin", page.url))
    if script.status != 200:
        sys.exit(f"FAIL precursor script returned {script.status}")
    return page, onestop.CloudflareCall(html=page.body, script=script.body, script_url=script.url)


def run_challenge_loop(
    hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, call: onestop.CloudflareCall
) -> str:
    """Sends each step's POSTs; every later call sends the previous context and the target's reply."""
    u = urlsplit(page.url)
    origin = f"{u.scheme}://{u.netloc}"
    for posts in range(1, 6):
        try:
            step = session.cloudflare_precursor(**call)
        except onestop.OneStopError as e:
            sys.exit(f"FAIL precursor: {e}")
        call = onestop.CloudflareCall(context=step.context)
        for r in step.requests:
            res = hc.do(r.method, r.url, httpclient.post(accept_language, "text/plain;charset=UTF-8", origin, page.url).with_(r.headers), r.body)
            try:
                reply: PrecursorReply | None = json.loads(res.body)
            except ValueError:
                reply = None
            if not 200 <= res.status <= 299 or not isinstance(reply, dict):
                sys.exit(f"FAIL precursor POST {posts} returned {res.status}: {res.body}")
            if reply.get("n"):
                return "precursor POSTs 2xx until n:true"
            call["response"] = res.content
    return "5 precursor POSTs 2xx"


def site_firewall(hc: httpclient.Client, page_url: str) -> None:
    # Insert the relevant requests for your site's firewall. This is up to you and your agent to experiment with.
    # Some sites (DataDome, Akamai) are strict on flow: you might need additional requests here.
    pass


if __name__ == "__main__":
    main()
