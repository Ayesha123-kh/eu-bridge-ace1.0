from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Domain = Literal["hiring", "credit", "education", "health", "biometrics",
                 "critical_infrastructure", "other"]
AiFeature = Literal["chat", "text_generation", "image_audio_video", "recommendations",
                    "decisions_about_people", "biometric_emotion", "other"]
DataType = Literal["contact", "identity", "financial", "health", "biometric", "children", "other"]
UserGroup = Literal["consumers", "business_customers", "employees", "job_applicants",
                    "students", "patients", "children"]
Provider = Literal["openai", "anthropic", "google", "groq", "self_hosted", "other", "unknown"]


class Questionnaire(BaseModel):
    product_name: str = Field(default="", max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    users: str = Field(default="", max_length=500)
    user_groups: list[UserGroup] = []
    eu_users: Literal["yes", "planned", "no"] = "planned"
    uses_llm: bool
    processes_personal_data: bool
    domain: Domain
    ai_features: list[AiFeature] = []
    data_types: list[DataType] = []
    ai_provider: Provider = "unknown"
    human_review: Literal["always", "sometimes", "never", "not_applicable"] = "not_applicable"


class ScanRequest(BaseModel):
    source: Literal["public", "private_token"] = "public"
    repo_url: str
    access_token: str | None = Field(default=None, repr=False)
    questionnaire: Questionnaire

    @model_validator(mode="after")
    def _token_for_private(self):
        if self.source == "private_token" and not (self.access_token or "").strip():
            raise ValueError("An access token is required to scan a private repository.")
        return self


class PrRequest(BaseModel):
    access_token: str | None = Field(default=None, repr=False)


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


class RegulationQuery(BaseModel):
    offers: list[str] = Field(default=[], max_length=20)
    eu_users: Literal["yes", "planned", "no"] = "planned"
    size: Literal["micro", "small", "medium", "large"] = "small"
    personal_data: bool = True
