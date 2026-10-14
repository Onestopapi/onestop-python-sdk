# DataDome interstitial: the page answers 403 with `var dd={...rt:'i'}`. Load
# the interstitial page and its script, POST the generated form body, store
# the returned datadome cookie and load the page again.
import json
import re
import sys
import time
from http.cookies import SimpleCookie
from typing import TypedDict
from urllib.parse import quote_plus

import httpclient
import onestop_antibot as onestop

api_key = "YOUR_API_KEY"
identifier = ""  # your identifier or account name
page_url = "https://www.example.com/"
accept_language = "en-US,en;q=0.9"

proxy = ""  # your proxy, in the site's country

geo_origin = "https://geo.captcha-delivery.com"

dd_object = re.compile(r"var\s+dd\s*=\s*(\{[^}]*\})")
dd_script = re.compile(r'src="([^"]*interstitial\.[^"]*)"')


class Challenge(TypedDict):
    """The page's dd object."""

    rt: str
    cid: str
    hsh: str
    t: str
    s: int
    e: str
    b: int
    cookie: str


class InterstitialReply(TypedDict, total=False):
    """The interstitial POST's JSON reply."""

    view: str
    cookie: str


def main() -> None:
    hc = httpclient.Client(proxy)
    client, ip = new_client()
    session = new_session(client, ip, page_url)
    page, dd = get_blocked_page(hc)
    geo_url, geo = get_challenge_page(hc, dd)
    solve_interstitial(hc, session, page, geo_url, geo)
    status = reload_page(hc)
    site_firewall(hc, page_url)
    print("PASS interstitial view redirect, page re-GET", status)


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
    if dd["rt"] != "i":
        sys.exit(f"FAIL challenge type {dd['rt']!r} is not the interstitial (t={dd.get('t', '')!r})")
    return page, dd


def get_challenge_page(hc: httpclient.Client, dd: Challenge) -> tuple[str, httpclient.Response]:
    geo_url = "{}/interstitial/?initialCid={}&hash={}&cid={}&referer={}&s={}".format(
        geo_origin, quote_plus(dd["cid"]), quote_plus(dd["hsh"]), quote_plus(dd["cookie"]), quote_plus(page_url), dd["s"]
    )
    if dd.get("e"):
        geo_url += "&e=" + quote_plus(dd["e"])
    geo_url += f"&b={dd['b']}&dm=cd"

    # These pauses are browser pacing between the challenge requests, not the API's sleep.
    time.sleep(0.4)
    geo = hc.get(geo_url, httpclient.frame(accept_language, "cross-site", page_url).storage_access())
    if geo.status != 200:
        sys.exit(f"FAIL interstitial page returned {geo.status}")
    return geo_url, geo


def solve_interstitial(
    hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, geo_url: str, geo: httpclient.Response
) -> None:
    # Without a script tag the bundle is inline and the API reads it from html.
    script = ""
    if match := dd_script.search(geo.body):
        time.sleep(0.2)
        script = hc.get(match[1], httpclient.script(accept_language, "same-site", geo_origin + "/").storage_access()).body

    time.sleep(0.4)
    # script and html are the interstitial's; page_response is the blocked page.
    try:
        res = session.datadome_interstitial(script=script, html=geo.body, page_response=page.body)
    except onestop.OneStopError as e:
        sys.exit(f"FAIL interstitial: {e}")

    time.sleep(1)
    # res.payload is the generated form body.
    post = hc.post(geo_origin + "/interstitial/", httpclient.post(accept_language, "application/x-www-form-urlencoded; charset=UTF-8", geo_origin, geo_url).storage_access(), res.payload)
    try:
        reply: InterstitialReply = json.loads(post.body)
    except ValueError:
        reply = {}
    if reply.get("view") != "redirect":
        sys.exit(f"FAIL interstitial POST returned {post.status}, view {reply.get('view', '')!r}: {post.body}")
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
