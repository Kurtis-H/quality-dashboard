"""The built page, in a real browser, checked against its own data.json.

SITE  a built site to check (CI points this at the real build). Without it,
      the fixture data is rendered into a temporary site.
"""

from __future__ import annotations

import functools
import json
import os
import threading
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

from dashboard.collect import totals
from dashboard.render import render

FIXTURE = Path(__file__).parents[1] / "fixtures" / "data.json"


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if os.environ.get("SITE"):
        return Path(os.environ["SITE"])
    out = tmp_path_factory.mktemp("site")
    render(json.loads(FIXTURE.read_text()), out, "Kurtis-H")
    return out


@pytest.fixture(scope="module")
def base_url(site: Path) -> Iterator[str]:
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("PW_EXECUTABLE") or None)
        yield b
        b.close()


@pytest.fixture
def data(site: Path) -> dict:
    return json.loads((site / "data.json").read_text())


def open_page(browser: Browser, base_url: str, scheme: str = "light") -> tuple[Page, list[str], list[str]]:
    page = browser.new_page(color_scheme=scheme)
    errors: list[str] = []
    requests: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: requests.append(r.url))
    page.goto(base_url + "/")
    return page, errors, requests


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_loads_cleanly_and_only_from_itself(browser: Browser, base_url: str, scheme: str) -> None:
    page, errors, requests = open_page(browser, base_url, scheme)
    assert errors == []
    assert all(url.startswith(base_url) for url in requests), requests
    page.close()


def test_the_kpis_match_the_data(browser: Browser, base_url: str, data: dict) -> None:
    t = totals(data)
    page, _, _ = open_page(browser, base_url)
    ci = page.get_by_test_id("tile-ci")
    assert ci.get_attribute("data-passing") == str(t["passing"])
    assert ci.get_attribute("data-repos") == str(t["repos"])
    assert f"{t['passing']} of {t['repos']} repos" in ci.inner_text()
    found = page.get_by_test_id("tile-findings")
    for key in ("fixed", "accepted", "open", "findings"):
        assert found.get_attribute(f"data-{key}") == str(t[key]), key
    assert f"{t['fixed'] + t['accepted']}/{t['findings']}" in found.inner_text()
    assert page.get_by_test_id("tile-open").get_attribute("data-open") == str(t["open"])
    runs = [w for r in data["repos"] for w in r["workflows"]]
    good = sum(
        w["status"] == "completed" and w["conclusion"] in ("success", "skipped", "neutral") for w in runs
    )
    wf = page.get_by_test_id("tile-workflows")
    assert (wf.get_attribute("data-good"), wf.get_attribute("data-runs")) == (str(good), str(len(runs)))
    page.close()


def test_every_repo_has_a_card_with_its_status(browser: Browser, base_url: str, data: dict) -> None:
    page, _, _ = open_page(browser, base_url)
    label = {"passing": "Passing", "failing": "Failing", "running": "Running", "no runs": "No runs"}
    assert page.locator("[data-tile]").count() == len(data["repos"])
    for repo in data["repos"]:
        card = page.locator(f'[data-tile="{repo["name"]}"]')
        assert card.get_attribute("data-status") == repo["status"]
        assert label[repo["status"]] in card.inner_text()
        assert card.locator(".wf").count() == len(repo["workflows"])
    page.close()


@pytest.mark.parametrize("chart", ["chart-assessment", "chart-severity"])
def test_charts_add_up_to_the_findings(browser: Browser, base_url: str, data: dict, chart: str) -> None:
    findings = [f for a in data["assessments"] for f in a["findings"]]
    page, _, _ = open_page(browser, base_url)
    segs = page.get_by_test_id(chart).locator(".seg")
    for status in ("fixed", "accepted", "open"):
        shown = sum(
            int(s.get_attribute("data-count")) for s in segs.all() if s.get_attribute("data-status") == status
        )
        assert shown == sum(f["status"] == status for f in findings), status
    page.close()


def test_the_assessment_chart_matches_each_ledger(browser: Browser, base_url: str, data: dict) -> None:
    page, _, _ = open_page(browser, base_url)
    rows = page.get_by_test_id("chart-assessment").locator(".bar-row").all()
    assert len(rows) == len(data["assessments"])
    for row, a in zip(rows, data["assessments"], strict=True):
        assert a["label"] in row.inner_text()
        assert row.locator(".bar-total").inner_text() == str(len(a["findings"]))
        key = page.locator(f'[data-assessment="{a["repo"]}"] .counts').inner_text()
        for status in ("fixed", "accepted", "open"):
            assert f"{sum(f['status'] == status for f in a['findings'])} {status}" in key
    page.close()


def test_the_page_uses_its_own_font(browser: Browser, base_url: str) -> None:
    page, _, requests = open_page(browser, base_url)
    page.wait_for_load_state("networkidle")
    assert any(u.endswith(".woff2") for u in requests)
    # check() is true for a family that was never defined, so look for the loaded face itself.
    loaded = "[...document.fonts].some(f => f.family.includes('Inter') && f.status === 'loaded')"
    assert page.evaluate(loaded)
    page.close()


@pytest.mark.parametrize("width", [360, 768, 1366])
def test_no_sideways_scroll(browser: Browser, base_url: str, width: int) -> None:
    page = browser.new_page(viewport={"width": width, "height": 800})
    page.goto(base_url + "/")
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    page.close()


def test_every_finding_shows_its_status(browser: Browser, base_url: str, data: dict) -> None:
    page, _, _ = open_page(browser, base_url)
    for assessment in data["assessments"]:
        table = page.locator(f'[data-assessment="{assessment["repo"]}"] table')
        assert table.locator("tbody tr").count() == len(assessment["findings"])
        for f in assessment["findings"]:
            row = table.locator(f'tr[data-finding="{f["id"]}"]')
            assert row.get_attribute("data-status") == f["status"]
            assert f["severity"] in row.inner_text()
    page.close()


def test_structure_is_accessible(browser: Browser, base_url: str) -> None:
    page, _, _ = open_page(browser, base_url)
    assert page.get_by_role("heading", level=1).count() == 1
    for name in ("Findings by assessment", "Findings by severity", "Repositories", "Assessment findings"):
        assert page.get_by_role("heading", name=name).count() == 1, name
    for table in page.locator("table").all():
        assert table.locator("caption").count() == 1
    # Every bar reads out its counts; icons are decoration next to a text label.
    for track in page.locator(".bar-track").all():
        assert track.get_attribute("role") == "img" and track.get_attribute("aria-label")
    assert page.locator("svg.icon:not([aria-hidden='true'])").count() == 0
    page.close()
