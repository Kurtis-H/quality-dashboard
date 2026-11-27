"""python -m dashboard build --out _site   (collect from GitHub, then render)
python -m dashboard render --data data.json --out _site   (render saved data)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dashboard import config
from dashboard.collect import collect, totals
from dashboard.github import client
from dashboard.render import render


def main() -> None:
    parser = argparse.ArgumentParser(prog="dashboard")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--out", type=Path, default=Path("_site"))
    rend = sub.add_parser("render")
    rend.add_argument("--data", type=Path, required=True)
    rend.add_argument("--out", type=Path, default=Path("_site"))
    args = parser.parse_args()

    if args.command == "build":
        with client(os.environ.get("GITHUB_TOKEN")) as gh:
            data = collect(gh)
    else:
        data = json.loads(args.data.read_text())
    render(data, args.out, config.OWNER)
    print(json.dumps(totals(data)))


if __name__ == "__main__":
    main()
