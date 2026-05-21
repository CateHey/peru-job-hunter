from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

import httpx

from shared.models import Job, JobSource, JobType
from shared.rate_limiter import RateLimiter
from shared.scraper_base import BaseScraper


class GetOnBoardScraper(BaseScraper):
    BASE_API = "https://www.getonbrd.com/api/v0"
    PERU_COUNTRY_ID = 4
    MAX_PAGES = 5
    PER_PAGE = 25

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(rate_limiter)

    def get_source(self) -> JobSource:
        return JobSource.GETONBOARD

    async def search(self, term: str, location: str = "Peru") -> list[Job]:
        jobs: list[Job] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(follow_redirects=True) as client:
            for page in range(1, self.MAX_PAGES + 1):
                url = (
                    f"{self.BASE_API}/search/jobs"
                    f"?query={quote_plus(term)}"
                    f"&country_id={self.PERU_COUNTRY_ID}"
                    f"&page={page}"
                    f"&per_page={self.PER_PAGE}"
                )

                try:
                    resp = await self._get(url, client)

                    if resp.status_code == 429:
                        self.logger.warning("Rate limited por GetOnBoard, deteniendo paginacion")
                        break
                    if resp.status_code != 200:
                        self.logger.warning("HTTP %d para GetOnBoard: %s", resp.status_code, url)
                        break

                    data = resp.json()
                    results = data if isinstance(data, list) else data.get("data", data.get("results", []))

                    if not results:
                        break

                    for item in results:
                        try:
                            job = self._parse_job(item)
                            if job and job.url not in seen_ids:
                                seen_ids.add(job.url)
                                jobs.append(job)
                        except Exception as e:
                            self.logger.debug("Error parseando job GetOnBoard: %s", e)

                    if len(results) < self.PER_PAGE:
                        break

                except httpx.HTTPStatusError as e:
                    self.logger.error("HTTP error GetOnBoard: %s", e)
                    break
                except Exception as e:
                    self.logger.error("Error en pagina %d GetOnBoard: %s", page, e)
                    break

        return jobs

    def _parse_job(self, item: dict) -> Job | None:
        if isinstance(item, dict) and "attributes" in item:
            attrs = item["attributes"]
            job_id = item.get("id", "")
        else:
            attrs = item
            job_id = item.get("id", item.get("slug", ""))

        title = attrs.get("title", "")
        if not title:
            return None

        company_data = attrs.get("company", {})
        if isinstance(company_data, dict):
            company = company_data.get("name", company_data.get("title", ""))
        else:
            company = str(company_data) if company_data else ""

        city = attrs.get("city", "")
        country = attrs.get("country", "")
        modality = attrs.get("modality", "")
        location_parts = [p for p in [city, country] if p]
        if modality:
            location_parts.append(f"({modality})")
        location = ", ".join(location_parts)

        slug = attrs.get("slug", job_id)
        url = attrs.get("url", "")
        if not url and slug:
            url = f"https://www.getonbrd.com/jobs/{slug}"
        if not url:
            url = f"https://www.getonbrd.com/jobs/{job_id}"

        description = attrs.get("description", attrs.get("description_headline", ""))

        date_posted = None
        for date_field in ("published_at", "created_at", "activated_at"):
            raw_date = attrs.get(date_field)
            if raw_date:
                date_posted = self._parse_date(raw_date)
                if date_posted:
                    break

        seniority = (attrs.get("seniority", "") or "").lower()
        job_type = JobType.UNKNOWN
        title_lower = title.lower()
        if any(w in title_lower for w in ["practicante", "intern", "pasantia", "prácticas"]):
            job_type = JobType.INTERNSHIP
        elif "part" in seniority or "part-time" in title_lower:
            job_type = JobType.PARTTIME

        salary = None
        min_sal = attrs.get("min_salary")
        max_sal = attrs.get("max_salary")
        currency = attrs.get("salary_currency", "USD")
        if min_sal and max_sal:
            salary = f"{currency} {min_sal}-{max_sal}"
        elif min_sal:
            salary = f"{currency} {min_sal}+"

        return Job(
            title=title,
            company=company,
            location=location,
            url=url,
            description=description[:500] if description else "",
            date_posted=date_posted,
            salary=salary,
            source=JobSource.GETONBOARD,
            job_type=job_type,
            sources_found=["getonboard"],
        )

    @staticmethod
    def _parse_date(raw: str | int) -> datetime | None:
        if isinstance(raw, (int, float)):
            try:
                return datetime.fromtimestamp(raw, tz=timezone.utc)
            except (ValueError, OSError):
                return None

        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(raw), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
