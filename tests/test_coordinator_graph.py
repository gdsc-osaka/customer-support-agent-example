from types import SimpleNamespace

from agents.coordinator.agent import candidate_workflow, root_agent
from agents.coordinator.candidates import STATE_RESEARCH_REPORTS, STATE_TRAVEL_OPTIONS
from agents.coordinator.evaluation import STATE_REVISED_EVALUATIONS
from agents.coordinator.intake import STATE_TRAVEL_REQUEST
from agents.coordinator.recommendation import (
    ROUTE_SELECTED,
    STATE_COORDINATOR_RECOMMENDATION,
    STATE_SELECTED_OPTION_CONTEXT,
    STATE_SELECTED_OPTION_ID,
    CoordinatorRecommendation,
    RankedOption,
    build_selected_option_context,
    request_user_selection,
    route_user_selection,
)


def edge_set(workflow):
    return {
        (edge.from_node.name, edge.route, edge.to_node.name)
        for edge in workflow.graph.edges
    }


def test_clarification_route_waits_before_reanalysis():
    edges = edge_set(root_agent)

    assert ("route_after_analysis", "clarify", "request_clarification") in edges
    assert ("request_clarification", None, "build_reanalysis_input") in edges
    assert ("build_reanalysis_input", None, "analyst") in edges

    assert ("route_after_analysis", "clarify", "build_reanalysis_input") not in edges
    assert ("route_after_analysis", "clarify", "analyst") not in edges


def test_replan_route_builds_replan_input_before_analysis():
    edges = edge_set(candidate_workflow)

    assert ("route_user_selection", "replan", "build_replan_input") in edges
    assert ("build_replan_input", None, "analyst") in edges

    assert ("route_user_selection", "replan", "analyst") not in edges


def sample_recommendation():
    return CoordinatorRecommendation(
        ranked_options=[
            RankedOption(
                option_id="option_1",
                rank=1,
                title="xxx",
                reason="first",
                cautions=[],
            ),
            RankedOption(
                option_id="option_2",
                rank=2,
                title="yyy",
                reason="second",
                cautions=[],
            ),
            RankedOption(
                option_id="option_3",
                rank=3,
                title="zzz",
                reason="third",
                cautions=[],
            ),
        ],
        comparison_summary="summary",
        conflict_resolution="notes",
        user_message="message",
    )


def sample_travel_option(option_id="option_1"):
    return {
        "option_id": option_id,
        "title": "xxx",
        "destination": "箱根",
        "concept": "静かな温泉旅行",
        "research_focus": ["アクセス", "宿泊"],
        "fit_hypothesis": "短期間で移動しやすい",
    }


def sample_research_report(option_id="option_1"):
    return {
        "option_id": option_id,
        "destination_summary": "温泉地",
        "access": "電車",
        "estimated_cost": "要確認",
        "lodging_area": "駅周辺",
        "recommended_spots": ["美術館"],
        "food_options": ["蕎麦"],
        "risks": ["混雑"],
        "weather_or_season_notes": ["雨具"],
        "source_notes": ["fixture"],
        "suitability_reason": "ゆっくり過ごせる",
    }


def test_user_selection_request_accepts_numeric_input():
    request = next(request_user_selection(SimpleNamespace(state={}), sample_recommendation()))

    assert request.response_schema == str | int


def test_route_user_selection_accepts_integer_rank():
    recommendation = sample_recommendation()
    ctx = SimpleNamespace(
        state={STATE_COORDINATOR_RECOMMENDATION: recommendation.model_dump()}
    )

    events = list(route_user_selection(ctx, 2))

    assert events[0].actions.route == ROUTE_SELECTED
    assert events[0].output == "option_2"
    assert ctx.state[STATE_SELECTED_OPTION_ID] == "option_2"


def test_build_selected_option_context_allows_empty_evaluation_json():
    recommendation = sample_recommendation()
    ctx = SimpleNamespace(
        state={
            STATE_TRAVEL_REQUEST: {"raw_user_query": "東京から1泊2日の温泉旅行"},
            STATE_TRAVEL_OPTIONS: [sample_travel_option()],
            STATE_RESEARCH_REPORTS: {"option_1": sample_research_report()},
            STATE_REVISED_EVALUATIONS: "",
            STATE_COORDINATOR_RECOMMENDATION: recommendation.model_dump(),
            STATE_SELECTED_OPTION_ID: "option_1",
        }
    )

    context = build_selected_option_context(ctx, None)

    assert context.selected_option.option_id == "option_1"
    assert context.evaluations == []
    assert ctx.state[STATE_SELECTED_OPTION_CONTEXT] == context.model_dump()
