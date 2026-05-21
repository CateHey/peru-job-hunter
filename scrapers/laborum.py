from __future__ import annotations

import asyncio
from urllib.parse import quote_plus

from shared.models import Job, JobSource, JobType
from shared.rate_limiter import RateLimiter
from shared.scraper_base import BaseScraper
from shared.utils import parse_relative_date


class LaborumScraper(BaseScraper):
    BASE_URL = "https://www.laborum.pe"

    def __init__(self, rate_limiter: RateLimiter, max_pages: int = 3):
        super().__init__(rate_limiter)
        self.max_pages = max_pages

    def get_source(self) -> JobSource:
        return JobSource.LABORUM

    async def search(self, term: str, location: str = "Peru") -> list[Job]:
        try:
            return await asyncio.to_thread(self._search_sync, term)
        except Exception as e:
            self.logger.error("Error Laborum Selenium: %s", e)
            return []

    def _search_sync(self, term: str) -> list[Job]:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            self.logger.error("selenium/webdriver-manager no instalados")
            return []

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"user-agent={self._random_ua()}")

        driver = None
        jobs: list[Job] = []

        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)

            encoded = quote_plus(term.replace(" ", "-"))
            url = f"{self.BASE_URL}/empleos-busqueda-{encoded}.html"
            driver.get(url)

            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='aviso'], a[class*='aviso']"))
            )

            for page in range(self.max_pages):
                cards = driver.find_elements(By.CSS_SELECTOR, "div[class*='aviso'], a[class*='aviso']")

                for card in cards:
                    try:
                        title_el = card.find_elements(By.CSS_SELECTOR, "h2, a[class*='title']")
                        title = title_el[0].text.strip() if title_el else ""
                        if not title:
                            continue

                        link_el = card.find_elements(By.CSS_SELECTOR, "a[href*='/empleos/']")
                        href = link_el[0].get_attribute("href") if link_el else ""
                        if not href:
                            for a in card.find_elements(By.TAG_NAME, "a"):
                                h = a.get_attribute("href") or ""
                                if "/empleos/" in h:
                                    href = h
                                    break

                        company_el = card.find_elements(By.CSS_SELECTOR, "span[class*='company'], div[class*='company']")
                        company = company_el[0].text.strip() if company_el else "Empresa Confidencial"

                        location_el = card.find_elements(By.CSS_SELECTOR, "span[class*='location'], div[class*='location']")
                        loc = location_el[0].text.strip() if location_el else ""

                        date_el = card.find_elements(By.CSS_SELECTOR, "span[class*='date'], span[class*='time']")
                        date_posted = None
                        if date_el:
                            date_posted = parse_relative_date(date_el[0].text.strip())

                        job_type = JobType.UNKNOWN
                        if any(w in title.lower() for w in ["practicante", "prácticas", "intern"]):
                            job_type = JobType.INTERNSHIP

                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=loc,
                            url=href or url,
                            description="",
                            date_posted=date_posted,
                            source=JobSource.LABORUM,
                            job_type=job_type,
                            sources_found=["laborum"],
                        ))
                    except Exception:
                        continue

                if page < self.max_pages - 1:
                    try:
                        next_btn = driver.find_elements(By.CSS_SELECTOR, "a[class*='next'], button[class*='next']")
                        if next_btn:
                            next_btn[0].click()
                            WebDriverWait(driver, 10).until(
                                EC.staleness_of(cards[0]) if cards else EC.presence_of_element_located(
                                    (By.CSS_SELECTOR, "div[class*='aviso']")
                                )
                            )
                        else:
                            break
                    except Exception:
                        break
        finally:
            if driver:
                driver.quit()

        return jobs
