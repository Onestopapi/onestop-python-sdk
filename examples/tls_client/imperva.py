# Imperva: the page answers with the reese84 challenge page, which adds the
# challenge script. Load the script, POST the generated body to the script's
# path with ?d=<host>, store the returned token as the reese84 cookie and
# load the page again.
import json
import re
import sys
from typing import TypedDict
from urllib.parse import SplitResult, urlsplit

import httpclient
import onestop_antibot as onestop

api_key = "YOUR_API_KEY"
identifier = "YOUR_IDENTIFIER"  # your identifier or account name
page_url = "https://www.example.com/"
accept_language = "en-GB,en;q=0.9"

proxy = ""  # your proxy, in the site's country

challenge_script = re.compile(r'scriptElement\.src\s*=\s*"([^"]+)"')


class TokenReply(TypedDict, total=False):
    """The reese84 POST's JSON reply."""

    token: str
    cookieDomain: str


def main() -> None:
    hc = httpclient.Client(proxy)
    client, ip = new_client()
    page = get_challenge_page(hc)
    script_url = find_script(page)
    session = new_session(client, ip, page.url)
    script = get_script(hc, page, script_url)
    solve_challenge(hc, session, page, script_url, script)
    reload_page(hc, page)
    site_firewall(hc, page_url)
    print("PASS reese84 cookie set, page re-GET 200")


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


def get_challenge_page(hc: httpclient.Client) -> httpclient.Response:
    return hc.get(page_url, httpclient.navigate(accept_language, ""))


def find_script(page: httpclient.Response) -> SplitResult:
    """Returns the script the challenge page adds with scriptElement.src = "..."."""
    match = challenge_script.search(page.body)
    if not match:
        sys.exit(f"FAIL page returned {page.status} without an Imperva challenge")
    return urlsplit(page.resolve(match[1]))


def get_script(hc: httpclient.Client, page: httpclient.Response, script_url: SplitResult) -> str:
    res = hc.get(script_url.geturl(), httpclient.imperva_script(accept_language, page.url))
    if res.status != 200:
        sys.exit(f"FAIL script returned {res.status}")
    return res.body


def solve_challenge(
    hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, script_url: SplitResult, script: str
) -> None:
    try:
        res = session.imperva(script_url.geturl(), script)
    except onestop.OneStopError as e:
        sys.exit(f"FAIL imperva: {e}")
    # res.payload is the POST body; it goes to the script's path with ?d=<host>.
    origin = f"{script_url.scheme}://{script_url.netloc}"
    post = hc.post(f"{origin}{script_url.path}?d={script_url.hostname}", httpclient.imperva_post(accept_language, origin, page.url), res.payload)
    try:
        reply: TokenReply = json.loads(post.body)
    except ValueError:
        reply = {}
    if not reply.get("token"):
        sys.exit(f"FAIL reese84 POST returned {post.status}: {post.body}")
    # The script stores the token as the reese84 cookie on cookieDomain.
    hc.set_cookie(reply["cookieDomain"], "reese84", reply["token"])


def reload_page(hc: httpclient.Client, page: httpclient.Response) -> None:
    loaded = hc.get(page.url, httpclient.navigate(accept_language, ""))
    if loaded.status != 200:
        sys.exit(f"FAIL page re-GET returned {loaded.status}")
    if challenge_script.search(loaded.body):
        sys.exit("FAIL page re-GET is still the challenge page")


def site_firewall(hc: httpclient.Client, page_url: str) -> None:
    # Insert the relevant requests for your site's firewall. This is up to you and your agent to experiment with.
    # Some sites (DataDome, Akamai) are strict on flow: you might need additional requests here.
    pass


if __name__ == "__main__":
    main()
