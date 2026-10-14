import hashlib
import json
import math
import random
import secrets
import time
from typing import TypedDict

from .errors import OneStopError


class CdMobile(TypedDict):
    """The x-kpsdk-cd header JSON; field order is the wire order."""

    workTime: int
    rst: int
    duration: float
    id: str
    st: int
    answers: list[int]
    d: int


class CdDesktop(TypedDict):
    workTime: int
    id: str
    answers: list[int]
    duration: float
    d: int
    st: int
    rst: int


def kasada_cd_header(
    *,
    st: int,
    rst: int,
    mobile: bool = False,
    ct: str = "",
    crypto_customer_key: str = "",
    seed_suffix: str = "",
    difficulty: int,
    subchallenge_count: int,
) -> str:
    """Compute the Kasada CD header locally. No client or network is used."""
    if st <= 0 or rst < st:
        raise OneStopError(0, "", "kasada: require positive ST and RST >= ST")
    if difficulty <= 0 or subchallenge_count <= 0:
        raise OneStopError(0, "", "kasada: difficulty and subchallenge count must be positive")
    platform = b"tp-v2-input"
    if not mobile:
        ct_bytes = ct.encode()
        if len(ct_bytes) < 16:
            raise OneStopError(0, "", "kasada: desktop CT must contain at least 16 bytes")
        platform += ct_bytes[:16]
    random_id = secrets.token_hex(16)
    work_time = time.time_ns() // 1_000_000 - (random.randrange(41) + 10)
    seed = platform + f", {work_time}, {random_id}".encode()
    if crypto_customer_key:
        seed += f", {crypto_customer_key}".encode()
    if seed_suffix:
        seed += f", {seed_suffix}".encode()
    digest = hashlib.sha256(seed).hexdigest()
    target = difficulty / subchallenge_count
    answers = []
    for _ in range(subchallenge_count):
        nonce = 1
        while True:
            candidate = hashlib.sha256(f"{nonce}, {digest}".encode()).hexdigest()
            if float(0x10000000000000) / float(int(candidate[:13], 16) + 1) >= target:
                answers.append(nonce)
                digest = candidate
                break
            nonce += 1
    duration = math.floor((0.5 + random.random() * 1.5) * 10 + 0.5) / 10
    dur = int(duration) if duration.is_integer() else duration  # the header carries 2, not 2.0
    if mobile:
        header: CdMobile | CdDesktop = CdMobile(
            workTime=work_time, rst=rst, duration=dur, id=random_id, st=st, answers=answers, d=rst - st
        )
    else:
        header = CdDesktop(workTime=work_time, id=random_id, answers=answers, duration=dur, d=rst - st, st=st, rst=rst)
    return json.dumps(header, separators=(",", ":"))
