# quality-dashboard

One page that shows the health of my whole portfolio: CI status for every repo, and every finding from the three assessments of the booking platform (penetration test, mobile security, fault injection), with what was fixed and what was accepted and why.

**Live page:** https://kurtis-h.github.io/quality-dashboard/

## How it works

A scheduled GitHub Actions job runs daily, on every push to `main` and by hand:

1. **Collect.** [`dashboard/collect.py`](dashboard/collect.py) reads the GitHub API: for each repo, the latest completed run of each of its own workflows on the default branch. One failing workflow marks the repo failing. It also reads each assessment's findings register, `findings.py`, which is the same file that assessment's tests check in its own CI. So the page can't disagree with the reports.
2. **Render.** [`dashboard/render.py`](dashboard/render.py) writes a static page (`index.html`, `style.css`) and the raw `data.json`.
3. **Check.** Playwright opens the built page and compares every number on it with `data.json`: the headline tiles, each repo's CI status, each finding's status and severity. A mismatch fails the job, and nothing is deployed.
4. **Deploy** to GitHub Pages.

## Why it's built this way

- **Fetched code is never run.** The findings registers come from other repos. They're parsed with Python's `ast`, and only literal values are read. A test proves a register with code at the top level is read without that code running.
- **No JavaScript.** The page is plain HTML and CSS with a Content-Security-Policy that allows nothing but its own stylesheet. Every value from the data is escaped, and links can only point to GitHub. Tests try script and image injection through the data and a `javascript:` link.
- **Readable at a glance.** The page opens with a two-sentence verdict, then a build board: every repo as a tile, like the CI wall on a team's TV. Findings get a bar of fixed, accepted and open, then the full ledger.
- **Status never rests on color alone.** Each state has its own icon shape and a text label, and the page follows the system's light or dark setting.
- **Set in Atkinson Hyperlegible,** a typeface designed by the Braille Institute for low-vision readers, self-hosted so the page loads nothing from anywhere else (OFL license in `dashboard/static/fonts/`).
- **Read-only and public.** The job uses its own short-lived token with read access, only for public repo data. There's no server and nothing to host.

## Layout

```
dashboard/
  config.py      the repos and assessments covered, grouped as on my profile
  github.py      the few read-only GitHub API calls
  registers.py   reads a findings.py without running it
  collect.py     builds the data; the CI rollup and the headline totals
  render.py      the static page
  static/        style.css, the favicon and the self-hosted font
tests/
  unit/          parser, collector (against a fake GitHub API), renderer
  e2e/           the built page in a real browser, checked against its data.json
```

## Run it

```bash
pip install --require-hashes -r requirements.txt
python -m playwright install chromium
GITHUB_TOKEN=... python -m dashboard build --out _site   # a token is optional; it raises the rate limit
python -m pytest
SITE=_site python -m pytest tests/e2e                     # check a real build
```

To cover another repo or assessment, add it to [`dashboard/config.py`](dashboard/config.py).
