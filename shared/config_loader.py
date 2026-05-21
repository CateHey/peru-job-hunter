from __future__ import annotations

from pathlib import Path

import yaml

from shared.models import (
    ClientProfile,
    HunterConfig,
    SearchConfig,
    SourceConfig,
)


def load_config(config_path: str | Path) -> HunterConfig:
    path = Path(config_path)
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    profile = ClientProfile(**raw["profile"])

    search_raw = raw.get("search", {})
    sources = [SourceConfig(**s) for s in search_raw.get("sources", [])]
    search = SearchConfig(
        max_results_per_source=search_raw.get("max_results_per_source", 50),
        max_age_days=search_raw.get("max_age_days", 30),
        sources=sources,
    )

    claude = raw.get("claude", {})

    return HunterConfig(profile=profile, search=search, claude=claude)
