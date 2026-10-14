# Cloudflare WAF: the page answers 403 with the managed challenge. Load the
# challenge script, then send the requests each step returns until the form
# POST that sets cf_clearance.
import re
import struct
import sys

import httpclient
import onestop_antibot as onestop

api_key = "YOUR_API_KEY"
identifier = ""  # your identifier or account name
page_url = "https://www.example.com/login"
accept_language = "en-US,en;q=0.9"

proxy = ""  # your proxy, in the site's country

challenge_script = re.compile(r"src = '(/cdn-cgi/challenge-platform/[^']+)'")
challenge_token = re.compile(r'__cf_chl_rt_tk=([^"&]+)')


def main() -> None:
    hc = httpclient.Client(proxy)
    client, ip = new_client()
    session = new_session(client, ip, page_url)
    first = get_challenge_page(hc)
    run_challenge_loop(hc, session, first)
    site_firewall(hc, page_url)
    print("PASS cf_clearance set")


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
    """Returns the first call: the challenge page and its script."""
    page = hc.get(page_url, httpclient.navigate(accept_language, ""))
    # The challenge page has the script path (src = '...') and the
    # __cf_chl_rt_tk token.
    script_match = challenge_script.search(page.body)
    token_match = challenge_token.search(page.body)
    if not script_match or not token_match:
        sys.exit(f"FAIL page returned {page.status} without a Cloudflare challenge")
    script_url = page.resolve(script_match[1])
    script = hc.get(script_url, httpclient.challenge_script(accept_language, page_url + "?__cf_chl_rt_tk=" + token_match[1]))
    return onestop.CloudflareCall(html=page.body, script=script.body, script_url=script_url)


def run_challenge_loop(hc: httpclient.Client, session: onestop.Session, call: onestop.CloudflareCall) -> None:
    """Sends each step's requests; each reply goes back on the next call, by its purpose. The form POST sets
    cf_clearance."""
    frame_url = ""
    try:
        step = session.cloudflare_waf(**call)
        while not step.token:
            call = onestop.CloudflareCall(context=step.context)
            for r in step.requests:
                if r.purpose == "form":
                    hc.follow_redirects(False)
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
                elif r.purpose == "form":
                    if not hc.cookie(page_url, "cf_clearance"):
                        sys.exit(f"FAIL form POST returned {res.status} without cf_clearance")
                    return
            step = session.cloudflare_waf(**call)
    except onestop.OneStopError as e:
        sys.exit(f"FAIL WAF: {e}")
    sys.exit("FAIL the challenge ended without a form POST")


def site_firewall(hc: httpclient.Client, page_url: str) -> None:
    # Insert the relevant requests for your site's firewall. This is up to you and your agent to experiment with.
    # Some sites (DataDome, Akamai) are strict on flow: you might need additional requests here.
    pass


if __name__ == "__main__":
    main()
