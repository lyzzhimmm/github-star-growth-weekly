# GitHub Star Growth Weekly

Weekly ranking of public GitHub repositories created within the last 36 months and meeting the configured recent star-growth threshold.

## Single source of truth

- `config.json` — ranking rules such as `min_growth` (currently 3000), window length and creation cutoff.
- `scripts/generate_weekly.py` — canonical entry point.
- `scripts/weekly_common.py` — configuration, HTTP helpers and classification.
- `scripts/weekly_sources.py` — GitHub / OSSInsight candidate discovery and history validation.
- `scripts/weekly_render.py` — CSV and interactive HTML rendering.
- `.github/workflows/weekly.yml` — runs automatically every Monday at 07:30 Asia/Shanghai and commits generated output back to `main`.

The ChatGPT scheduled task should not independently recalculate a second ranking. It should read the files produced by this workflow and report the result at 09:00 Asia/Shanghai.

## Output

- `index.html` — latest interactive ranking (GitHub Pages homepage)
- `latest.csv` — latest CSV
- `YYYY-MM-DD-github-star-growth-weekly.html`
- `YYYY-MM-DD-github-star-growth-weekly.csv`
- `archive/YYYY-MM-DD.html`
- `archive/YYYY-MM-DD.csv`
- `data/latest-run.json` — machine-readable run summary
- `data/snapshots/YYYY-MM-DD.json` — current-star audit snapshot

Latest site: https://lyzzhimmm.github.io/github-star-growth-weekly/

## Data policy

Repositories created inside the configured lookback window have an exact baseline of zero. Older repositories require discrete OSSInsight stargazer-history snapshots around the target date. The generator does not use linear interpolation, age-based star estimates, or back-calculation from a previous growth estimate; unverifiable candidates are omitted.
