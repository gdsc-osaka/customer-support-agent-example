from __future__ import annotations

from pydantic import BaseModel, Field


class TravelRequest(BaseModel):
    origin: str | None = Field(default=None, description="出発地。例: 東京、大阪。")
    duration: str | None = Field(default=None, description="旅行期間。通常は1泊2日。")
    budget: str | None = Field(default=None, description="総予算または一人あたり予算。")
    transport: str | None = Field(default=None, description="主な交通手段。")
    companions: str | None = Field(default=None, description="同行者構成。")
    preferences: list[str] = Field(default_factory=list, description="旅行嗜好。")
    constraints: list[str] = Field(default_factory=list, description="制約条件。")
    unknowns: list[str] = Field(default_factory=list, description="品質に影響する不足情報。")
    raw_user_query: str = Field(description="元のユーザー入力。")
