from __future__ import annotations

from pydantic import BaseModel, Field

from agents.coordinator.candidates_models import ResearchReport, TravelOption
from agents.coordinator.evaluation_models import EvaluationReport
from agents.coordinator.clarify_models import TravelRequest


class RankedOption(BaseModel):
    option_id: str
    rank: int
    title: str
    reason: str
    cautions: list[str]


class CoordinatorRecommendation(BaseModel):
    ranked_options: list[RankedOption] = Field(max_length=3)
    comparison_summary: str
    conflict_resolution: str
    user_message: str


class SelectedOptionContext(BaseModel):
    travel_request: TravelRequest
    selected_option: TravelOption
    research_report: ResearchReport
    evaluations: list[EvaluationReport]
    recommendation: RankedOption | None
    coordinator_notes: str
