import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Domain = Literal["hiring", "credit", "education", "health", "biometrics",
                 "critical_infrastructure", "other"]
AiFeature = Literal["chat", "text_generation", "image_audio_video", "recommendations",
                    "decisions_about_people", "biometric_emotion", "other"]
DataType = Literal["none", "contact", "identity", "financial", "health", "biometric", "children", "other"]
UserGroup = Literal["consumers", "business_customers", "employees", "job_applicants",
                    "students", "patients", "children"]
Provider = Literal["openai", "anthropic", "google", "groq", "self_hosted", "other", "unknown"]


HIGH_RISK_DOMAINS = {"hiring", "credit", "education", "health", "biometrics", "critical_infrastructure"}
HOST_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")


def plausible_text(text: str) -> bool:
    """Reject keyboard mashing and one-word answers. Not a language check."""
    words = re.findall(r"[A-Za-z]{2,}", text)
    letters = re.findall(r"[A-Za-z]", text)
    if len(text.strip()) < 20 or len(words) < 4 or not letters:
        return False
    vowels = sum(c in "aeiouAEIOU" for c in letters) / len(letters)
    if not 0.18 <= vowels <= 0.65 or re.search(r"(.)\1{4,}", text):
        return False
    rows = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
    mashed = sum(any(w.lower() in r or w.lower()[::-1] in r for r in rows) for w in words if len(w) >= 4)
    if mashed >= 2:
        return False
    return sum(bool(re.search(r"[aeiouyAEIOUY]", w)) for w in words) / len(words) >= 0.7


def clean_website(value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValueError("Enter your business website, for example https://example.com.")
    if not re.match(r"^https?://", v, re.I):
        v = "https://" + v
    host = re.sub(r"^https?://", "", v, flags=re.I).split("/")[0].split("?")[0].split(":")[0].lower()
    if not HOST_RE.match(host):
        raise ValueError("Enter a valid website address, for example https://example.com.")
    return v


class Questionnaire(BaseModel):
    company_name: str = Field(default="", max_length=120)
    website: str = Field(default="", max_length=300)
    industry: str = Field(default="", max_length=120)
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
    ai_provider: Provider = "unknown"  # kept for older clients; mirrors ai_providers[0]
    ai_providers: list[Provider] = []
    human_review: Literal["always", "sometimes", "never", "not_applicable"] = "not_applicable"


    @model_validator(mode="after")
    def _sync_providers(self):
        if self.ai_providers and self.ai_provider == "unknown":
            self.ai_provider = self.ai_providers[0]
        elif self.ai_provider != "unknown" and not self.ai_providers:
            self.ai_providers = [self.ai_provider]
        return self

    @model_validator(mode="after")
    def _check_answers(self):
        """Server-side rules, so the API cannot be used to skip what the form requires."""
        if len(re.findall(r"[A-Za-z]", self.company_name)) < 2:
            raise ValueError("Enter your company name.")
        self.company_name = self.company_name.strip()
        self.website = clean_website(self.website)
        if not plausible_text(self.description):
            raise ValueError("Describe what the product does in a full sentence, at least four words.")
        if not self.user_groups:
            raise ValueError("Choose who uses the product.")
        if self.domain == "other" and len(re.findall(r"[A-Za-z]", self.industry)) < 3:
            raise ValueError("Tell us your industry, since none of the listed areas fit.")
        if not self.ai_features:
            raise ValueError("Choose what the AI does.")
        if not self.ai_providers:
            raise ValueError("Choose the AI providers you use, or Not sure.")
        if not self.data_types:
            raise ValueError("Choose the personal data you handle, or No personal data.")
        self.processes_personal_data = any(d != "none" for d in self.data_types)
        oversight_needed = (self.domain in HIGH_RISK_DOMAINS or
                            {"decisions_about_people", "recommendations", "biometric_emotion"} & set(self.ai_features))
        if oversight_needed and self.human_review == "not_applicable":
            raise ValueError("Tell us whether a person reviews the AI's output, since it can affect people.")
        return self



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


class SignupRequest(BaseModel):
    name: str = Field(max_length=80)
    email: str = Field(max_length=200)
    password: str = Field(max_length=200, repr=False)


class LoginRequest(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200, repr=False)
