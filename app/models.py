from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Questionnaire(BaseModel):
    description: str = Field(min_length=1, max_length=1000)
    users: str = Field(default="", max_length=500)
    uses_llm: bool
    processes_personal_data: bool
    domain: Literal["hiring", "credit", "education", "health", "biometrics",
                    "critical_infrastructure", "other"]


class ScanRequest(BaseModel):
    repo_url: str
    questionnaire: Questionnaire


class _Reviewer(BaseModel):
    reviewer: str
    reason: str

    @field_validator("reviewer")
    @classmethod
    def _reviewer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("reviewer name is required")
        return v

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("reason must be at least 5 characters")
        return v


class ReviewRequest(_Reviewer):
    action: Literal["approve", "edit_and_approve", "reject"]
    final_patch: str | None = None


class RiskReviewRequest(_Reviewer):
    pass
