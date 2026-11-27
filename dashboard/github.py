"""The few GitHub REST calls the collector needs. Read-only, public data only."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")


@dataclass(frozen=True)
class Run:
    workflow: str
    status: str  # completed | in_progress | queued | ...
    conclusion: str | None  # success | failure | cancelled | skipped | ...
    url: str
    updated_at: str


def client(token: str | None = None, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(base_url=API, headers=headers, timeout=30, transport=transport)


def repo_info(gh: httpx.Client, owner: str, repo: str) -> dict[str, Any]:
    r = gh.get(f"/repos/{owner}/{repo}")
    r.raise_for_status()
    data = r.json()
    return {
        "description": data.get("description") or "",
        "url": data["html_url"],
        "pushed_at": data.get("pushed_at") or "",
        "default_branch": data.get("default_branch") or "main",
    }


def latest_runs(gh: httpx.Client, owner: str, repo: str, branch: str) -> list[Run]:
    """The latest completed run on `branch` of each of the repo's own active workflows.

    Completed only: a run still going says nothing yet, and this dashboard's
    own workflow is always mid-run while it collects.

    GitHub's built-in workflows (Dependabot, default CodeQL setup) live under
    `dynamic/` and are skipped: they aren't part of the repo's CI. A workflow
    that has never run on the branch (one that runs on tags only) is skipped.
    """
    r = gh.get(f"/repos/{owner}/{repo}/actions/workflows", params={"per_page": 100})
    r.raise_for_status()
    runs = []
    for wf in r.json()["workflows"]:
        if wf["state"] != "active" or not wf["path"].startswith(".github/workflows/"):
            continue
        rr = gh.get(
            f"/repos/{owner}/{repo}/actions/workflows/{wf['id']}/runs",
            params={
                "branch": branch,
                "status": "completed",
                "per_page": 1,
                "exclude_pull_requests": "true",
            },
        )
        rr.raise_for_status()
        found = rr.json()["workflow_runs"]
        if not found:
            continue
        run = found[0]
        runs.append(
            Run(
                workflow=wf["name"],
                status=run["status"],
                conclusion=run.get("conclusion"),
                url=run["html_url"],
                updated_at=run["updated_at"],
            )
        )
    return runs


def file_text(gh: httpx.Client, owner: str, repo: str, path: str) -> str:
    r = gh.get(f"/repos/{owner}/{repo}/contents/{path}")
    r.raise_for_status()
    data = r.json()
    if data.get("encoding") != "base64":
        raise ValueError(f"{repo}/{path}: unexpected encoding {data.get('encoding')!r}")
    return base64.b64decode(data["content"]).decode("utf-8")
