from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup

from shared.models import Job, JobSource, JobType
from shared.rate_limiter import RateLimiter
from shared.scraper_base import BaseScraper
from shared.utils import normalize_text

CONFIGS_DIR = Path(__file__).parent / "company_configs"


class CompanyCareersScraper(BaseScraper):
    def __init__(self, rate_limiter: RateLimiter, company_names: list[str] | None = None):
        super().__init__(rate_limiter)
        self.company_names = company_names or []

    def get_source(self) -> JobSource:
        return JobSource.COMPANY_CAREER

    async def search(self, term: str, location: str = "Peru") -> list[Job]:
        all_jobs: list[Job] = []

        for name in self.company_names:
            config_path = CONFIGS_DIR / f"{name}.yaml"
            if not config_path.exists():
                self.logger.warning("Config no encontrada: %s", config_path)
                continue

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            try:
                jobs = await self._scrape_company(config, term)
                all_jobs.extend(jobs)
            except Exception as e:
                self.logger.error("Error scrapeando %s: %s", config.get("name", name), e)

        return all_jobs

    async def _scrape_company(self, config: dict, search_term: str) -> list[Job]:
        company_name = config.get("name", "Desconocido")
        requires_js = config.get("requires_js", False)

        search_url = config.get("search_url_pattern", "")
        if not search_url:
            return []

        url = search_url.replace("{keyword}", search_term).replace("{location}", "Peru")

        if requires_js:
            return await asyncio.to_thread(self._scrape_with_selenium, config, url, company_name)
        else:
            return await self._scrape_with_httpx(config, url, company_name)

    async def _scrape_with_httpx(self, config: dict, url: str, company_name: str) -> list[Job]:
        selectors = config.get("selectors", {})
        jobs: list[Job] = []

        async with httpx.AsyncClient(follow_redirects=True) as client:
            if not await self.rate_limiter.can_fetch(url):
                self.logger.warning("robots.txt bloquea %s", url)
                return []

            try:
                resp = await self._get(url, client)
                if resp.status_code != 200:
                    return []
            except Exception as e:
                self.logger.error("HTTP error para %s: %s", company_name, e)
                return []

            soup = BeautifulSoup(resp.text, "lxml")

            card_selector = selectors.get("job_card", "")
            if not card_selector:
                return []

            cards = soup.select(card_selector)
            for card in cards:
                try:
                    title_el = card.select_one(selectors.get("title", "h3"))
                    title = title_el.get_text(strip=True) if title_el else ""
                    if not title:
                        continue

                    link_el = card.select_one(selectors.get("link", "a"))
                    href = ""
                    if link_el:
                        href = link_el.get("href", "")
                        if href and not href.startswith("http"):
                            base = config.get("careers_url", "")
                            href = f"{base.rstrip('/')}/{href.lstrip('/')}"

                    loc_el = card.select_one(selectors.get("location", ""))
                    loc = loc_el.get_text(strip=True) if loc_el else ""

                    job_type = JobType.UNKNOWN
                    if any(w in title.lower() for w in ["intern", "practicante", "prácticas"]):
                        job_type = JobType.INTERNSHIP

                    jobs.append(Job(
                        title=title,
                        company=company_name,
                        location=loc,
                        url=href or url,
                        description="",
                        source=JobSource.COMPANY_CAREER,
                        job_type=job_type,
                        sources_found=[f"career_{config.get('name', '').lower().replace(' ', '_')}"],
                    ))
                except Exception:
                    continue

        return jobs

    def _scrape_with_selenium(self, config: dict, url: str, company_name: str) -> list[Job]:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            self.logger.error("selenium no instalado")
            return []

        selectors = config.get("selectors", {})
        jobs: list[Job] = []

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"user-agent={self._random_ua()}")

        driver = None
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(30)
            driver.get(url)

            card_sel = selectors.get("job_card", "")
            if card_sel:
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, card_sel))
                    )
                except Exception:
                    return []

                cards = driver.find_elements(By.CSS_SELECTOR, card_sel)
                for card in cards:
                    try:
                        title_sel = selectors.get("title", "h3")
                        title_els = card.find_elements(By.CSS_SELECTOR, title_sel)
                        title = title_els[0].text.strip() if title_els else ""
                        if not title:
                            continue

                        link_sel = selectors.get("link", "a")
                        link_els = card.find_elements(By.CSS_SELECTOR, link_sel)
                        href = link_els[0].get_attribute("href") if link_els else url

                        loc_sel = selectors.get("location", "")
                        loc = ""
                        if loc_sel:
                            loc_els = card.find_elements(By.CSS_SELECTOR, loc_sel)
                            loc = loc_els[0].text.strip() if loc_els else ""

                        job_type = JobType.UNKNOWN
                        if any(w in title.lower() for w in ["intern", "practicante"]):
                            job_type = JobType.INTERNSHIP

                        jobs.append(Job(
                            title=title,
                            company=company_name,
                            location=loc,
                            url=href or url,
                            description="",
                            source=JobSource.COMPANY_CAREER,
                            job_type=job_type,
                            sources_found=[f"career_{company_name.lower().replace(' ', '_')}"],
                        ))
                    except Exception:
                        continue
        finally:
            if driver:
                driver.quit()

        return jobs
