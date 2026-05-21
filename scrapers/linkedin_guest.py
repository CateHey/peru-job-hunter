from __future__ import annotations

import re
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from shared.models import Job, JobSource, JobType
from shared.rate_limiter import RateLimiter
from shared.scraper_base import BaseScraper
from shared.utils import normalize_text, parse_relative_date


class LinkedInGuestScraper(BaseScraper):
    SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    PAGE_SIZE = 25
    MAX_PAGES = 10

    def __init__(self, rate_limiter: RateLimiter, max_pages: int = 5):
        super().__init__(rate_limiter)
        self.max_pages = min(max_pages, self.MAX_PAGES)

    def get_source(self) -> JobSource:
        return JobSource.LINKEDIN

    async def search(self, term: str, location: str = "Peru") -> list[Job]:
        jobs: list[Job] = []

        async with httpx.AsyncClient(follow_redirects=True) as client:
            for page in range(self.max_pages):
                start = page * self.PAGE_SIZE
                params = {
                    "keywords": term,
                    "location": location,
                    "start": str(start),
                    "f_TPR": "r2592000",  # last 30 days
                }

                url = self.SEARCH_URL
                try:
                    await self.rate_limiter.wait(url)
                    resp = await client.get(
                        url,
                        params=params,
                        headers=self._headers(),
                        timeout=30,
                    )
                    if resp.status_code == 429:
                        self.logger.warning("LinkedIn rate limit alcanzado, deteniendo paginacion")
                        break
                    if resp.status_code != 200:
                        self.logger.warning("HTTP %d de LinkedIn", resp.status_code)
                        break

                    page_jobs = self._parse_search_results(resp.text)
                    if not page_jobs:
                        break
                    jobs.extend(page_jobs)
                except Exception as e:
                    self.logger.error("Error en pagina %d: %s", page, e)
                    break

        return jobs

    def _parse_search_results(self, html: str) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[Job] = []

        cards = soup.select("li") or soup.select("div.base-card")

        for card in cards:
            try:
                title_el = (
                    card.select_one("h3.base-search-card__title")
                    or card.select_one("h3")
                    or card.select_one("a.base-card__full-link")
                )
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)

                link_el = card.select_one("a.base-card__full-link") or card.select_one("a[href*='linkedin.com/jobs']")
                if not link_el:
                    continue

                url = link_el.get("href", "").split("?")[0]
                if not url:
                    continue

                job_id_match = re.search(r"/view/(\d+)", url) or re.search(r"-(\d+)\?", link_el.get("href", ""))
                job_id = job_id_match.group(1) if job_id_match else ""

                company_el = card.select_one("h4.base-search-card__subtitle") or card.select_one("a.hidden-nested-link")
                company = company_el.get_text(strip=True) if company_el else "Desconocido"

                location_el = card.select_one("span.job-search-card__location")
                location = location_el.get_text(strip=True) if location_el else ""

                date_el = card.select_one("time")
                date_posted = None
                if date_el:
                    datetime_attr = date_el.get("datetime")
                    if datetime_attr:
                        try:
                            from datetime import datetime
                            date_posted = datetime.fromisoformat(datetime_attr)
                        except ValueError:
                            date_posted = parse_relative_date(date_el.get_text(strip=True))
                    else:
                        date_posted = parse_relative_date(date_el.get_text(strip=True))

                job_type = JobType.UNKNOWN
                if any(w in title.lower() for w in ["intern", "practicante", "prácticas", "pasantía"]):
                    job_type = JobType.INTERNSHIP

                jobs.append(Job(
                    title=title,
                    company=company,
                    location=location,
                    url=url,
                    description="",
                    date_posted=date_posted,
                    source=JobSource.LINKEDIN,
                    job_type=job_type,
                    sources_found=["linkedin"],
                ))
            except Exception as e:
                self.logger.debug("Error parseando card LinkedIn: %s", e)
                continue

        return jobs
