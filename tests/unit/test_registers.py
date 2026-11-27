"""The register parser reads literals only, and never runs the source."""

from __future__ import annotations

import pytest

from dashboard.registers import RegisterError, parse_register

REGISTER = """
from dataclasses import dataclass

FINDINGS = [
    Finding(
        id="XX-01",
        title="A high one",
        cvss="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:L/A:N",
        owasp="API2:2023",
        status="accepted",
        accepted_because=(
            "Two strings "
            "joined."
        ),
    ),
    Finding(id="XX-02", title="Rated by hand", severity="Low", status="fixed", fixed_in="app#3"),
]
"""


def test_reads_each_finding_in_source_order() -> None:
    findings = parse_register(REGISTER)
    assert [f.id for f in findings] == ["XX-01", "XX-02"]
    assert findings[0].accepted_because == "Two strings joined."
    assert findings[1].fixed_in == "app#3"


def test_computes_severity_from_a_cvss_vector() -> None:
    assert parse_register(REGISTER)[0].severity == "High"  # 8.2


def test_never_executes_the_source(tmp_path) -> None:
    marker = tmp_path / "ran"
    hostile = f'open({str(marker)!r}, "w").write("x")\nraise SystemExit(1)\n' + REGISTER
    parse_register(hostile)
    assert not marker.exists()


def test_refuses_values_that_are_not_literals() -> None:
    with pytest.raises(RegisterError, match="title is not a literal"):
        parse_register('Finding(id="A", title=__import__("os").getcwd(), severity="Low", status="open")')


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("x = 1", "no Finding"),
        ('Finding(id="A", title="t", severity="Severe", status="open")', "unknown severity"),
        ('Finding(id="A", title="t", severity="Low", status="done")', "unknown status"),
        ('Finding(title="t", severity="Low", status="open")', "no id"),
        (
            '[Finding(id="A", title="t", severity="Low", status="open")] * 2\n'
            'Finding(id="A", title="t", severity="Low", status="open")',
            "duplicate",
        ),
        ("Finding(", "not valid Python"),
    ],
)
def test_rejects_a_register_it_cannot_trust(source: str, message: str) -> None:
    with pytest.raises(RegisterError, match=message):
        parse_register(source)
