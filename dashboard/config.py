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
    "mobile-security-lab": "Mobile security",
    "resilience-lab": "Fault injection",
}

# One-line descriptions, used only while a repo's GitHub "About" box is empty.
# GitHub's own description always wins, so these can be deleted once set there.
FALLBACK_DESCRIPTIONS: dict[str, str] = {
    "api-performance-lab": (
        "FastAPI and Postgres booking API with six switchable performance problems, "
        "k6 load tests, a regression gate and Pact contract checks"
    ),
    "framework-showdown": (
        "One test plan in Playwright, Cypress, Appium and Maestro, measured over 10 CI runs "
        "each for speed, flakiness and code size"
    ),
    "booking-pentest": (
        "Penetration test of the booking API and web app: a CVSS-scored report where every "
        "finding is a test that runs in CI"
    ),
    "mobile-security-lab": (
        "Security assessment of the booking Android app: the release APK is built and scanned "
        "with MobSF in CI, and every finding is triaged"
    ),
    "resilience-lab": (
        "Fault injection with Toxiproxy: the booking platform under database outages, "
        "latency, dropped connections and a silent API"
    ),
    "supply-chain-lab": (
        "SBOMs, keyless-signed images and SLSA provenance, with a deploy gate proven "
        "to reject tampered images"
    ),
    "security-practice-lab": (
        "Automated OWASP Juice Shop attacks, Atheris fuzzing, and a test runner built "
        "from scratch and checked with mutation testing"
    ),
    "qa-agent-skills": (
        "QA know-how packaged as skills for AI coding agents, with a harness that measures "
        "whether each skill actually helps"
    ),
    "agent-guardrails-lab": (
        "Guardrails for a tool-using AI agent, proven against a worst-case agent that "
        "obeys every prompt injection"
    ),
    "quality-dashboard": (
        "CI status and assessment findings for the whole portfolio on one page, rebuilt "
        "daily and checked against its sources"
    ),
}
