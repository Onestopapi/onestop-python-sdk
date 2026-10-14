# Akamai: load the homepage, send the SBSD payloads (mode f, then t), then
# POST sensor data until the sensor is accepted.
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
accept_language = "en-US,en;q=0.9"

proxy = ""  # your proxy, in the site's country

sensor_script = re.compile(r'<script type="text/javascript"[^>]*src="([A-Za-z0-9/_-]+)"></script>')
sbsd_script = re.compile(r'<script[^>]*src="([^"]*\?v=[^"]*)"')


class SbsdBody(TypedDict):
    """The JSON body of an SBSD POST."""

    body: str


class SensorBody(TypedDict):
    """The JSON body of a sensor POST."""

    sensor_data: str


def main() -> None:
    hc = httpclient.Client(proxy)
    client, ip = new_client()
    page = get_home_page(hc)
    sensor_url, sbsd_url = find_scripts(page)
    session = new_session(client, ip, page.url)
    sensor, sbsd = get_scripts(hc, page, sensor_url, sbsd_url)
    solve_sbsd_passive(hc, session, page, sbsd_url, sbsd)
    post_sensors(hc, session, page, sensor_url, sensor)
    site_firewall(hc, page_url)
    print("PASS sensor accepted")


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


def get_home_page(hc: httpclient.Client) -> httpclient.Response:
    return hc.get(page_url, httpclient.navigate(accept_language, "").no_cache())


def find_scripts(page: httpclient.Response) -> tuple[SplitResult, SplitResult]:
    sensor_match = sensor_script.search(page.body)
    sbsd_match = sbsd_script.search(page.body)
    if page.status != 200 or not sensor_match or not sbsd_match:
        sys.exit(f"FAIL homepage returned {page.status} without the sensor and SBSD scripts")
    return urlsplit(page.resolve(sensor_match[1])), urlsplit(page.resolve(sbsd_match[1]))


def get_scripts(
    hc: httpclient.Client, page: httpclient.Response, sensor_url: SplitResult, sbsd_url: SplitResult
) -> tuple[str, str]:
    sensor = hc.get(sensor_url.geturl(), httpclient.script(accept_language, "same-origin", page.url).no_cache()).body
    sbsd = hc.get(sbsd_url.geturl(), httpclient.script(accept_language, "same-origin", page.url).no_cache()).body
    return sensor, sbsd


def solve_sbsd_passive(
    hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, sbsd_url: SplitResult, script: str
) -> None:
    u = urlsplit(page.url)
    origin = f"{u.scheme}://{u.netloc}"
    # uuid is the v= value of the SBSD script URL; mode t sends f's context.
    uuid = parse_qs(sbsd_url.query)["v"][0]
    context = ""
    for mode in ("f", "t"):
        try:
            res = session.sbsd_payload(
                uuid=uuid,
                sbsd_cookie=hc.cookie(page.url, "bm_so", "sbsd_o"),  # cookie set by the page
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


def post_sensors(
    hc: httpclient.Client, session: onestop.Session, page: httpclient.Response, sensor_url: SplitResult, script: str
) -> None:
    origin = f"{sensor_url.scheme}://{sensor_url.netloc}"
    # The first sensor call sends the script, every later call the previous
    # context instead. _abck and bm_sz are cookies set by the site.
    context = ""
    for _ in range(8):
        try:
            res = session.akamai_sensor(
                abck=hc.cookie(page.url, "_abck"),
                bmsz=hc.cookie(page.url, "bm_sz"),
                script=script,
                script_url=sensor_url.geturl(),
                context=context,
            )
        except onestop.OneStopError as e:
            sys.exit(f"FAIL sensor: {e}")
        body = json.dumps(SensorBody(sensor_data=res.payload), separators=(",", ":"))
        post = hc.post(sensor_url.geturl(), httpclient.post(accept_language, "text/plain;charset=UTF-8", origin, page.url).no_cache(), body)
        if post.status not in (200, 201):
            sys.exit(f"FAIL sensor POST returned {post.status}")
        # Accepted: _abck contains ~0~ or the reply is the 17-byte ack.
        if "~0~" in hc.cookie(page.url, "_abck") or len(post.content) == 17:
            return
        script, context = "", res.context
    sys.exit("FAIL sensor not accepted after 8 POSTs")


def site_firewall(hc: httpclient.Client, page_url: str) -> None:
    # Insert the relevant requests for your site's firewall. This is up to you and your agent to experiment with.
    # Some sites (DataDome, Akamai) are strict on flow: you might need additional requests here.
    # If a later request resets _abck, run one more sensor call with the last context plus one POST.
    pass


if __name__ == "__main__":
    main()
