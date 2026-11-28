"""Collecting from GitHub, against a fake GitHub API."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import httpx
import pytest

from dashboard import collect as collect_module
from dashboard import config
from dashboard.collect import FAILING, NO_RUNS, PASSING, RUNNING, collect, rollup, totals
from dashboard.github import Run, client


def run(status: str = "completed", conclusion: str | None = "success") -> Run:
    return Run("CI", status, conclusion, "https://github.com/x", "2026-11-27T00:00:00Z")


@pytest.mark.parametrize(
    ("runs", "expected"),
    [
        ([], NO_RUNS),
        ([run(), run(conclusion="skipped")], PASSING),
        ([run(), run(conclusion="failure")], FAILING),
        ([run(), run(conclusion="cancelled")], FAILING),
        ([run(), run(status="in_progress", conclusion=None)], RUNNING),
        ([run(status="in_progress", conclusion=None), run(conclusion="failure")], FAILING),
    ],
)
def test_rollup(runs: list[Run], expected: str) -> None:
    assert rollup(runs) == expected


REGISTER = 'Finding(id="A-01", title="t", severity="Medium", status="fixed", fixed_in="app#1")'


def fake_github(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    parts = path.strip("/").split("/")
    repo = parts[2] if len(parts) > 2 else ""
    if path.endswith("/actions/workflows"):
        return httpx.Response(
            200,
            json={
                "workflows": [
                    {"id": 1, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"},
                    {"id": 2, "name": "Dependabot", "path": "dynamic/dependabot/x", "state": "active"},
                    {
                        "id": 3,
                        "name": "Old",
                        "path": ".github/workflows/old.yml",
                        "state": "disabled_manually",
                    },
                    {"id": 4, "name": "Release", "path": ".github/workflows/release.yml", "state": "active"},
                ]
            },
        )
    if "/actions/workflows/" in path:
        assert request.url.params["branch"] == "main"
        assert request.url.params["status"] == "completed"
        wf = parts[-2]
        if wf == "4":  # runs on tags only: none on main
            return httpx.Response(200, json={"workflow_runs": []})
        assert wf == "1", f"should not ask about workflow {wf}"
        conclusion = "failure" if repo == "bug-hunt-lab" else "success"
        return httpx.Response(
            200,
            json={
                "workflow_runs": [
                    {
                        "status": "completed",
                        "conclusion": conclusion,
                        "html_url": f"https://github.com/Kurtis-H/{repo}/actions/runs/9",
                        "updated_at": "2026-11-27T12:00:00Z",
                    }
                ]
            },
        )
    if path.endswith("/contents/findings.py"):
        return httpx.Response(
            200, json={"encoding": "base64", "content": base64.b64encode(REGISTER.encode()).decode()}
        )
    if len(parts) == 3:
        return httpx.Response(
            200,
            json={
                "html_url": f"https://github.com/Kurtis-H/{repo}",
                "description": "" if repo in ("booking-pentest", "vuln-shop") else f"About {repo}",
                "pushed_at": "2026-11-27T10:00:00Z",
                "default_branch": "main",
            },
        )
    return httpx.Response(404)


@pytest.fixture
def data() -> dict:
    with client("t", transport=httpx.MockTransport(fake_github)) as gh:
        return collect(gh, now=datetime(2026, 11, 27, 18, 0, tzinfo=UTC))


def test_collects_every_configured_repo_in_order(data: dict) -> None:
    expected = [name for names in config.GROUPS.values() for name in names]
    assert [r["name"] for r in data["repos"]] == expected


def test_only_the_repos_own_active_workflows_with_runs_count(data: dict) -> None:
    assert {tuple(w["workflow"] for w in r["workflows"]) for r in data["repos"]} == {("CI",)}


def test_a_failing_workflow_marks_its_repo(data: dict) -> None:
    status = {r["name"]: r["status"] for r in data["repos"]}
    assert status["bug-hunt-lab"] == FAILING
    assert sum(s == PASSING for s in status.values()) == len(status) - 1


def test_reads_every_assessment_register(data: dict) -> None:
    assert [a["repo"] for a in data["assessments"]] == list(config.ASSESSMENTS)
    assert all(a["findings"][0]["id"] == "A-01" for a in data["assessments"])


def test_totals(data: dict) -> None:
    n = len(data["repos"])
    assert totals(data) == {
        "repos": n,
        "passing": n - 1,
        "failing": 1,
        "findings": 3,
        "fixed": 3,
        "accepted": 0,
        "open": 0,
    }


def test_data_is_plain_json(data: dict) -> None:
    assert json.loads(json.dumps(data)) == data
    assert data["generated_at"] == "2026-11-27T18:00:00+00:00"


def test_an_api_error_stops_the_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dashboard.github.time.sleep", lambda s: None)

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with client(transport=httpx.MockTransport(broken)) as gh, pytest.raises(httpx.HTTPStatusError):
        collect_module.collect(gh)


def test_transient_errors_are_retried_then_succeed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dashboard.github.time.sleep", lambda s: None)
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        if calls["n"] == 2:
            return httpx.Response(502)
        return fake_github(request)

    with client(transport=httpx.MockTransport(flaky)) as gh:
        assert collect(gh)["repos"]
    assert calls["n"] > 2


def test_a_client_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dashboard.github.time.sleep", lambda s: None)
    calls = {"n": 0}

    def missing(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    with client(transport=httpx.MockTransport(missing)) as gh, pytest.raises(httpx.HTTPStatusError):
        collect(gh)
    assert calls["n"] == 1


def test_an_empty_github_description_falls_back_and_a_real_one_wins(data: dict) -> None:
    by_name = {r["name"]: r["description"] for r in data["repos"]}
    assert by_name["booking-pentest"] == config.FALLBACK_DESCRIPTIONS["booking-pentest"]
    assert by_name["vuln-shop"] == ""  # no fallback: shown empty rather than invented
    assert by_name["api-performance-lab"] == "About api-performance-lab"  # GitHub's text wins


def test_fallbacks_only_name_repos_the_dashboard_covers() -> None:
    covered = {name for names in config.GROUPS.values() for name in names}
    assert set(config.FALLBACK_DESCRIPTIONS) <= covered
