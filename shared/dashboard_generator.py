from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from shared.models import EnrichedJob, Recommendation
from shared.utils import setup_logging

logger = setup_logging("dashboard")

TEMPLATES_DIR = Path(__file__).parent / "templates"


def generate_dashboard(
    enriched_jobs: list[EnrichedJob],
    profile_name: str,
    output_path: str | Path,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    enriched_jobs.sort(key=lambda ej: ej.score, reverse=True)

    apply_count = sum(1 for ej in enriched_jobs if ej.analysis and ej.analysis.recommendation == Recommendation.APPLY_NOW)
    consider_count = sum(1 for ej in enriched_jobs if ej.analysis and ej.analysis.recommendation == Recommendation.CONSIDER)
    skip_count = sum(1 for ej in enriched_jobs if ej.analysis and ej.analysis.recommendation == Recommendation.SKIP)
    unscored_count = sum(1 for ej in enriched_jobs if ej.analysis is None)

    all_sources = sorted(set(ej.job.source.value for ej in enriched_jobs))

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("dashboard.html")

    html = template.render(
        profile_name=profile_name,
        run_date=datetime.now().strftime("%d/%m/%Y %H:%M"),
        total_jobs=len(enriched_jobs),
        sources_count=len(all_sources),
        apply_count=apply_count,
        consider_count=consider_count,
        skip_count=skip_count,
        unscored_count=unscored_count,
        all_sources=all_sources,
        enriched_jobs=enriched_jobs,
    )

    output_path.write_text(html, encoding="utf-8")
    logger.info("Dashboard generado: %s", output_path)
    return output_path
