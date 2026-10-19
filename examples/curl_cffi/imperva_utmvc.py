# Imperva utmvc: the page loads the utmvc script from
# /_Incapsula_Resource?SWJIYLWA=<hash>. Load the script, store the generated
# value as the ___utmvc cookie, send the SWKMTFSR image request and load the
# page again.
import random
import re
import sys
from urllib.parse import urlsplit

import httpclient
import onestop_antibot as onestop

api_key = "YOUR_API_KEY"
identifier = "YOUR_IDENTIFIER"  # your identifier or account name
page_url = "https://www.example.com/"
accept_language = "en-GB,en;q=0.9"

proxy = ""  # your proxy, in the site's country

utmvc_script = re.compile(r'"([^"]*/_Incapsula_Resource\?SWJIYLWA=[^"]*)"')


def main() -> None:
    hc = httpclient.Client(proxy)
    client, ip = new_client()
    page = get_challenge_page(hc)
    script_url = find_script(page)
    session = new_session(client, ip, page.url)
    script = get_script(hc, page, script_url)
    solve_challenge(hc, session, page, script_url, script)
    send_beacon(hc, page)
    reload_page(hc, page)
    site_firewall(hc, page_url)
    print("PASS ___utmvc cookie set, page re-GET 200")


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


def find_script(page: httpclient.Response) -> str:
    """Returns the utmvc script the page loads from /_Incapsula_Resource?SWJIYLWA=<hash>."""
    match = utmvc_script.search(page.body)
    if not match:
        sys.exit(f"FAIL page returned {page.status} without an Imperva utmvc script")
    return page.resolve(match[1])


def get_script(hc: httpclient.Client, page: httpclient.Response, script_url: str) -> str:
    res = hc.get(script_url, httpclient.script(accept_language, "same-origin", page.url))
    if res.status != 200:
        sys.exit(f"FAIL script returned {res.status}")
    return res.body


def solve_challenge(
    hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, script_url: str, script: str
) -> None:
    cookies = hc.cookies(page.url, "incap_ses_")
    try:
        res = session.imperva_utmvc(script_url, script, cookies)
    except onestop.OneStopError as e:
        sys.exit(f"FAIL imperva utmvc: {e}")
    # The script stores res.payload as the ___utmvc cookie on the page host, path /.
    hc.set_cookie(urlsplit(page.url).hostname, "___utmvc", res.payload)


def send_beacon(hc: httpclient.Client, page: httpclient.Response) -> None:
    """The image request the script makes after setting ___utmvc; e is Math.random()."""
    beacon = page.resolve(f"/_Incapsula_Resource?SWKMTFSR=1&e={random.random()}")
    hc.get(beacon, httpclient.image(accept_language, "", "same-origin", page.url))


def reload_page(hc: httpclient.Client, page: httpclient.Response) -> None:
    loaded = hc.get(page.url, httpclient.navigate(accept_language, ""))
    if loaded.status != 200:
        sys.exit(f"FAIL page re-GET returned {loaded.status}")


def site_firewall(hc: httpclient.Client, page_url: str) -> None:
    # Insert the relevant requests for your site's firewall. This is up to you and your agent to experiment with.
    # Some sites (DataDome, Akamai) are strict on flow: you might need additional requests here.
    pass


if __name__ == "__main__":
    main()
