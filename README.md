# OneStop Python SDK

Python client for the [OneStop Antibot](https://onestopantibot.com) API. The SDK calls `/generate` and returns typed results; your application fetches the target pages and scripts and sends the generated payloads.

Products: Akamai (sensor, SBSD, Pixel, sec-cpt), DataDome (tags, interstitial, slider), Cloudflare (WAF, Turnstile, JSD, precursor), Kasada (p.js, /tl, CD header), Imperva (reese84).

## Install

```sh
python -m pip install onestop-antibot
```

Requires Python 3.10+. Import it as `onestop_antibot`. Package: [PyPI](https://pypi.org/project/onestop-antibot/).

## Quick start

```python
import onestop_antibot as onestop

client = onestop.Client(
    api_key="YOUR_API_KEY",
    identifier="YOUR_IDENTIFIER",  # your identifier or account name
)
ip = client.get_ip()  # set ip_http_client to an httpx.Client through your proxy so this is the proxy's IP
session = client.session(
    site=page_url, referer=page_url, user_agent=user_agent, accept_language="en-US,en;q=0.9", ip=ip,
)
res = session.akamai_sensor(abck=abck, bmsz=bmsz, script=script, script_url=script_url)
# POST res.payload as sensor_data; send res.context on the next call.
```

## Header order

Copy each request's header names, values and order from a browser recording (DevTools, powhttp, Charles) of that request, and set the order explicitly in your TLS client; the examples' headers only show how:

```python
# curl_cffi: requests.Session(impersonate=..., default_headers=False), headers as ordered pairs
session.get(url, headers=[("user-agent", user_agent), ("accept", "*/*")])

# tls_client
session.get(url, headers={"user-agent": user_agent, "accept": "*/*"}, header_order=["user-agent", "accept"])

# wreq: Emulation(..., headers=False)
client.get(url, headers={"user-agent": user_agent, "accept": "*/*"}, orig_headers=["user-agent", "accept"], default_headers=False)
```

See [examples/](https://github.com/Onestopapi/onestop-python-sdk/tree/main/examples) for full flows per product and TLS client.

Documentation: [onestopantibot.com/dashboard/docs](https://onestopantibot.com/dashboard/docs)
