from __future__ import annotations

import random
from abc import ABC, abstractmethod

import httpx

from shared.models import Job, JobSource
from shared.rate_limiter import RateLimiter
from shared.utils import setup_logging

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


class BaseScraper(ABC):
    def __init__(self, rate_limiter: RateLimiter):
        self.rate_limiter = rate_limiter
        self.logger = setup_logging(self.__class__.__name__)

    @abstractmethod
    def get_source(self) -> JobSource:
        ...

    @abstractmethod
    async def search(self, term: str, location: str = "Peru") -> list[Job]:
        ...

    async def search_all_terms(self, terms: list[str], location: str = "Peru") -> list[Job]:
        all_jobs: list[Job] = []
        seen_urls: set[str] = set()

        for term in terms:
            try:
                self.logger.info("Buscando: '%s' en %s", term, self.get_source().value)
                jobs = await self.search(term, location)
                for job in jobs:
                    if job.url not in seen_urls:
                        seen_urls.add(job.url)
                        all_jobs.append(job)
                self.logger.info("  -> %d resultados nuevos", len(jobs))
            except Exception as e:
                self.logger.error("Error buscando '%s' en %s: %s", term, self.get_source().value, e)

        self.logger.info("Total %s: %d trabajos unicos", self.get_source().value, len(all_jobs))
        return all_jobs

    def _random_ua(self) -> str:
        return random.choice(USER_AGENTS)

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        }

    async def _get(self, url: str, client: httpx.AsyncClient, **kwargs) -> httpx.Response:
        await self.rate_limiter.wait(url)
        return await client.get(url, headers=self._headers(), timeout=30, **kwargs)
