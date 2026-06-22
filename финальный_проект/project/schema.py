"""Pydantic-схемы финального проекта CloudPay Knowledge Assistant."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

KNOWN_DOC_IDS = {
    "cloudpay_dev_ivan",
    "cloudpay_dev_maria",
    "cloudpay_dev_petr",
    "cloudpay_ops_anna",
    "cloudpay_ops_denis",
    "cloudpay_pm_kate",
    "cloudpay_sec_nikita",
    "cloudpay_sec_svetlana",
    "cloudpay_support_elena",
    "cloudpay_support_oleg",
}

QuestionType = Literal["lookup", "multi_hop", "negative"]


class Citation(BaseModel):
    doc_id: str = Field(description="ID документа, напр. cloudpay_dev_ivan")
    quote: str = Field(min_length=8, description="Дословная цитата из документа")
    speaker: str = Field(min_length=2, description="Имя респондента из интервью")

    @field_validator("doc_id")
    @classmethod
    def doc_must_exist(cls, v: str) -> str:
        stem = v.split("__")[0]
        if stem not in KNOWN_DOC_IDS:
            raise ValueError(f"неизвестный doc_id: {v}")
        return v


class Answer(BaseModel):
    question: str
    speakers: list[str] = Field(description="Кто упомянут в ответе")
    summary: str = Field(min_length=10)
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    found_in_corpus: bool = Field(
        description="True если ответ основан на корпусе; False если данных нет"
    )
    chunk_ids: list[str] = Field(default_factory=list, description="ID использованных чанков")

    @field_validator("citations")
    @classmethod
    def citations_if_found(cls, v: list[Citation], info) -> list[Citation]:
        found = info.data.get("found_in_corpus", True)
        if not found and v:
            raise ValueError("found_in_corpus=False — цитаты должны быть пусты")
        return v

    @model_validator(mode="after")
    def normalize_found_flag(self) -> Answer:
        if self.found_in_corpus and not self.citations:
            self.found_in_corpus = False
        return self


class RouterDecision(BaseModel):
    question_type: QuestionType
    reasoning: str = Field(max_length=300)
    retrieval_k: int = Field(ge=3, le=12, default=5)


class JudgeItem(BaseModel):
    criterion: str
    verdict: Literal["supported", "weakly_supported", "not_supported"]
    reason: str


class JudgeReport(BaseModel):
    items: list[JudgeItem]
    overall: Literal["pass", "fail"]
    ghost_citations: int = Field(ge=0, default=0)


class PathMetrics(BaseModel):
    retrieval_calls: int = 0
    agent_steps: int = 0
    tools_used: list[str] = Field(default_factory=list)
    chunks_read: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_sec: float = 0.0


class PipelineResult(BaseModel):
    question: str
    router: RouterDecision
    answer: Answer
    judge: JudgeReport
    path: PathMetrics
    retrieved_sources: list[str] = Field(default_factory=list)
    trace: list[dict] = Field(default_factory=list)
