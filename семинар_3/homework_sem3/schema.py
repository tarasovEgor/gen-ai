"""
schema.py — Pydantic-схемы пайплайна анализа отзывов из App Store / Google Play.

Домен: мобильное приложение «МойБанк» (фиктивный банковский клиент).
Адаптация семинарного пайплайна: Participant → Review, concerns → issues.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Фиксированный набор аспектов (раунд 2)
# performance=производительность, design=дизайн, support=поддержка,
# price=цена, ads=реклама, reliability=надёжность
REVIEW_ASPECTS = [
    "performance",
    "design",
    "support",
    "price",
    "ads",
    "reliability",
]

ASPECT_LABELS_RU = {
    "performance": "производительность",
    "design": "дизайн",
    "support": "поддержка",
    "price": "цена",
    "ads": "реклама",
    "reliability": "надёжность",
}

IssueCategory = Literal["performance", "design", "support", "price", "ads", "reliability"]
ReviewAspect = Literal["performance", "design", "support", "price", "ads", "reliability"]
Platform = Literal["ios", "android", "rustore"]
Sentiment = Literal["positive", "negative", "neutral"]


# ══════════════════════════════════════════════════════════
# Раунд 1 — Information Extraction
# ══════════════════════════════════════════════════════════
class Issue(BaseModel):
    category: IssueCategory
    severity: int = Field(ge=1, le=5, description="1 — мелочь, 5 — критично")
    quote: str = Field(min_length=10, description="Точная цитата из отзыва")


class Review(BaseModel):
    author: str
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    platform: Platform
    review_date: date
    app_version: Optional[str] = None
    issues: list[Issue] = Field(min_length=1)
    competitor_mentions: list[str] = Field(default_factory=list)

    @field_validator("review_date")
    @classmethod
    def date_not_in_future(cls, v: date) -> date:
        if v > date.today():
            raise ValueError(f"Дата отзыва {v} не может быть позже сегодняшней ({date.today()})")
        return v


# ══════════════════════════════════════════════════════════
# Раунд 2 — Аспектный анализ
# ══════════════════════════════════════════════════════════
class AspectSentiment(BaseModel):
    aspect: ReviewAspect
    sentiment: Sentiment
    quote: str = Field(min_length=10)
    confidence: float = Field(ge=0, le=1)


class ReviewSentiment(BaseModel):
    author: str
    aspects: list[AspectSentiment]


# ══════════════════════════════════════════════════════════
# Раунд 2.5 — Autodiscovery аспектов
# ══════════════════════════════════════════════════════════
class DiscoveredAspect(BaseModel):
    name: str
    description: str = Field(min_length=5)


class DiscoveredAspects(BaseModel):
    aspects: list[DiscoveredAspect] = Field(min_length=3, max_length=12)


class DynamicAspect(BaseModel):
    aspect: str
    sentiment: Sentiment
    quote: str = Field(min_length=10)
    confidence: float = Field(ge=0, le=1)


class DynamicReviewSentiment(BaseModel):
    author: str
    aspects: list[DynamicAspect]


# ══════════════════════════════════════════════════════════
# Раунд 3 — Map-Reduce
# ══════════════════════════════════════════════════════════
class ChunkSummary(BaseModel):
    speaker: str
    key_points: list[str] = Field(min_length=1, max_length=6)
    sentiment: Literal["positive", "negative", "mixed"]


class ReviewsSummary(BaseModel):
    headline: str
    key_findings: list[str] = Field(min_length=2, max_length=8)
    action_items: list[str] = Field(min_length=1, max_length=8)


# ══════════════════════════════════════════════════════════
# Раунд 5 — LLM-as-judge
# ══════════════════════════════════════════════════════════
class ActionVerdict(BaseModel):
    action: str
    support: Literal["supported", "weakly_supported", "not_supported"]
    evidence: list[str] = Field(default_factory=list)
    comment: str


class JudgeReport(BaseModel):
    verdicts: list[ActionVerdict]
    overall_score: float = Field(ge=0, le=1)
    summary: str
