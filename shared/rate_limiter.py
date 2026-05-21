from __future__ import annotations

import asyncio
import random
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx


class RateLimiter:
    def __init__(self, min_delay: float = 1.5, max_delay: float = 3.0):
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._last_request: dict[str, float] = {}
        self._robot_parsers: dict[str, RobotFileParser | None] = {}
        self._lock = asyncio.Lock()

    def _get_domain(self, url: str) -> str:
        return urlparse(url).netloc

    async def _load_robots(self, domain: str) -> RobotFileParser | None:
        if domain in self._robot_parsers:
            return self._robot_parsers[domain]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://{domain}/robots.txt")
                if resp.status_code == 200:
                    rp = RobotFileParser()
                    rp.parse(resp.text.splitlines())
                    self._robot_parsers[domain] = rp
                    return rp
        except Exception:
            pass
        self._robot_parsers[domain] = None
        return None

    async def can_fetch(self, url: str, user_agent: str = "*") -> bool:
        domain = self._get_domain(url)
        rp = await self._load_robots(domain)
        if rp is None:
            return True
        return rp.can_fetch(user_agent, url)

    async def wait(self, url: str) -> None:
        domain = self._get_domain(url)
        async with self._lock:
            now = time.monotonic()
            last = self._last_request.get(domain, 0)
            delay = random.uniform(self._min_delay, self._max_delay)
            elapsed = now - last
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
            self._last_request[domain] = time.monotonic()
