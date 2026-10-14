# OneStop Python SDK

Python client for the [OneStop Antibot](https://onestopantibot.com) API. The SDK calls `/generate` and returns typed results; your application fetches the target pages and scripts and sends the generated payloads.

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
    identifier="",  # your identifier or account name
)
ip = client.get_ip()  # set ip_http_client to an httpx.Client through your proxy so this is the proxy's IP
session = client.session(
    site=page_url, referer=page_url, user_agent=user_agent, accept_language="en-US,en;q=0.9", ip=ip,
)
res = session.akamai_sensor(abck=abck, bmsz=bmsz, script=script, script_url=script_url)
# POST res.payload as sensor_data; send res.context on the next call.
```

See [examples/](examples) for full flows per product and TLS client.

Documentation: [onestopantibot.com/dashboard/docs](https://onestopantibot.com/dashboard/docs)
