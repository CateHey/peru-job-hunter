from __future__ import annotations

import asyncio
from urllib.parse import quote_plus

from shared.models import Job, JobSource, JobType
from shared.rate_limiter import RateLimiter
from shared.scraper_base import BaseScraper
from shared.utils import normalize_text, parse_relative_date


class GobiernoPeScraper(BaseScraper):
    EMPLEOS_PERU_URL = "https://www.empleosperu.gob.pe"

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(rate_limiter)

    def get_source(self) -> JobSource:
        return JobSource.GOBIERNO

    async def search(self, term: str, location: str = "Peru") -> list[Job]:
        try:
            return await asyncio.to_thread(self._search_sync, term)
        except Exception as e:
            self.logger.warning("Gobierno Peru no disponible: %s", e)
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
            driver.set_page_load_timeout(30)

            search_url = f"{self.EMPLEOS_PERU_URL}/portal-mtpe/#/busqueda?palabra={quote_plus(term)}"
            driver.get(search_url)

            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.oferta, div[class*='job'], div[class*='result']"))
                )
            except Exception:
                self.logger.info("No se encontraron resultados en Portal Empleos Peru para: %s", term)
                return []

            cards = driver.find_elements(By.CSS_SELECTOR, "div.oferta, div[class*='job'], div[class*='result']")

            for card in cards:
                try:
                    title_el = card.find_elements(By.CSS_SELECTOR, "h3, h4, a[class*='title']")
                    title = title_el[0].text.strip() if title_el else ""
                    if not title:
                        continue

                    link_el = card.find_elements(By.TAG_NAME, "a")
                    href = ""
                    for a in link_el:
                        h = a.get_attribute("href") or ""
                        if h and "oferta" in h.lower():
                            href = h
                            break
                    if not href and link_el:
                        href = link_el[0].get_attribute("href") or search_url

                    company_el = card.find_elements(By.CSS_SELECTOR, "span[class*='empresa'], p[class*='empresa']")
                    company = company_el[0].text.strip() if company_el else "Entidad Publica"

                    location_el = card.find_elements(By.CSS_SELECTOR, "span[class*='ubic'], span[class*='location']")
                    loc = location_el[0].text.strip() if location_el else "Peru"

                    job_type = JobType.UNKNOWN
                    if any(w in title.lower() for w in ["practicante", "prácticas", "cas"]):
                        job_type = JobType.INTERNSHIP if "practicante" in title.lower() else JobType.CONTRACT

                    jobs.append(Job(
                        title=title,
                        company=company,
                        location=loc,
                        url=href,
                        description="",
                        source=JobSource.GOBIERNO,
                        job_type=job_type,
                        sources_found=["gobierno"],
                    ))
                except Exception:
                    continue

        except Exception as e:
            self.logger.warning("Error accediendo Portal Empleos Peru: %s", e)
        finally:
            if driver:
                driver.quit()

        return jobs
