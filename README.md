# GitHub Star Growth Weekly

Weekly ranking of public GitHub repositories created within the last 36 months and meeting the configured recent star-growth threshold.

## Single source of truth

- `config.json` — ranking rules and output-language settings. The growth threshold is currently 3000.
- `scripts/generate_weekly.py` — canonical entry point.
- `scripts/weekly_common.py` — configuration, HTTP helpers and classification.
- `scripts/weekly_sources.py` — GitHub / OSSInsight candidate discovery and history validation.
- `scripts/weekly_i18n.py` — Simplified Chinese localization, validation and cache.
- `scripts/weekly_render.py` — CSV and interactive HTML rendering.
- `.github/workflows/weekly.yml` — runs every Monday at 06:15 Asia/Shanghai and commits generated output back to `main`.

The ChatGPT scheduled task reads the files produced by this workflow and reports the result at 09:00 Asia/Shanghai. It does not independently calculate a second ranking.

## Chinese descriptions

The `主要用途` column must be Simplified Chinese. Official product names and necessary technical terms such as API, CLI and Agent may remain in English, but full English sentences are rejected.

The generator first validates ranking data, then localizes descriptions, then renders CSV and HTML from the same localized rows. Localization never changes stars, growth, creation dates, rankings or tracks.

GitHub Models was retired in 2026, so this repository does not depend on its retired inference API. The weekly workflow uses the open-source Argos Translate engine locally inside the GitHub Actions runner. The English→Chinese model is downloaded during the run and inference happens on the runner itself; no translation API key, GitHub Copilot license or long-lived credential is required.

`config.json` controls the provider and translation batch size. The current provider is `argos-offline`.

- `data/description-translations.json` — generated cache keyed by repository and exact source description. Unchanged source text reuses the validated Chinese translation.
- `data/description-overrides.json` — optional human-reviewed overrides mapping `owner/repo` to a Chinese sentence. Overrides take precedence.
- `data/latest-run.json` — includes localization statistics after a successful run.

If an offline translation is unusable, the generator never falls back to publishing the English original. It uses a truthful Chinese category-level fallback telling readers to consult the official repository description. This guarantees that the `主要用途` column remains Chinese without inventing project-specific capabilities.

Local tests:

    python3 -m unittest discover -s tests -v

Normal local generation:

    pip install argostranslate==1.11.0
    python3 scripts/generate_weekly.py

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
