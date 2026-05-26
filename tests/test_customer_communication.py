from __future__ import annotations

from hirenest_support.communication import generate_customer_response_package


def test_customer_communication_redacts_internal_details_and_requires_review() -> None:
    brief = "\n".join(
        [
            "# Coordinator Support Brief",
            "## Case Summary",
            (
                "- Inquiry summary: Apex Robotics reports that interview invitation emails are "
                "not delivered to all candidates for a hiring event."
            ),
            "- Impact scope: all candidates did not receive interview invitations",
            "- Problem category: candidate_communication",
            "## Customer Account Context",
            "- Customer name: Apex Robotics",
            "- Support tier: Premier",
            "- ARR $420000",
            "- Health score 62",
            "## Similar Historical Tickets",
            "- TCK-4101 - Interview invitation delivery failures",
            "## Incident Correlation",
            "- Related active incident: INC-2026-0524-INVITE-DELIVERY (investigating, SEV2)",
            (
                "- Customer-shareable status update: We are investigating delayed interview "
                "invitation delivery for some customers."
            ),
            "## Severity Recommendation",
            "- Recommended severity: SEV2",
            "- SLA update frequency: 60 minutes",
            "- Additional information needed: exact first failure time",
        ]
    )

    package = generate_customer_response_package(brief)

    assert package["subject"] == "Update on interview invitation delivery"
    assert package["requires_human_review"] is True
    assert "SEV2 case" in package["human_review_reason"]
    assert "INC-2026" not in package["customer_response"]
    assert "TCK-" not in package["customer_response"]
    assert "ARR" not in package["customer_response"]
    assert "health score" not in package["customer_response"].lower()
    assert package["disclosure_check"]["omitted_or_softened"] is True


def test_customer_communication_allows_low_risk_informational_response() -> None:
    brief = "\n".join(
        [
            "# Customer Support Escalation Brief",
            "## Case Summary",
            "- Impact scope: one administrator asks how to export a dashboard",
            "- Problem category: reporting",
            "## Customer Account Context",
            "- Support tier: Standard",
            "## Incident Correlation",
            "- Related active incident: None found.",
            "- Customer-shareable status update: No public status update found.",
            "## Severity Recommendation",
            "- Recommended severity: SEV4",
            "- SLA update frequency: 2 business days",
            "- Additional information needed: preferred export format",
        ]
    )

    package = generate_customer_response_package(brief)

    assert package["requires_human_review"] is False
    assert package["disclosure_check"]["safe_to_send"] is True
    assert "preferred export format" in package["customer_response"]
