from __future__ import annotations

from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from shared.models import Job, JobSource, JobType
from shared.rate_limiter import RateLimiter
from shared.scraper_base import BaseScraper
from shared.utils import normalize_text, parse_relative_date


class CompuTrabajoScraper(BaseScraper):
    BASE_URL = "https://pe.computrabajo.com"

    def __init__(self, rate_limiter: RateLimiter, max_pages: int = 5):
        super().__init__(rate_limiter)
        self.max_pages = max_pages

    def get_source(self) -> JobSource:
        return JobSource.COMPUTRABAJO

    async def search(self, term: str, location: str = "Peru") -> list[Job]:
        jobs: list[Job] = []
        encoded_term = quote_plus(term)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            for page in range(1, self.max_pages + 1):
                url = f"{self.BASE_URL}/trabajo-de-{encoded_term}"
                if page > 1:
                    url += f"?p={page}"

                if not await self.rate_limiter.can_fetch(url):
                    self.logger.warning("robots.txt bloquea: %s", url)
                    break

                try:
                    resp = await self._get(url, client)
                    if resp.status_code != 200:
                        self.logger.warning("HTTP %d para %s", resp.status_code, url)
                        break

                    page_jobs = self._parse_listing_page(resp.text)
                    if not page_jobs:
                        break
                    jobs.extend(page_jobs)
                except Exception as e:
                    self.logger.error("Error en pagina %d: %s", page, e)
                    break

        return jobs

    def _parse_listing_page(self, html: str) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[Job] = []

        articles = soup.select("article.box_offer") or soup.select("div.box_offer")
        if not articles:
            articles = soup.select("article[data-title]")

        for article in articles:
            try:
                title_el = (
                    article.select_one("a.js-o-link")
                    or article.select_one("h2 a")
                    or article.select_one("a[href*='/oferta-de-trabajo/']")
                )
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

                company_el = (
                    article.select_one("a.fc_base")
                    or article.select_one("span.b_cname")
                    or article.select_one("a[href*='/empresa/']")
                )
                company = company_el.get_text(strip=True) if company_el else "Empresa Confidencial"

                location_el = (
                    article.select_one("span.b_location")
                    or article.select_one("p.fs16")
                )
                location = location_el.get_text(strip=True) if location_el else ""

                date_el = article.select_one("span.b_date") or article.select_one("p.fs13")
                date_posted = None
                if date_el:
                    date_posted = parse_relative_date(date_el.get_text(strip=True))

                desc_el = article.select_one("p.ellipsis") or article.select_one("div.bp_desc")
                description = normalize_text(desc_el.get_text()) if desc_el else ""

                job_type = JobType.UNKNOWN
                text_lower = f"{title} {description}".lower()
                if any(w in text_lower for w in ["practicante", "prácticas", "intern", "pasantía"]):
                    job_type = JobType.INTERNSHIP

                jobs.append(Job(
                    title=title,
                    company=company,
                    location=location,
                    url=url,
                    description=description,
                    date_posted=date_posted,
                    source=JobSource.COMPUTRABAJO,
                    job_type=job_type,
                    sources_found=["computrabajo"],
                ))
            except Exception as e:
                self.logger.debug("Error parseando articulo: %s", e)
                continue

        return jobs
