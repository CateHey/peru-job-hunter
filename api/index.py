from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from shared.claude_analyzer import analyze_single_job, filter_single_job, is_api_available
from shared.config_loader import load_config
from shared.deduplicator import deduplicate_jobs
from shared.models import Job
from shared.rate_limiter import RateLimiter

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent

PROFILES = {
    "mechatronics": BASE_DIR / "mechatronics_hunter" / "config.yaml",
    "infra": BASE_DIR / "infra_hunter" / "config.yaml",
}

rate_limiter = RateLimiter(min_delay=1.0, max_delay=2.0)


def _jobs_to_dicts(jobs: list[Job]) -> list[dict]:
    return [j.model_dump(mode="json") for j in jobs]


def _has_server_key() -> bool:
    return is_api_available()


def _use_client_key(api_key: str | None):
    if api_key and api_key.startswith("sk-ant-"):
        os.environ["ANTHROPIC_API_KEY"] = api_key


@app.get("/api/profiles")
async def get_profiles(request: Request):
    _use_client_key(request.headers.get("x-api-key"))

    profiles = {}
    for name, path in PROFILES.items():
        try:
            config = load_config(path)
            profiles[name] = {
                "name": config.profile.name,
                "description": config.profile.description,
                "sources": [
                    {"name": s.name, "enabled": s.enabled}
                    for s in config.search.sources
                ],
            }
        except Exception as e:
            profiles[name] = {"error": str(e)}

    return {
        "profiles": profiles,
        "claude_available": is_api_available(),
        "server_has_key": _has_server_key(),
    }


@app.get("/api/search/{profile}/{source}")
async def search_source(
    profile: str,
    source: str,
    max_pages: int = Query(default=2, ge=1, le=5),
):
    if profile not in PROFILES:
        return JSONResponse({"error": f"Perfil '{profile}' no encontrado"}, status_code=404)

    config = load_config(PROFILES[profile])
    source_config = next((s for s in config.search.sources if s.name == source), None)

    if not source_config:
        return JSONResponse({"error": f"Fuente '{source}' no encontrada en perfil"}, status_code=404)

    if not source_config.enabled and source not in ("computrabajo", "linkedin", "indeed"):
        return JSONResponse({"error": f"Fuente '{source}' deshabilitada"}, status_code=400)

    jobs: list[Job] = []

    try:
        if source == "computrabajo":
            from scrapers.computrabajo import CompuTrabajoScraper
            scraper = CompuTrabajoScraper(rate_limiter, max_pages=max_pages)
            jobs = await scraper.search_all_terms(source_config.search_terms[:3])

        elif source == "linkedin":
            from scrapers.linkedin_guest import LinkedInGuestScraper
            scraper = LinkedInGuestScraper(rate_limiter, max_pages=max_pages)
            jobs = await scraper.search_all_terms(source_config.search_terms[:3])

        elif source == "indeed":
            from scrapers.indeed_jobspy import IndeedJobSpyScraper
            scraper = IndeedJobSpyScraper(rate_limiter, results_wanted=30)
            jobs = await scraper.search_all_terms(source_config.search_terms[:2])

        else:
            return JSONResponse(
                {"error": f"Fuente '{source}' no soportada en modo web (requiere Selenium)"},
                status_code=400,
            )

    except Exception as e:
        return JSONResponse({"error": str(e), "jobs": []}, status_code=200)

    return {"source": source, "count": len(jobs), "jobs": _jobs_to_dicts(jobs)}


@app.get("/api/search/{profile}")
async def search_all(profile: str, request: Request):
    _use_client_key(request.headers.get("x-api-key"))

    if profile not in PROFILES:
        return JSONResponse({"error": f"Perfil '{profile}' no encontrado"}, status_code=404)

    config = load_config(PROFILES[profile])
    all_jobs: list[Job] = []
    source_results = {}

    web_sources = ["computrabajo", "linkedin", "indeed"]

    for sc in config.search.sources:
        if sc.name not in web_sources or not sc.enabled:
            continue

        try:
            if sc.name == "computrabajo":
                from scrapers.computrabajo import CompuTrabajoScraper
                scraper = CompuTrabajoScraper(rate_limiter, max_pages=2)
                jobs = await scraper.search_all_terms(sc.search_terms[:3])

            elif sc.name == "linkedin":
                from scrapers.linkedin_guest import LinkedInGuestScraper
                scraper = LinkedInGuestScraper(rate_limiter, max_pages=2)
                jobs = await scraper.search_all_terms(sc.search_terms[:3])

            elif sc.name == "indeed":
                from scrapers.indeed_jobspy import IndeedJobSpyScraper
                scraper = IndeedJobSpyScraper(rate_limiter, results_wanted=30)
                jobs = await scraper.search_all_terms(sc.search_terms[:2])
            else:
                continue

            source_results[sc.name] = len(jobs)
            all_jobs.extend(jobs)

        except Exception as e:
            source_results[sc.name] = f"error: {e}"

    all_jobs = deduplicate_jobs(all_jobs)

    return {
        "profile": config.profile.name,
        "total": len(all_jobs),
        "sources": source_results,
        "jobs": _jobs_to_dicts(all_jobs),
        "claude_available": is_api_available(),
    }


@app.post("/api/analyze")
async def analyze_job_endpoint(request: Request):
    payload = await request.json()

    api_key = request.headers.get("x-api-key") or payload.get("api_key")
    _use_client_key(api_key)

    if not is_api_available():
        return JSONResponse(
            {"error": "API key no proporcionada", "analysis": None},
            status_code=200,
        )

    profile_key = payload.get("profile", "mechatronics")
    if profile_key not in PROFILES:
        return JSONResponse({"error": "Perfil no encontrado"}, status_code=404)

    config = load_config(PROFILES[profile_key])

    try:
        job = Job(**payload["job"])
    except Exception as e:
        return JSONResponse({"error": f"Job invalido: {e}"}, status_code=400)

    enriched = analyze_single_job(
        job,
        config.profile,
        model=config.claude.get("model", "claude-haiku-4-5-20251001"),
    )

    result = enriched.analysis.model_dump(mode="json") if enriched.analysis else None
    return {"analysis": result}


@app.post("/api/filter")
async def filter_job_endpoint(request: Request):
    payload = await request.json()

    api_key = request.headers.get("x-api-key") or payload.get("api_key")
    _use_client_key(api_key)

    profile_key = payload.get("profile", "mechatronics")
    if profile_key not in PROFILES:
        return JSONResponse({"error": "Perfil no encontrado"}, status_code=404)

    config = load_config(PROFILES[profile_key])

    try:
        job = Job(**payload["job"])
    except Exception as e:
        return JSONResponse({"error": f"Job invalido: {e}"}, status_code=400)

    result = filter_single_job(
        job,
        config.profile,
        model=config.claude.get("model", "claude-haiku-4-5-20251001"),
    )
    return result


@app.get("/api/search/{profile}/{source}/keywords")
async def search_by_keywords(
    profile: str,
    source: str,
    q: str = Query(..., min_length=1, max_length=200),
    max_pages: int = Query(default=2, ge=1, le=5),
):
    if profile not in PROFILES:
        return JSONResponse({"error": f"Perfil '{profile}' no encontrado"}, status_code=404)

    keywords = [k.strip() for k in q.split(",") if k.strip()]
    if not keywords:
        return JSONResponse({"error": "No se proporcionaron keywords"}, status_code=400)

    jobs: list[Job] = []

    try:
        if source == "computrabajo":
            from scrapers.computrabajo import CompuTrabajoScraper
            scraper = CompuTrabajoScraper(rate_limiter, max_pages=max_pages)
            jobs = await scraper.search_all_terms(keywords)

        elif source == "linkedin":
            from scrapers.linkedin_guest import LinkedInGuestScraper
            scraper = LinkedInGuestScraper(rate_limiter, max_pages=max_pages)
            jobs = await scraper.search_all_terms(keywords)

        elif source == "indeed":
            from scrapers.indeed_jobspy import IndeedJobSpyScraper
            scraper = IndeedJobSpyScraper(rate_limiter, results_wanted=30)
            jobs = await scraper.search_all_terms(keywords)

        elif source == "getonboard":
            from scrapers.getonboard import GetOnBoardScraper
            scraper = GetOnBoardScraper(rate_limiter)
            jobs = await scraper.search_all_terms(keywords)

        else:
            return JSONResponse(
                {"error": f"Fuente '{source}' no soportada para busqueda por keywords"},
                status_code=400,
            )

    except Exception as e:
        return JSONResponse({"error": str(e), "jobs": []}, status_code=200)

    return {"source": source, "keywords": keywords, "count": len(jobs), "jobs": _jobs_to_dicts(jobs)}
