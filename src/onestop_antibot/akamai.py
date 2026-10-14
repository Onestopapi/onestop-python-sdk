import hashlib
import math
import random

from .errors import OneStopError

_HEX = "0123456789abcdef"


def akamai_sec_cpt_payload(*, cookie: str, token: str, nonce: str, timestamp: int, difficulty: int, count: int) -> str:
    """Solve the sec-cpt crypto challenge locally; returns the body to POST to /_sec/verify?provider=<provider> (crypto or adaptive)."""
    prefix, tilde, _ = cookie.partition("~")
    if not tilde:
        raise OneStopError(0, "", 'akamai: sec_cpt cookie must contain "~"')
    if not token or not nonce or timestamp <= 0:
        raise OneStopError(0, "", "akamai: token, nonce and a positive timestamp are required")
    if difficulty <= 0 or count <= 0:
        raise OneStopError(0, "", "akamai: difficulty and count must be positive")
    seed = f"{prefix}{timestamp}{nonce}"
    answers = []
    for i in range(count):
        target = difficulty + i
        base = f"{seed}{target}"
        while True:
            answer = _candidate(random.getrandbits(53) / (1 << 53))
            remainder = 0
            for b in hashlib.sha256(f"{base}{answer}".encode()).digest():
                remainder = ((remainder << 8) | b) % target
            if remainder == 0:
                answers.append(answer)
                break
    return '{"token": "%s", "answers": ["%s"]}' % (token, '","'.join(answers))


def _candidate(value: float) -> str:
    """Format value in [0, 1) the way the browser's Number.prototype.toString(16) does."""
    delta = max(math.nextafter(0.0, 1.0), 0.5 * (math.nextafter(value, 1.0) - value))
    fraction = value
    digits: list[int] = []
    while fraction >= delta:
        fraction *= 16
        delta *= 16
        digit = int(fraction)
        fraction -= digit
        digits.append(digit)
        if (fraction > 0.5 or (fraction == 0.5 and digit & 1)) and fraction + delta > 1:
            while digits and digits[-1] == 15:
                digits.pop()
            if not digits:
                return "1"
            digits[-1] += 1
            break
    if not digits:
        return "0"
    return "0." + "".join(_HEX[d] for d in digits)
