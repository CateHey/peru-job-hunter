"""
Peru Job Hunter - Mechatronics Intern Profile
Busca practicas en AI, ML, BI, Robotica, Electronica para estudiante de Mecatronica.

Uso:
  python -m mechatronics_hunter.run                 # Busqueda completa con Claude
  python -m mechatronics_hunter.run --no-claude      # Solo scraping, sin analisis
  python -m mechatronics_hunter.run --no-batch       # Claude secuencial (sin batch API)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from shared.claude_analyzer import analyze_jobs, is_api_available
from shared.config_loader import load_config
from shared.dashboard_generator import generate_dashboard
from shared.deduplicator import deduplicate_jobs
from shared.models import EnrichedJob, Job
from shared.rate_limiter import RateLimiter
from shared.utils import setup_logging

logger = setup_logging("mechatronics_hunter")

CONFIG_PATH = Path(__file__).parent / "config.yaml"
OUTPUT_DIR = Path(__file__).parent / "output"


def _build_scrapers(config, rate_limiter: RateLimiter):
    scrapers = []
    source_map = {s.name: s for s in config.search.sources}

    if "computrabajo" in source_map and source_map["computrabajo"].enabled:
        from scrapers.computrabajo import CompuTrabajoScraper
        scrapers.append((CompuTrabajoScraper(rate_limiter), source_map["computrabajo"]))

    if "linkedin" in source_map and source_map["linkedin"].enabled:
        from scrapers.linkedin_guest import LinkedInGuestScraper
        scrapers.append((LinkedInGuestScraper(rate_limiter), source_map["linkedin"]))

    if "indeed" in source_map and source_map["indeed"].enabled:
        from scrapers.indeed_jobspy import IndeedJobSpyScraper
        scrapers.append((IndeedJobSpyScraper(rate_limiter), source_map["indeed"]))

    if "laborum" in source_map and source_map["laborum"].enabled:
        from scrapers.laborum import LaborumScraper
        scrapers.append((LaborumScraper(rate_limiter), source_map["laborum"]))

    if "getonboard" in source_map and source_map["getonboard"].enabled:
        from scrapers.getonboard import GetOnBoardScraper
        scrapers.append((GetOnBoardScraper(rate_limiter), source_map["getonboard"]))

    if "gobierno" in source_map and source_map["gobierno"].enabled:
        from scrapers.gobierno_peru import GobiernoPeScraper
        scrapers.append((GobiernoPeScraper(rate_limiter), source_map["gobierno"]))

    if "company_careers" in source_map and source_map["company_careers"].enabled:
        from scrapers.company_careers import CompanyCareersScraper
        sc = source_map["company_careers"]
        scrapers.append((CompanyCareersScraper(rate_limiter, sc.companies), sc))

    return scrapers


async def _run_scraper(scraper, source_config) -> list[Job]:
    try:
        return await scraper.search_all_terms(source_config.search_terms)
    except Exception as e:
        logger.error("Error en %s: %s", scraper.get_source().value, e)
        return []


async def run(args):
    load_dotenv()
    config = load_config(CONFIG_PATH)
    rate_limiter = RateLimiter(min_delay=1.5, max_delay=3.0)

    logger.info("=== Peru Job Hunter - %s ===", config.profile.name)
    logger.info("Fuentes habilitadas: %s", [s.name for s in config.search.sources if s.enabled])

    scrapers = _build_scrapers(config, rate_limiter)
    if not scrapers:
        logger.error("No hay scrapers habilitados. Revisa config.yaml")
        return

    logger.info("Iniciando busqueda en %d fuentes...", len(scrapers))
    tasks = [_run_scraper(s, sc) for s, sc in scrapers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_jobs: list[Job] = []
    for result in results:
        if isinstance(result, list):
            all_jobs.extend(result)
        elif isinstance(result, Exception):
            logger.error("Scraper fallo: %s", result)

    logger.info("Total bruto: %d trabajos", len(all_jobs))

    all_jobs = deduplicate_jobs(all_jobs)
    logger.info("Despues de deduplicacion: %d trabajos unicos", len(all_jobs))

    if not all_jobs:
        logger.warning("No se encontraron trabajos. Verifica conexion y config.")
        return

    enriched: list[EnrichedJob]
    if args.no_claude:
        logger.info("Modo --no-claude: omitiendo analisis con Claude")
        enriched = [EnrichedJob(job=job, analysis=None) for job in all_jobs]
    elif not is_api_available():
        logger.info("API key no encontrada. Continuando sin analisis de relevancia.")
        enriched = [EnrichedJob(job=job, analysis=None) for job in all_jobs]
    else:
        enriched = analyze_jobs(
            all_jobs,
            config.profile,
            model=config.claude.get("model", "claude-haiku-4-5-20251001"),
            max_tokens=config.claude.get("max_tokens", 512),
            use_batch=not args.no_batch,
            system_prompt=config.claude.get("system_prompt"),
        )

    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    output_path = OUTPUT_DIR / f"dashboard_{date_str}.html"

    dashboard_path = generate_dashboard(enriched, config.profile.name, output_path)

    logger.info("Dashboard listo: %s", dashboard_path)
    logger.info("Resumen: %d APPLY_NOW, %d CONSIDER, %d SKIP, %d sin evaluar",
        sum(1 for e in enriched if e.rec == "APPLY_NOW"),
        sum(1 for e in enriched if e.rec == "CONSIDER"),
        sum(1 for e in enriched if e.rec == "SKIP"),
        sum(1 for e in enriched if e.rec == "UNSCORED"),
    )

    webbrowser.open(str(dashboard_path.resolve()))


def main():
    parser = argparse.ArgumentParser(description="Peru Job Hunter - Mechatronics Intern")
    parser.add_argument("--no-claude", action="store_true", help="Omitir analisis con Claude API")
    parser.add_argument("--no-batch", action="store_true", help="Usar llamadas secuenciales en vez de batch API")
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
