"""Render the collected data as a static page: index.html, style.css, data.json.

Every value from the data is escaped. The page has no JavaScript, and its
Content-Security-Policy allows nothing but its own stylesheet.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from dashboard.collect import FAILING, NO_RUNS, PASSING, RUNNING, totals

STATIC = Path(__file__).parent / "static"
CSP = (
    "default-src 'none'; style-src 'self'; img-src 'self'; font-src 'self'; "
    "base-uri 'none'; form-action 'none'"
)

# Status icons: a shape for each state, so it never rests on color alone.
ICONS = {
    "good": '<path d="M3.5 8.5l3 3 6-7"/>',
    "bad": '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>',
    "busy": '<circle cx="8" cy="8" r="5.5"/><path d="M8 5v3.5l2 1.5"/>',
    "none": '<path d="M4 8h8"/>',
}
CI_STATES = {
    PASSING: ("good", "Passing"),
    FAILING: ("bad", "Failing"),
    RUNNING: ("busy", "Running"),
    NO_RUNS: ("none", "No runs"),
}
RUN_STATES = {"success": "good", "skipped": "good", "neutral": "good"}
FINDING_STATES = {"fixed": ("good", "Fixed"), "accepted": ("none", "Accepted"), "open": ("bad", "Open")}
PR_REF = re.compile(r"^([A-Za-z0-9_.-]+)#(\d+)$")


def icon(kind: str) -> str:
    return (
        f'<svg class="icon {kind}" viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        f"{ICONS[kind]}</svg>"
    )


def badge(kind: str, label: str) -> str:
    return f'<span class="badge {kind}">{icon(kind)}{escape(label)}</span>'


def link(url: str, text: str) -> str:
    if not url.startswith("https://github.com/"):
        return escape(text)  # only ever link to GitHub
    return f'<a href="{escape(url)}">{escape(text)}</a>'


def pr_link(ref: str, owner: str) -> str:
    m = PR_REF.match(ref)
    if not m:
        return escape(ref)
    return link(f"https://github.com/{owner}/{m[1]}/pull/{m[2]}", ref)


def when(iso: str) -> str:
    if not iso:
        return ""
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return f'<time datetime="{escape(iso)}">{t.strftime("%-d %b %Y")}</time>'


def ci_note(data: dict[str, Any]) -> str:
    """What the repos that aren't passing are doing, e.g. "1 failing, 1 with no runs yet"."""
    labels = {FAILING: "failing", RUNNING: "running", NO_RUNS: "with no runs yet"}
    counts = [
        f"{n} {label}"
        for state, label in labels.items()
        if (n := sum(r["status"] == state for r in data["repos"]))
    ]
    return ", ".join(counts) if counts else "none failing"


def verdict(data: dict[str, Any]) -> str:
    """The headline: two plain sentences a reader gets before anything else."""
    t = totals(data)
    if t["passing"] == t["repos"]:
        ci = f"All {t['repos']} repos pass CI."
    else:
        ci = f"{t['passing']} of {t['repos']} repos pass CI ({ci_note(data)})."
    is_are = {1: "is"}
    still_open = (
        "none are open" if not t["open"] else f"{t['open']} {is_are.get(t['open'], 'are')} still open"
    )
    findings = (
        f"{t['fixed']} of {t['findings']} security and resilience findings are fixed and retested, "
        f"{t['accepted']} {is_are.get(t['accepted'], 'are')} accepted with a reason, and {still_open}."
    )
    return (
        f'<p class="verdict"><span data-testid="tile-ci" data-passing="{t["passing"]}" '
        f'data-repos="{t["repos"]}">{escape(ci)}</span> '
        f'<span data-testid="tile-findings" data-fixed="{t["fixed"]}" data-accepted="{t["accepted"]}" '
        f'data-open="{t["open"]}" data-findings="{t["findings"]}">{escape(findings)}</span></p>'
    )


def radiator(data: dict[str, Any]) -> str:
    """Every repo as a tile, grouped as on the profile: the build board at a glance."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in data["repos"]:
        groups.setdefault(r["group"], []).append(r)
    parts = [
        '<section class="radiator" aria-labelledby="board"><h2 id="board">Build board</h2>',
        '<p class="lede">Each repo\'s CI on its main branch. A cross marks a failing workflow.</p>',
    ]
    for group, repos in groups.items():
        tiles = []
        for r in repos:
            kind, label = CI_STATES[r["status"]]
            name = escape(r["name"])
            href = escape(r["url"]) if r["url"].startswith("https://github.com/") else ""
            tag = f'<a href="{href}"' if href else "<div"
            close = "</a>" if href else "</div>"
            tiles.append(
                f'<li>{tag} class="tile {kind}" data-tile="{name}" data-status="{escape(r["status"])}">'
                f'{icon(kind)}<span class="tile-name">{name}</span>'
                f'<span class="tile-state">{escape(label)}</span>{close}</li>'
            )
        parts.append(f'<h3>{escape(group)}</h3><ul class="tiles" role="list">{"".join(tiles)}</ul>')
    parts.append("</section>")
    return "\n".join(parts)


def bar(findings: list[dict[str, Any]]) -> str:
    """A segmented bar of fixed, accepted and open, drawn in SVG: the CSP allows no inline styles."""
    total = len(findings) or 1
    x = 0.0
    rects = []
    for status in ("fixed", "accepted", "open"):
        n = sum(f["status"] == status for f in findings)
        if n:
            w = 100 * n / total
            rects.append(
                f'<rect class="seg-{status}" x="{x:.3f}" y="0" width="{max(w - 0.6, 0.4):.3f}" height="8" rx="2"/>'
            )
            x += w
    return f'<svg class="bar" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true" focusable="false">{"".join(rects)}</svg>'


def findings_section(data: dict[str, Any], owner: str) -> str:
    parts = [
        '<section aria-labelledby="findings"><h2 id="findings">Assessment findings</h2>',
        '<p class="lede">Read from each assessment\'s findings register, the same file its tests check in CI.</p>',
    ]
    for a in data["assessments"]:
        fs = a["findings"]
        n = {s: sum(f["status"] == s for f in fs) for s in ("fixed", "accepted", "open")}
        rows = []
        for f in fs:
            kind, label = FINDING_STATES[f["status"]]
            detail = (
                pr_link(f["fixed_in"], owner) if f["status"] == "fixed" else escape(f["accepted_because"])
            )
            sev = escape(f["severity"])
            rows.append(
                f'<tr data-finding="{escape(f["id"])}" data-status="{escape(f["status"])}">'
                f'<th scope="row">{escape(f["id"])}</th><td>{escape(f["title"])}</td>'
                f'<td><span class="sev sev-{sev.lower()}">{sev}</span></td>'
                f"<td>{badge(kind, label)}</td><td>{detail}</td></tr>"
            )
        parts.append(
            f'<div class="assessment" data-assessment="{escape(a["repo"])}">'
            f'<div class="assessment-head"><h3>{escape(a["label"])}</h3>'
            f'<p class="assessment-links">{link(a["url"], a["repo"])}, {link(a["report_url"], "the report")}</p></div>'
            f'{bar(fs)}<p class="bar-key"><span class="k-fixed">{n["fixed"]} fixed</span>'
            f'<span class="k-accepted">{n["accepted"]} accepted</span><span class="k-open">{n["open"]} open</span></p>'
            f'<table class="findings"><caption class="visually-hidden">{escape(a["label"])} findings</caption>'
            '<colgroup><col class="c-id"><col class="c-title"><col class="c-sev"><col class="c-status"><col class="c-detail"></colgroup>'
            '<thead><tr><th scope="col">ID</th><th scope="col">Finding</th><th scope="col">Severity</th>'
            '<th scope="col">Status</th><th scope="col">Fix, or why accepted</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>"
        )
    parts.append("</section>")
    return "\n".join(parts)


def repo_rows(repos: list[dict[str, Any]]) -> str:
    rows = []
    for r in repos:
        kind, label = CI_STATES[r["status"]]
        runs = " ".join(
            f'<span class="run">{icon(RUN_STATES.get(w["conclusion"] or "", "busy" if w["status"] != "completed" else "bad"))}'
            f"{link(w['url'], w['workflow'])}</span>"
            for w in r["workflows"]
        )
        rows.append(
            f'<tr data-repo="{escape(r["name"])}" data-status="{escape(r["status"])}">'
            f'<th scope="row">{link(r["url"], r["name"])}<span class="desc">{escape(r["description"])}</span></th>'
            f'<td>{badge(kind, label)}</td><td class="runs">{runs}</td><td>{when(r["pushed_at"])}</td></tr>'
        )
    return "\n".join(rows)


def ci_section(data: dict[str, Any]) -> str:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in data["repos"]:
        groups.setdefault(r["group"], []).append(r)
    parts = [
        '<section aria-labelledby="ci"><h2 id="ci">Workflow detail</h2>',
        '<p class="lede">The latest completed run of each workflow on the default branch. One failing workflow marks the repo failing.</p>',
    ]
    for group, repos in groups.items():
        parts.append(
            f'<table class="ci"><caption>{escape(group)}</caption>'
            '<colgroup><col class="c-repo"><col class="c-ci"><col class="c-runs"><col class="c-push"></colgroup>'
            '<thead><tr><th scope="col">Repo</th>'
            '<th scope="col">CI</th><th scope="col">Workflows</th><th scope="col">Last push</th></tr></thead>'
            f"<tbody>{repo_rows(repos)}</tbody></table>"
        )
    parts.append("</section>")
    return "\n".join(parts)


def page(data: dict[str, Any], owner: str) -> str:
    t = totals(data)
    generated = datetime.fromisoformat(data["generated_at"])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>Quality dashboard: Kurtis H</title>
<meta name="description" content="CI status for {t["repos"]} portfolio repos and every security and resilience finding, rebuilt daily.">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="masthead">
<h1>Quality dashboard</h1>
<p class="byline">{link(f"https://github.com/{owner}", "Kurtis H")}, QA engineer. Updated <time datetime="{escape(data["generated_at"])}">{generated.strftime("%-d %b %Y at %H:%M UTC")}</time>.</p>
</header>
<main>
{verdict(data)}
{radiator(data)}
{findings_section(data, owner)}
{ci_section(data)}
</main>
<footer>
<p>Rebuilt daily and on every change by {link(f"https://github.com/{owner}/quality-dashboard", "quality-dashboard")}. A scheduled job reads the GitHub API and each assessment's findings register, a browser test checks every number on this page against its sources, and only then is it published. The raw data is in <a href="data.json">data.json</a>.</p>
</footer>
</body>
</html>
"""


def render(data: dict[str, Any], out: Path, owner: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(data, owner))
    (out / "data.json").write_text(json.dumps(data, indent=2))
    for name in ("style.css", "favicon.svg"):
        shutil.copy(STATIC / name, out / name)
    shutil.copytree(STATIC / "fonts", out / "fonts", dirs_exist_ok=True)
