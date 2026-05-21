from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobSource(str, Enum):
    COMPUTRABAJO = "computrabajo"
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    LABORUM = "laborum"
    GOBIERNO = "gobierno"
    COMPANY_CAREER = "company_career"
    GETONBOARD = "getonboard"


class JobType(str, Enum):
    FULLTIME = "fulltime"
    PARTTIME = "parttime"
    INTERNSHIP = "internship"
    CONTRACT = "contract"
    UNKNOWN = "unknown"


class Recommendation(str, Enum):
    APPLY_NOW = "APPLY_NOW"
    CONSIDER = "CONSIDER"
    SKIP = "SKIP"


class Job(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    company: str
    location: str = ""
    url: str
    description: str = ""
    date_posted: Optional[datetime] = None
    salary: Optional[str] = None
    source: JobSource
    job_type: JobType = JobType.UNKNOWN
    sources_found: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    job_id: str
    relevance_score: int = Field(ge=0, le=100)
    reasoning: str = ""
    summary: str
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    recommendation: Recommendation


class EnrichedJob(BaseModel):
    job: Job
    analysis: Optional[AnalysisResult] = None

    @property
    def score(self) -> int:
        return self.analysis.relevance_score if self.analysis else 0

    @property
    def rec(self) -> str:
        return self.analysis.recommendation.value if self.analysis else "UNSCORED"


class ClientProfile(BaseModel):
    name: str
    description: str
    target_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: str = ""
    experience_level: str = ""
    preferred_locations: list[str] = Field(default_factory=list)


class SourceConfig(BaseModel):
    name: str
    enabled: bool = True
    search_terms: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    experience_levels: list[str] = Field(default_factory=list)


class SearchConfig(BaseModel):
    max_results_per_source: int = 50
    max_age_days: int = 30
    sources: list[SourceConfig] = Field(default_factory=list)


class HunterConfig(BaseModel):
    profile: ClientProfile
    search: SearchConfig
    claude: dict = Field(default_factory=lambda: {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 512,
    })
