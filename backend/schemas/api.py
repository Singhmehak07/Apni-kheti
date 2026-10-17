from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["pa", "hi", "en"]


class NewSession(BaseModel):
    lang: Lang = "pa"


class LangPatch(BaseModel):
    lang: Lang


class Answer(BaseModel):
    field: str
    option_id: str | None = None
    value: dict | None = None
    text: str | None = Field(default=None, max_length=1000)
    skip: bool = False
    via: Literal["typed", "chip", "voice", "voice_browser", "stepper"] = "typed"


class ProfilePatch(BaseModel):
    field: str
    option_id: str | None = None
    value: dict | None = None
    text: str | None = Field(default=None, max_length=1000)
    clear: bool = False


class ReportPatch(BaseModel):
    ph: float | None = Field(default=None, ge=3, le=11)
    ec: float | None = Field(default=None, ge=0, le=20)
    oc: float | None = Field(default=None, ge=0, le=5)


class RecRequest(BaseModel):
    session_id: str
    lang: Lang = "pa"


class LangOnly(BaseModel):
    lang: Lang = "pa"


class PlanRequest(BaseModel):
    recommendation_id: str
    crop_id: str
    lang: Lang = "pa"


class AskRequest(BaseModel):
    plan_id: str
    text: str = Field(max_length=1000)
    lang: Lang = "pa"


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    lang: Lang = "pa"


class TTSPrefetch(BaseModel):
    texts: list[str] = Field(max_length=200)
    lang: Lang = "pa"
