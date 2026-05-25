from __future__ import annotations

from typing import Any

from acmedesk_support.intake import parse_case


def recommend_diagnostics(inquiry: str) -> dict[str, Any]:
    intake = parse_case(inquiry)
    return {
        "category": intake.category,
        "impact_scope": intake.impact_scope,
        "initial_urgency": intake.initial_urgency,
        "diagnostic_focus": _diagnostic_focus(intake.category),
        "evidence_to_collect": _evidence_to_collect(intake.category),
        "clarification_questions": _clarification_questions(inquiry, intake.category),
        "customer_safe_next_steps": _customer_safe_next_steps(intake.category),
    }


def _diagnostic_focus(category: str) -> list[str]:
    if category == "authentication":
        return [
            "Compare SP-initiated and IdP-initiated login behavior.",
            "Check recent IdP metadata, certificate, and ACS URL changes.",
            "Separate tenant-specific configuration symptoms from broad service symptoms.",
        ]
    if category == "billing":
        return [
            "Compare invoice period, seat changes, proration, and contract terms.",
            "Identify whether a billing operations correction or explanation is needed.",
        ]
    if category == "integrations":
        return [
            "Check endpoint responses, retry history, queue age, and rate-limit signals.",
            "Confirm whether replay or customer endpoint mitigation is available.",
        ]
    if category == "performance":
        return [
            "Compare affected pages, regions, browser conditions, and time windows.",
            "Check whether symptoms match a known degradation or local environment issue.",
        ]
    return [
        "Classify the affected workflow and collect first-failure timing.",
        "Confirm customer, impact scope, and visible error or symptom.",
    ]


def _evidence_to_collect(category: str) -> list[str]:
    if category == "authentication":
        return [
            "Affected user count",
            "First failure time",
            "Sanitized SAML error or screenshot",
            "Recent IdP certificate or metadata change time",
            "Whether password or bypass login works",
        ]
    if category == "billing":
        return [
            "Invoice number",
            "Billing period",
            "Expected amount",
            "Seat-change dates and counts",
            "Contract or order form reference",
        ]
    if category == "integrations":
        return [
            "Affected endpoint or integration name",
            "Example event IDs",
            "Observed delay or failure window",
            "Recent endpoint response codes",
            "Replay requirements",
        ]
    return ["Affected users", "First observed time", "Screenshots or error messages"]


def _clarification_questions(inquiry: str, category: str) -> list[str]:
    lowered = inquiry.lower()
    questions: list[str] = []
    known_customers = ["contoso", "globex", "initech", "umbrella", "northwind"]
    if not any(word in lowered for word in known_customers):
        questions.append("Which customer or tenant is affected?")
    if category == "authentication" and not any(
        word in lowered for word in ["all users", "all employees", "全社員"]
    ):
        questions.append("Are all users affected, or only a subset?")
    if category == "billing" and "invoice" not in lowered and "請求" not in lowered:
        questions.append("Which invoice number and billing period should be reviewed?")
    if category == "integrations" and "event" not in lowered and "endpoint" not in lowered:
        questions.append("Can the customer share example event IDs or affected endpoints?")
    if not any(word in lowered for word in ["since", "yesterday", "today", "時", "first"]):
        questions.append("When did the issue first start?")
    return questions


def _customer_safe_next_steps(category: str) -> list[str]:
    if category == "authentication":
        return [
            "Ask for sanitized sign-in errors and affected scope.",
            "Confirm recent IdP changes before stating a cause.",
        ]
    if category == "billing":
        return [
            "Ask for the invoice number and expected amount.",
            "Offer a line-item review before asserting invoice correctness.",
        ]
    if category == "integrations":
        return [
            "Ask for example events and endpoint response behavior.",
            "Confirm whether replay is needed after diagnosis.",
        ]
    return ["Ask for scope, timing, and visible symptoms."]
