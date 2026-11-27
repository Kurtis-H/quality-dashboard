"""What the dashboard covers. Edit here to add a repo or an assessment."""

from __future__ import annotations

OWNER = "Kurtis-H"

# Grouped as on the profile README. Order is display order.
GROUPS: dict[str, list[str]] = {
    "The booking platform": [
        "api-performance-lab",
        "booking-web",
        "booking-mobile",
        "platform-probe",
        "locator-lens",
        "framework-showdown",
        "booking-pentest",
        "mobile-security-lab",
        "resilience-lab",
    ],
    "Test frameworks and tooling": ["qa-reference-framework", "bug-hunt-lab", "flaky-hunter"],
    "Security testing": [
        "supply-chain-lab",
        "security-practice-lab",
        "vuln-shop",
        "scan-triage-bot",
    ],
    "AI for QA": [
        "qa-agent-skills",
        "testgen-agent",
        "agent-guardrails-lab",
        "llm-arena",
        "bug-report-enhancer",
    ],
    "This dashboard": ["quality-dashboard"],
}

# Assessments whose findings register (findings.py) the dashboard reads.
ASSESSMENTS: dict[str, str] = {
    "booking-pentest": "Penetration test",
    "mobile-security-lab": "Mobile security assessment",
    "resilience-lab": "Fault injection",
}
