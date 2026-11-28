"""Rendering: escaping, links, and the headline numbers."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from dashboard.collect import totals
from dashboard.render import ci_note, page, pr_link, render

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "data.json").read_text())


@pytest.fixture
def data() -> dict:
    return copy.deepcopy(FIXTURE)


def test_text_from_the_data_is_escaped(data: dict) -> None:
    data["assessments"][0]["findings"][0]["title"] = '<script>alert(1)</script>"'
    data["repos"][0]["description"] = "<img src=x onerror=alert(1)>"
    html = page(data, "Kurtis-H")
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;&quot;" in html


def test_links_only_ever_point_to_github(data: dict) -> None:
    data["repos"][0]["url"] = "javascript:alert(1)"
    data["repos"][0]["workflows"][0]["url"] = "https://evil.example/run"
    html = page(data, "Kurtis-H")
    assert "javascript:" not in html and "evil.example" not in html


def test_the_page_runs_no_script_and_allows_nothing_external(data: dict) -> None:
    html = page(data, "Kurtis-H")
    assert "<script" not in html
    assert "default-src 'none'; style-src 'self'; img-src 'self'" in html


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("api-performance-lab#17", 'href="https://github.com/Kurtis-H/api-performance-lab/pull/17"'),
        ("not a ref", "not a ref"),
    ],
)
def test_fixed_in_links_to_the_pull_request(ref: str, expected: str) -> None:
    assert expected in pr_link(ref, "Kurtis-H")


def test_ci_note_names_what_is_not_passing(data: dict) -> None:
    assert ci_note(data) == "1 failing, 1 with no runs yet"
    for r in data["repos"]:
        r["status"] = "passing"
    assert ci_note(data) == "none failing"


def test_tiles_show_the_totals(data: dict) -> None:
    t = totals(data)
    html = page(data, "Kurtis-H")
    assert f"{t['passing']} of {t['repos']}" in html
    assert f"{t['fixed']} of {t['findings']}" in html


def test_render_writes_the_site(tmp_path: Path, data: dict) -> None:
    render(data, tmp_path, "Kurtis-H")
    expected = {"index.html", "data.json", "style.css", "favicon.svg", "fonts"}
    assert {p.name for p in tmp_path.iterdir()} == expected
    assert sorted(p.name for p in (tmp_path / "fonts").iterdir()) == [
        "OFL.txt",
        "inter-latin-400-normal.woff2",
        "inter-latin-600-normal.woff2",
        "inter-latin-700-normal.woff2",
    ]
    assert json.loads((tmp_path / "data.json").read_text()) == data


def test_summary_reads_as_plain_sentences(data: dict) -> None:
    from dashboard.render import summary

    for r in data["repos"]:
        r["status"] = "passing"
    for a in data["assessments"]:
        for f in a["findings"]:
            f["status"] = "fixed"
    text = summary(data)
    assert text.startswith(f"All {len(data['repos'])} repos pass CI.")
    assert text.endswith("0 accepted with a reason, and none are open.")
    data["assessments"][0]["findings"][0]["status"] = "open"
    assert summary(data).endswith("1 still open.")


def test_bars_share_one_scale_and_skip_empty_segments() -> None:
    from dashboard.render import stacked_bars

    html = stacked_bars(
        [("Big", {"fixed": 3, "accepted": 1, "open": 0}), ("Small", {"fixed": 1, "accepted": 0, "open": 1})],
        "c",
    )
    assert "seg-open w-25" in html  # 1 of the biggest row's 4
    assert "seg-fixed w-75" in html and "seg-accepted w-25" in html
    assert html.count("seg-open") == 1  # the big row has no open segment


def test_every_bar_width_class_exists() -> None:
    from dashboard.render import STATIC

    css = (STATIC / "style.css").read_text()
    assert all(f".w-{i} {{ width: {i}%; }}" in css for i in range(101))
