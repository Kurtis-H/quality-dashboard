"""Read a findings register (findings.py) without running it.

The registers live in other repos. Their source is parsed with `ast` and only
literal keyword arguments of `Finding(...)` calls are read, so nothing fetched
from the network is ever executed.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from cvss import CVSS3

FIELDS = ("id", "title", "severity", "cvss", "status", "fixed_in", "accepted_because")
STATUSES = ("open", "accepted", "fixed")
SEVERITIES = ("Critical", "High", "Medium", "Low")


class RegisterError(ValueError):
    """The register couldn't be read as expected."""


@dataclass(frozen=True)
class Finding:
    id: str
    title: str
    severity: str
    status: str
    fixed_in: str = ""
    accepted_because: str = ""


def _literal_kwargs(call: ast.Call) -> dict[str, object]:
    values: dict[str, object] = {}
    for kw in call.keywords:
        if kw.arg in FIELDS:
            try:
                values[kw.arg] = ast.literal_eval(kw.value)
            except ValueError as e:
                raise RegisterError(f"{kw.arg} is not a literal (line {kw.value.lineno})") from e
    return values


def parse_register(source: str) -> list[Finding]:
    """Every `Finding(...)` call in the source, in order."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise RegisterError(f"not valid Python: {e}") from e
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Finding":
            findings.append((node.lineno, _to_finding(_literal_kwargs(node))))
    if not findings:
        raise RegisterError("no Finding(...) entries found")
    ordered = [f for _, f in sorted(findings, key=lambda pair: pair[0])]
    ids = [f.id for f in ordered]
    if len(set(ids)) != len(ids):
        raise RegisterError(f"duplicate finding ids: {ids}")
    return ordered


def _to_finding(values: dict[str, object]) -> Finding:
    for required in ("id", "title", "status"):
        if not isinstance(values.get(required), str):
            raise RegisterError(f"a finding has no {required}: {values}")
    severity = values.get("severity")
    if severity is None and isinstance(values.get("cvss"), str):
        severity = str(CVSS3(str(values["cvss"])).severities()[0])
    if severity not in SEVERITIES:
        raise RegisterError(f"{values['id']}: unknown severity {severity!r}")
    status = str(values["status"])
    if status not in STATUSES:
        raise RegisterError(f"{values['id']}: unknown status {status!r}")
    return Finding(
        id=str(values["id"]),
        title=str(values["title"]),
        severity=str(severity),
        status=status,
        fixed_in=str(values.get("fixed_in") or ""),
        accepted_because=str(values.get("accepted_because") or ""),
    )
