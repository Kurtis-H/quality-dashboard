"""Collect everything the page shows into one JSON-able dict."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx

from dashboard import config
from dashboard.github import Run, file_text, latest_runs, repo_info
from dashboard.registers import parse_register

# How a repo's CI reads, from its workflows' latest runs on the default branch.
PASSING, FAILING, RUNNING, NO_RUNS = "passing", "failing", "running", "no runs"
GOOD = {"success", "skipped", "neutral"}


def rollup(runs: list[Run]) -> str:
    """Failing beats running beats passing: one red workflow makes the repo red."""
    if not runs:
        return NO_RUNS
    if any(r.status == "completed" and r.conclusion not in GOOD for r in runs):
        return FAILING
    if any(r.status != "completed" for r in runs):
        return RUNNING
    return PASSING


def collect(gh: httpx.Client, now: datetime | None = None) -> dict[str, Any]:
    repos = []
    for group, names in config.GROUPS.items():
        for name in names:
            info = repo_info(gh, config.OWNER, name)
            runs = latest_runs(gh, config.OWNER, name, info["default_branch"])
            repos.append(
                {
                    "name": name,
                    "group": group,
                    **info,
                    "status": rollup(runs),
                    "workflows": [asdict(r) for r in runs],
                }
            )
    assessments = []
    for name, label in config.ASSESSMENTS.items():
        findings = parse_register(file_text(gh, config.OWNER, name, "findings.py"))
        assessments.append(
            {
                "repo": name,
                "label": label,
                "url": f"https://github.com/{config.OWNER}/{name}",
                "report_url": f"https://github.com/{config.OWNER}/{name}/blob/main/REPORT.md",
                "findings": [asdict(f) for f in findings],
            }
        )
    return {
        "generated_at": (now or datetime.now(UTC)).replace(microsecond=0).isoformat(),
        "repos": repos,
        "assessments": assessments,
    }


def totals(data: dict[str, Any]) -> dict[str, int]:
    """The headline numbers. The page and its tests both use this."""
    findings = [f for a in data["assessments"] for f in a["findings"]]
    return {
        "repos": len(data["repos"]),
        "passing": sum(r["status"] == PASSING for r in data["repos"]),
        "failing": sum(r["status"] == FAILING for r in data["repos"]),
        "findings": len(findings),
        "fixed": sum(f["status"] == "fixed" for f in findings),
        "accepted": sum(f["status"] == "accepted" for f in findings),
        "open": sum(f["status"] == "open" for f in findings),
    }
