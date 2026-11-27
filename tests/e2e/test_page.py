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


def test_tiles_match_the_data(browser: Browser, base_url: str, data: dict) -> None:
    t = totals(data)
    page, _, _ = open_page(browser, base_url)
    assert f"{t['passing']} of {t['repos']}" in page.get_by_test_id("tile-ci").inner_text()
    assert f"{t['fixed']} of {t['findings']}" in page.get_by_test_id("tile-fixed").inner_text()
    assert page.get_by_test_id("tile-accepted").inner_text().endswith(str(t["accepted"]))
    assert page.get_by_test_id("tile-open").inner_text().endswith(str(t["open"]))
    page.close()


def test_every_repo_shows_its_ci_status(browser: Browser, base_url: str, data: dict) -> None:
    page, _, _ = open_page(browser, base_url)
    for repo in data["repos"]:
        row = page.locator(f'tr[data-repo="{repo["name"]}"]')
        assert row.count() == 1, repo["name"]
        assert row.get_attribute("data-status") == repo["status"]
        label = {"passing": "Passing", "failing": "Failing", "running": "Running", "no runs": "No runs"}
        assert label[repo["status"]] in row.inner_text()
    page.close()


def test_every_finding_shows_its_status(browser: Browser, base_url: str, data: dict) -> None:
    page, _, _ = open_page(browser, base_url)
    for assessment in data["assessments"]:
        table = page.locator(f'table[data-assessment="{assessment["repo"]}"]')
        assert table.locator("tbody tr").count() == len(assessment["findings"])
        for f in assessment["findings"]:
            row = table.locator(f'tr[data-finding="{f["id"]}"]')
            assert row.get_attribute("data-status") == f["status"]
            assert f["severity"] in row.inner_text()
    page.close()


def test_structure_is_accessible(browser: Browser, base_url: str) -> None:
    page, _, _ = open_page(browser, base_url)
    assert page.get_by_role("heading", level=1).count() == 1
    assert page.get_by_role("heading", name="CI on main").count() == 1
    assert page.get_by_role("heading", name="Assessment findings").count() == 1
    for table in page.locator("table").all():
        assert table.locator("caption").count() == 1
    assert page.locator("svg.icon:not([aria-hidden='true'])").count() == 0
    page.close()
