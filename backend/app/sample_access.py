"""Explicit public synthetic routes and bounded, single-process request throttling."""

import math
import re
import time
from collections import OrderedDict, deque
from threading import Lock

from app.samples import SAMPLES


def is_public_sample(method: str, path: str) -> bool:
    if method == "GET" and path == "/api/samples":
        return True
    if method == "POST":
        match = re.fullmatch(r"/api/runs/sample/([a-z-]+)", path)
        if match:
            return match[1] in SAMPLES
        match = re.fullmatch(r"/api/runs/sample-([a-z-]+)/verify", path)
        return bool(match and match[1] in SAMPLES)
    if method == "GET":
        match = re.fullmatch(r"/api/runs/sample-([a-z-]+)(?:/report)?", path)
        if match:
            return match[1] in SAMPLES
        match = re.fullmatch(
            r"/api/media/sample-([a-z-]+)/(?:original\.mp4|evidence_frame_[0-9_.]+\.jpg)",
            path,
        )
        return bool(match and match[1] in SAMPLES)
    return False


class SampleRateLimiter:
    """30 requests per rolling minute per socket IP; never trust forwarded headers.

    At most 4096 recent clients and 30 timestamps per client are retained. This
    is a best-effort single-worker guard, not a distributed abuse prevention layer.
    """

    def __init__(self) -> None:
        self.clients: OrderedDict[str, deque[float]] = OrderedDict()
        self.lock = Lock()

    def retry_after(self, ip: str) -> int:
        now = time.monotonic()
        with self.lock:
            while self.clients:
                first = next(iter(self.clients))
                if self.clients[first][-1] > now - 60:
                    break
                self.clients.popitem(last=False)
            if ip not in self.clients:
                if len(self.clients) >= 4096:
                    self.clients.popitem(last=False)
                self.clients[ip] = deque()
            hits = self.clients[ip]
            while hits and hits[0] <= now - 60:
                hits.popleft()
            if len(hits) >= 30:
                return max(1, math.ceil(hits[0] + 60 - now))
            hits.append(now)
            self.clients.move_to_end(ip)
        return 0
