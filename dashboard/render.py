"""Render the collected data as a static dashboard: index.html, style.css, data.json.

Every value from the data is escaped. The page has no JavaScript, and its
Content-Security-Policy allows nothing but its own stylesheet and font, so
charts are SVG drawn with attributes (inline styles would be blocked) and
their tooltips are SVG <title> elements.
"""

from __future__ import annotations

import json
import math
import re
import shutil
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from dashboard.collect import FAILING, NO_RUNS, PASSING, RUNNING, totals

Data = dict[str, Any]

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
STATUSES = ("fixed", "accepted", "open")
SEVERITIES = ("Critical", "High", "Medium", "Low")
PR_REF = re.compile(r"^([A-Za-z0-9_.-]+)#(\d+)$")


def icon(kind: str, cls: str = "icon") -> str:
    return (
        f'<svg class="{cls} {kind}" viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        f"{ICONS[kind]}</svg>"
    )


def badge(kind: str, label: str) -> str:
    return f'<span class="badge {kind}">{icon(kind)}{escape(label)}</span>'


def link(url: str, text: str, cls: str = "") -> str:
    if not url.startswith("https://github.com/"):
        return escape(text)  # only ever link to GitHub
    attr = f' class="{cls}"' if cls else ""
    return f'<a{attr} href="{escape(url)}">{escape(text)}</a>'


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


def ci_note(data: Data) -> str:
    """What the repos that aren't passing are doing, e.g. "1 failing, 1 with no runs yet"."""
    labels = {FAILING: "failing", RUNNING: "running", NO_RUNS: "with no runs yet"}
    counts = [
        f"{n} {label}"
        for state, label in labels.items()
        if (n := sum(r["status"] == state for r in data["repos"]))
    ]
    return ", ".join(counts) if counts else "none failing"


def summary(data: Data) -> str:
    """One plain sentence under the header: the whole page in words."""
    t = totals(data)
    ci = (
        f"All {t['repos']} repos pass CI"
        if t["passing"] == t["repos"]
        else f"{t['passing']} of {t['repos']} repos pass CI ({ci_note(data)})"
    )
    still_open = "none are open" if not t["open"] else f"{t['open']} still open"
    return (
        f"{ci}. {t['fixed']} of {t['findings']} findings are fixed and retested, "
        f"{t['accepted']} accepted with a reason, and {still_open}."
    )


def workflow_totals(data: Data) -> tuple[int, int]:
    runs = [w for r in data["repos"] for w in r["workflows"]]
    good = sum(w["status"] == "completed" and (w["conclusion"] or "") in RUN_STATES for w in runs)
    return good, len(runs)


# Charts --------------------------------------------------------------------


def ring(value: int, total: int, tone: str) -> str:
    """A ring gauge: the arc's length is value / total."""
    r = 30
    c = 2 * math.pi * r
    share = value / total if total else 0
    arc = (
        f'<circle class="ring-arc {tone}" cx="40" cy="40" r="{r}" stroke-dasharray="{c * share:.2f} {c:.2f}" '
        'transform="rotate(-90 40 40)"/>'
        if share
        else ""
    )
    return (
        '<svg class="ring" viewBox="0 0 80 80" aria-hidden="true" focusable="false">'
        f'<circle class="ring-track" cx="40" cy="40" r="{r}"/>{arc}</svg>'
    )


def kpi(test_id: str, attrs: str, label: str, value: str, note: str, gauge: str) -> str:
    return (
        f'<article class="kpi" data-testid="{test_id}" {attrs}>'
        f'<div class="kpi-gauge">{gauge}<span class="kpi-value">{escape(value)}</span></div>'
        f'<h2 class="kpi-label">{escape(label)}</h2><p class="kpi-note">{escape(note)}</p></article>'
    )


def kpis(data: Data) -> str:
    t = totals(data)
    good_runs, runs = workflow_totals(data)
    resolved = t["fixed"] + t["accepted"]
    pct = round(100 * t["passing"] / t["repos"]) if t["repos"] else 0
    return (
        '<div class="kpis">'
        + "".join(
            [
                kpi(
                    "tile-ci",
                    f'data-passing="{t["passing"]}" data-repos="{t["repos"]}"',
                    "Repos passing CI",
                    f"{pct}%",
                    f"{t['passing']} of {t['repos']} repos, {ci_note(data)}",
                    ring(t["passing"], t["repos"], "good" if t["passing"] == t["repos"] else "bad"),
                ),
                kpi(
                    "tile-workflows",
                    f'data-good="{good_runs}" data-runs="{runs}"',
                    "Workflows green",
                    str(good_runs),
                    f"of {runs} workflows on main",
                    ring(good_runs, runs, "good" if good_runs == runs else "bad"),
                ),
                kpi(
                    "tile-findings",
                    f'data-fixed="{t["fixed"]}" data-accepted="{t["accepted"]}" data-open="{t["open"]}" '
                    f'data-findings="{t["findings"]}"',
                    "Findings resolved",
                    f"{resolved}/{t['findings']}",
                    f"{t['fixed']} fixed and retested, {t['accepted']} accepted",
                    ring(resolved, t["findings"], "good" if resolved == t["findings"] else "bad"),
                ),
                kpi(
                    "tile-open",
                    f'data-open="{t["open"]}"',
                    "Open findings",
                    str(t["open"]),
                    "across 3 assessments" if not t["open"] else "still to fix or accept",
                    ring(t["open"], t["findings"], "bad") if t["open"] else icon("good", "kpi-icon"),
                ),
            ]
        )
        + "</div>"
    )


def stacked_bars(rows: list[tuple[str, dict[str, int]]], test_id: str) -> str:
    """Horizontal bars, one per row, split into fixed / accepted / open.

    HTML, so labels stay readable at any width. Widths are whole-percent
    classes (.w-0 to .w-100 in style.css) because the CSP blocks inline
    styles. Every bar is to one scale, the largest row, so lengths compare.
    """
    biggest = max((sum(c.values()) for _, c in rows), default=1) or 1
    out = [f'<div class="bars" data-testid="{test_id}">']
    for name, counts in rows:
        segs = []
        for status in STATUSES:
            n = counts[status]
            if n:
                segs.append(
                    f'<span class="seg seg-{status} w-{round(100 * n / biggest)}" data-status="{status}" '
                    f'data-count="{n}" title="{escape(name)}: {n} {status}"></span>'
                )
        total = sum(counts.values())
        words = ", ".join(f"{counts[s]} {s}" for s in STATUSES if counts[s])
        out.append(
            f'<div class="bar-row"><span class="bar-label">{escape(name)}</span>'
            f'<span class="bar-track" role="img" aria-label="{escape(name)}: {escape(words)}">{"".join(segs)}</span>'
            f'<span class="bar-total">{total}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def legend() -> str:
    return (
        '<p class="legend"><span class="k-fixed">Fixed and retested</span>'
        '<span class="k-accepted">Accepted with a reason</span><span class="k-open">Open</span></p>'
    )


def charts(data: Data) -> str:
    by_assessment = [
        (a["label"], {s: sum(f["status"] == s for f in a["findings"]) for s in STATUSES})
        for a in data["assessments"]
    ]
    findings = [f for a in data["assessments"] for f in a["findings"]]
    by_severity = [
        (sev, {s: sum(f["status"] == s and f["severity"] == sev for f in findings) for s in STATUSES})
        for sev in SEVERITIES
        if any(f["severity"] == sev for f in findings)
    ]
    return (
        '<div class="grid-2">'
        '<section class="panel" aria-labelledby="by-assessment"><header class="panel-head">'
        '<h2 id="by-assessment">Findings by assessment</h2>'
        "<p>Penetration test, mobile security and fault injection</p></header>"
        f"{stacked_bars(by_assessment, 'chart-assessment')}{legend()}</section>"
        '<section class="panel" aria-labelledby="by-severity"><header class="panel-head">'
        '<h2 id="by-severity">Findings by severity</h2>'
        "<p>Rated with CVSS 3.1 or by the assessment</p></header>"
        f"{stacked_bars(by_severity, 'chart-severity')}{legend()}</section>"
        "</div>"
    )


# Repositories and findings -------------------------------------------------


def repos_panel(data: Data) -> str:
    cards = []
    for r in data["repos"]:
        kind, label = CI_STATES[r["status"]]
        dots = "".join(
            f"<li>{link(w['url'], w['workflow'], 'wf ' + RUN_STATES.get(w['conclusion'] or '', 'bad' if w['status'] == 'completed' else 'busy'))}</li>"
            for w in r["workflows"]
        )
        cards.append(
            f'<li class="repo {kind}" data-tile="{escape(r["name"])}" data-status="{escape(r["status"])}">'
            f'<div class="repo-top">{link(r["url"], r["name"], "repo-name")}'
            f'<span class="pill {kind}">{icon(kind)}{escape(label)}</span></div>'
            f'<p class="repo-group">{escape(r["group"])}</p>'
            f'<p class="repo-desc">{escape(r["description"])}</p>'
            f'<div class="repo-foot"><ul class="wfs" aria-label="Workflows">{dots}</ul>'
            f'<span class="repo-push">Pushed {when(r["pushed_at"])}</span></div></li>'
        )
    return (
        '<section class="panel" aria-labelledby="repos"><header class="panel-head">'
        '<h2 id="repos">Repositories</h2>'
        "<p>Latest completed run of each workflow on main. One failing workflow marks the repo failing.</p>"
        f'</header><ul class="repos" role="list">{"".join(cards)}</ul></section>'
    )


def findings_panel(data: Data, owner: str) -> str:
    blocks = []
    for a in data["assessments"]:
        n = {s: sum(f["status"] == s for f in a["findings"]) for s in STATUSES}
        rows = []
        for f in a["findings"]:
            kind, label = FINDING_STATES[f["status"]]
            detail = (
                pr_link(f["fixed_in"], owner) if f["status"] == "fixed" else escape(f["accepted_because"])
            )
            sev = escape(f["severity"])
            rows.append(
                f'<tr data-finding="{escape(f["id"])}" data-status="{escape(f["status"])}">'
                f'<th scope="row">{escape(f["id"])}</th><td class="f-title">{escape(f["title"])}</td>'
                f'<td><span class="sev sev-{sev.lower()}">{sev}</span></td>'
                f'<td>{badge(kind, label)}</td><td class="f-detail">{detail}</td></tr>'
            )
        blocks.append(
            f'<div class="assessment" data-assessment="{escape(a["repo"])}">'
            f'<div class="assessment-head"><h3>{escape(a["label"])}</h3>'
            f'<p class="counts"><span class="k-fixed">{n["fixed"]} fixed</span>'
            f'<span class="k-accepted">{n["accepted"]} accepted</span><span class="k-open">{n["open"]} open</span></p>'
            f'<p class="assessment-links">{link(a["url"], a["repo"])} {link(a["report_url"], "Report")}</p></div>'
            f'<table class="findings"><caption class="visually-hidden">{escape(a["label"])} findings</caption>'
            '<thead><tr><th scope="col">ID</th><th scope="col">Finding</th><th scope="col">Severity</th>'
            '<th scope="col">Status</th><th scope="col">Fix, or why accepted</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>"
        )
    return (
        '<section class="panel" aria-labelledby="findings"><header class="panel-head">'
        '<h2 id="findings">Assessment findings</h2>'
        "<p>Read from each assessment's findings register, the same file its tests check in CI.</p>"
        f"</header>{''.join(blocks)}</section>"
    )


def page(data: Data, owner: str) -> str:
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
<header class="topbar">
<div class="topbar-inner">
<div class="brand">{icon("good", "brand-mark")}<div><h1>Quality dashboard</h1>
<p class="brand-sub">{link(f"https://github.com/{owner}", "Kurtis H")}, QA engineer</p></div></div>
<p class="updated">Updated <time datetime="{escape(data["generated_at"])}">{generated.strftime("%-d %b %Y, %H:%M UTC")}</time></p>
</div>
</header>
<main>
<p class="summary">{escape(summary(data))}</p>
{kpis(data)}
{charts(data)}
{findings_panel(data, owner)}
{repos_panel(data)}
</main>
<footer>
<p>Rebuilt daily and on every change by {link(f"https://github.com/{owner}/quality-dashboard", "quality-dashboard")}. A scheduled job reads the GitHub API and each assessment's findings register, a browser test checks every number here against its sources, and only then is the page published. Raw data: <a href="data.json">data.json</a>.</p>
</footer>
</body>
</html>
"""


def render(data: Data, out: Path, owner: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(data, owner))
    (out / "data.json").write_text(json.dumps(data, indent=2))
    for name in ("style.css", "favicon.svg"):
        shutil.copy(STATIC / name, out / name)
    shutil.copytree(STATIC / "fonts", out / "fonts", dirs_exist_ok=True)
