from __future__ import annotations

from acmedesk_support.diagnostics import recommend_diagnostics


def test_diagnostics_returns_authentication_evidence_gaps() -> None:
    diagnostics = recommend_diagnostics("Contoso SAML SSO login fails for some users.")

    assert diagnostics["category"] == "authentication"
    assert "Sanitized SAML error or screenshot" in diagnostics["evidence_to_collect"]
    assert any("all users" in question for question in diagnostics["clarification_questions"])


def test_diagnostics_returns_billing_evidence_gaps() -> None:
    diagnostics = recommend_diagnostics("Globex says the invoice is higher than expected.")

    assert diagnostics["category"] == "billing"
    assert "Expected amount" in diagnostics["evidence_to_collect"]
    assert diagnostics["customer_safe_next_steps"]
