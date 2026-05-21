from __future__ import annotations

from rapidfuzz import fuzz

from shared.models import Job
from shared.utils import normalize_url, setup_logging

logger = setup_logging("deduplicator")


def deduplicate_jobs(jobs: list[Job], fuzzy_threshold: float = 85.0) -> list[Job]:
    if not jobs:
        return []

    by_url: dict[str, Job] = {}
    for job in jobs:
        norm = normalize_url(job.url)
        if norm in by_url:
            existing = by_url[norm]
            existing.sources_found = list(set(existing.sources_found + job.sources_found))
            if len(job.description) > len(existing.description):
                existing.description = job.description
            if job.salary and not existing.salary:
                existing.salary = job.salary
            if job.date_posted and not existing.date_posted:
                existing.date_posted = job.date_posted
        else:
            by_url[norm] = job

    unique = list(by_url.values())

    merged: list[Job] = []
    used: set[int] = set()

    for i, job_a in enumerate(unique):
        if i in used:
            continue

        for j in range(i + 1, len(unique)):
            if j in used:
                continue

            job_b = unique[j]
            title_sim = fuzz.token_sort_ratio(job_a.title.lower(), job_b.title.lower())
            company_sim = fuzz.token_sort_ratio(job_a.company.lower(), job_b.company.lower())
            combined = (title_sim * 0.6) + (company_sim * 0.4)

            if combined >= fuzzy_threshold:
                job_a.sources_found = list(set(job_a.sources_found + job_b.sources_found))
                if len(job_b.description) > len(job_a.description):
                    job_a.description = job_b.description
                if job_b.salary and not job_a.salary:
                    job_a.salary = job_b.salary
                if job_b.date_posted and not job_a.date_posted:
                    job_a.date_posted = job_b.date_posted
                used.add(j)

        merged.append(job_a)

    removed = len(jobs) - len(merged)
    if removed > 0:
        logger.info("Deduplicacion: %d trabajos -> %d unicos (%d duplicados eliminados)", len(jobs), len(merged), removed)

    return merged
