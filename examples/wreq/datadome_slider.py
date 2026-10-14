# DataDome slider: the page answers 403 with `var dd={...rt:'c'}`. Load the
# captcha page, its script and both images, GET the captcha check with the
# generated query string, store the datadome cookie and load the page again.
import base64
import json
import re
import sys
from http.cookies import SimpleCookie
from typing import TypedDict
from urllib.parse import quote_plus, urlsplit

import httpclient
import onestop_antibot as onestop

api_key = "YOUR_API_KEY"
identifier = ""  # your identifier or account name
page_url = "https://www.example.com/events/example"
accept_language = "en-GB,en;q=0.9"

proxy = ""  # your proxy, in the site's country

geo_origin = "https://geo.captcha-delivery.com"

dd_object = re.compile(r"var\s+dd\s*=\s*(\{[^}]*\})")
challenge_path = re.compile(r"captchaChallengePath: '([^']+)'")
captcha_script = re.compile(r'<script[^>]*\ssrc="([^"]*captcha[^"]*\.js)"')


class Challenge(TypedDict):
    """The page's dd object."""

    rt: str
    cid: str
    hsh: str
    t: str
    s: int
    e: str
    cookie: str


class CheckReply(TypedDict, total=False):
    """The captcha check's JSON reply."""

    cookie: str


def main() -> None:
    hc = httpclient.Client(proxy)
    client, ip = new_client()
    session = new_session(client, ip, page_url)
    page, dd = get_blocked_page(hc)
    geo_url, geo = get_challenge_page(hc, dd)
    solve_slider(hc, session, page, geo_url, geo)
    status = reload_page(hc)
    site_firewall(hc, page_url)
    print("PASS captcha check cookie, page re-GET", status)


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


def get_blocked_page(hc: httpclient.Client) -> tuple[httpclient.Response, Challenge]:
    page = hc.get(page_url, httpclient.navigate(accept_language, ""))
    match = dd_object.search(page.body)
    if page.status != 403 or not match:
        sys.exit(f"FAIL page returned {page.status} without a DataDome challenge")
    try:
        dd: Challenge = json.loads(match[1].replace("'", '"'))
    except ValueError as e:
        sys.exit(f"FAIL dd object: {e}")
    if dd["rt"] != "c" or dd.get("t") == "bv":
        sys.exit(f"FAIL challenge type {dd['rt']!r} t={dd.get('t', '')!r} is not the slider")
    return page, dd


def get_challenge_page(hc: httpclient.Client, dd: Challenge) -> tuple[str, httpclient.Response]:
    geo_url = "{}/captcha/?initialCid={}&hash={}&cid={}&t={}&referer={}&s={}".format(
        geo_origin, quote_plus(dd["cid"]), quote_plus(dd["hsh"]), quote_plus(dd["cookie"]), dd["t"], quote_plus(page_url), dd["s"]
    )
    if dd.get("e"):
        geo_url += "&e=" + quote_plus(dd["e"])
    geo_url += "&dm=cd"

    u = urlsplit(page_url)
    geo = hc.get(geo_url, httpclient.frame(accept_language, "cross-site", f"{u.scheme}://{u.netloc}/").storage_access())
    if geo.status != 200 or not challenge_path.search(geo.body):
        sys.exit(f"FAIL captcha page returned {geo.status} without the slider challenge")
    return geo_url, geo


def solve_slider(
    hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, geo_url: str, geo: httpclient.Response
) -> None:
    # Without a script tag the bundle is inline and the API reads it from html.
    script = ""
    if match := captcha_script.search(geo.body):
        script = hc.get(match[1], httpclient.script(accept_language, "same-site", geo_origin + "/").storage_access()).body

    # The background is captchaChallengePath (.jpg); the puzzle piece is the
    # same path as .frag.png. Both go to the API as base64.
    path = challenge_path.search(geo.body)[1]
    images = []
    for p in (path, path.replace(".jpg", ".frag.png", 1)):
        image = hc.get(geo.resolve(p), httpclient.image(accept_language, geo_origin, "same-site", geo_origin + "/"))
        if image.status != 200:
            sys.exit(f"FAIL captcha image returned {image.status}")
        images.append(base64.b64encode(image.content).decode())

    # script and html are the captcha page's; page_response is the blocked page.
    try:
        res = session.datadome_slider(
            script=script,
            html=geo.body,
            page_response=page.body,
            background_image=images[0],
            puzzle_piece=images[1],
        )
    except onestop.OneStopError as e:
        sys.exit(f"FAIL slider: {e}")

    # res.payload is the generated check query string.
    answer = hc.get(geo_origin + "/captcha/check" + res.payload, httpclient.post(accept_language, "application/x-www-form-urlencoded; charset=UTF-8", "", geo_url).storage_access())
    try:
        reply: CheckReply = json.loads(answer.body)
    except ValueError:
        reply = {}
    if answer.status != 200 or not reply.get("cookie"):
        sys.exit(f"FAIL captcha check returned {answer.status}: {answer.body}")
    # reply["cookie"] is the datadome Set-Cookie line.
    cookie = SimpleCookie(reply["cookie"])["datadome"]
    hc.set_cookie(cookie["domain"], cookie.key, cookie.value)


def reload_page(hc: httpclient.Client) -> int:
    again = hc.get(page_url, httpclient.navigate(accept_language, page_url))
    if again.status not in (200, 302):
        sys.exit(f"FAIL page re-GET returned {again.status}")
    return again.status


def site_firewall(hc: httpclient.Client, page_url: str) -> None:
    # Insert the relevant requests for your site's firewall. This is up to you and your agent to experiment with.
    # Some sites (DataDome, Akamai) are strict on flow: you might need additional requests here.
    pass


if __name__ == "__main__":
    main()
