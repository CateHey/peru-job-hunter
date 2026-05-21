from __future__ import annotations

import asyncio
from datetime import datetime

from shared.models import Job, JobSource, JobType
from shared.rate_limiter import RateLimiter
from shared.scraper_base import BaseScraper


class IndeedJobSpyScraper(BaseScraper):
    def __init__(self, rate_limiter: RateLimiter, results_wanted: int = 50):
        super().__init__(rate_limiter)
        self.results_wanted = results_wanted

    def get_source(self) -> JobSource:
        return JobSource.INDEED

    async def search(self, term: str, location: str = "Peru") -> list[Job]:
        try:
            from jobspy import scrape_jobs
        except ImportError:
            self.logger.error("python-jobspy no instalado. Ejecuta: pip install python-jobspy")
            return []

        try:
            df = await asyncio.to_thread(
                scrape_jobs,
                site_name=["indeed"],
                search_term=term,
                location=location,
                country_indeed="Peru",
                results_wanted=self.results_wanted,
                hours_old=720,  # last 30 days
            )
        except Exception as e:
            self.logger.error("Error con python-jobspy: %s", e)
            return []

        if df is None or df.empty:
            return []

        jobs: list[Job] = []
        for _, row in df.iterrows():
            try:
                title = str(row.get("title", ""))
                if not title:
                    continue

                date_posted = None
                raw_date = row.get("date_posted")
                if raw_date is not None:
                    try:
                        if isinstance(raw_date, str):
                            date_posted = datetime.fromisoformat(raw_date)
                        elif hasattr(raw_date, "to_pydatetime"):
                            date_posted = raw_date.to_pydatetime()
                    except (ValueError, TypeError):
                        pass

                job_type = JobType.UNKNOWN
                raw_type = str(row.get("job_type", "")).lower()
                if "intern" in raw_type or "practicante" in title.lower():
                    job_type = JobType.INTERNSHIP
                elif "full" in raw_type:
                    job_type = JobType.FULLTIME
                elif "part" in raw_type:
                    job_type = JobType.PARTTIME
                elif "contract" in raw_type:
                    job_type = JobType.CONTRACT

                salary = None
                min_sal = row.get("min_amount")
                max_sal = row.get("max_amount")
                currency = row.get("currency", "")
                if min_sal and max_sal:
                    salary = f"{currency} {min_sal}-{max_sal}"
                elif min_sal:
                    salary = f"{currency} {min_sal}+"

                jobs.append(Job(
                    title=title,
                    company=str(row.get("company", "Desconocido")),
                    location=str(row.get("location", "")),
                    url=str(row.get("job_url", "")),
                    description=str(row.get("description", "")),
                    date_posted=date_posted,
                    salary=salary,
                    source=JobSource.INDEED,
                    job_type=job_type,
                    sources_found=["indeed"],
                ))
            except Exception as e:
                self.logger.debug("Error parseando fila Indeed: %s", e)
                continue

        return jobs
