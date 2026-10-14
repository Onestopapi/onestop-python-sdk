# Cloudflare Turnstile: load the widget's api.js and its iframe, then send
# the requests each step returns until the API returns the token.
import random
import struct
import sys
from urllib.parse import urlsplit

import httpclient
import onestop_antibot as onestop

api_key = "YOUR_API_KEY"
identifier = ""  # your identifier or account name
page_url = "https://www.example.com/event"
site_key = "YOUR_TURNSTILE_SITE_KEY"  # from the page's turnstile.render options
action = "YOUR_TURNSTILE_ACTION"
c_data = "YOUR_TURNSTILE_CDATA"
accept_language = "en-US,en;q=0.9"

proxy = ""  # your proxy, in the site's country


def main() -> None:
    hc = httpclient.Client(proxy)
    client, ip = new_client()
    session = new_session(client, ip, page_url)
    first = get_challenge_page(hc)
    token = run_challenge_loop(hc, session, first)
    site_firewall(hc, page_url, token)
    print("PASS Turnstile token returned")


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


def get_challenge_page(hc: httpclient.Client) -> onestop.CloudflareCall:
    """Returns the first call: the widget iframe, its final URL and its cf-ray header."""
    page = urlsplit(page_url)
    api = hc.get(
        "https://challenges.cloudflare.com/turnstile/v0/api.js",
        httpclient.script(accept_language, "cross-site", f"{page.scheme}://{page.netloc}/").storage_access(),
    )
    # api.js redirects to /turnstile/v0/<mode>/<version>/api.js.
    segments = urlsplit(api.url).path.split("/")
    if len(segments) != 6:
        sys.exit(f"FAIL api.js resolved to {api.url}")
    mode = segments[3]
    # rch is a random 5-character render id.
    rch = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=5))
    frame = hc.get(
        f"https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/{mode}/turnstile/f/av0/rch/{rch}/{site_key}/light/fbE/new/normal?lang=auto",
        httpclient.frame(accept_language, "cross-site", "").storage_access(),
    )
    if frame.status != 200:
        sys.exit(f"FAIL widget iframe returned {frame.status}")
    return onestop.CloudflareCall(
        html=frame.body,
        script_url=api.url,
        iframe_url=frame.url,
        bytecode_ray_id=frame.header("cf-ray"),
        action=action,
        c_data=c_data,
    )


def run_challenge_loop(hc: httpclient.Client, session: onestop.Session, call: onestop.CloudflareCall) -> str:
    """Sends each step's requests; each reply goes back on the next call, by its purpose, until the API returns the
    token."""
    frame_url = call["iframe_url"]
    try:
        step = session.cloudflare_turnstile(**call)
        while not step.token:
            call = onestop.CloudflareCall(context=step.context, action=action, c_data=c_data)
            for r in step.requests:
                res = hc.do(r.method, r.url, httpclient.cloudflare(r, accept_language, page_url, frame_url), r.body)
                if r.purpose == "challenge":
                    if res.status != 200:
                        sys.exit(f"FAIL challenge request returned {res.status}")
                    call["response"] = res.body
                elif r.purpose == "iframe":
                    frame_url = res.url
                    call["html"] = res.body
                    call["iframe_url"] = res.url
                    call["bytecode_ray_id"] = res.header("cf-ray")
                elif r.purpose == "image":
                    if res.content[:8] != b"\x89PNG\r\n\x1a\n":
                        sys.exit("FAIL challenge image: not a PNG")
                    call["image_width"], call["image_height"] = struct.unpack(">II", res.content[16:24])  # PNG IHDR
                elif r.purpose == "pat":
                    call["pat_status"] = res.status  # a 4xx is normal
            step = session.cloudflare_turnstile(**call)
    except onestop.OneStopError as e:
        sys.exit(f"FAIL Turnstile: {e}")
    return step.token


def site_firewall(hc: httpclient.Client, page_url: str, token: str) -> None:
    # Insert the relevant requests for your site's firewall. This is up to you and your agent to experiment with.
    # Some sites (DataDome, Akamai) are strict on flow: you might need additional requests here.
    pass


if __name__ == "__main__":
    main()
