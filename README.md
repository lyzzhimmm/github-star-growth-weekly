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

The `主要用途` column is generated as natural Simplified Chinese, rather than copying GitHub's original English description. Official product names and necessary technical terms such as API, CLI and Agent may remain in English, but full English sentences must not be published.

The generator first validates the ranking, then localizes descriptions, then renders the CSV and HTML from the same localized rows. The localization step does not change stars, growth, creation dates, rankings or tracks.

GitHub Actions uses GitHub Models with its built-in `GITHUB_TOKEN` and `models: read` permission. No additional personal access token or OpenAI API key is required. GitHub Models access and rate limits still depend on the repository owner's account. The selected model and batch size are configured in `config.json`.

- `data/description-translations.json` — generated cache, keyed by repository and matched to the exact source description. Unchanged descriptions reuse their translations; changed source text is translated again.
- `data/description-overrides.json` — optional human-reviewed overrides, mapping `owner/repo` to a Chinese sentence. Overrides take precedence over generated translations.
- `data/latest-run.json` — includes localization statistics after a successful run.

If translation access fails, a response is invalid, or a description cannot pass the Chinese-language check after retries, generation fails before publishing. It must not silently copy the English source or replace a specific description with a fabricated generic claim. Existing published output remains unchanged if the Actions generation step fails. GitHub Models free usage may be rate-limited; repeat runs reuse the translation cache to reduce requests.

Local test command:

    python3 -m unittest discover -s tests -v

Normal local generation:

    python3 scripts/generate_weekly.py

The latter requires GitHub credentials and network access to the data sources and translation service when uncached English descriptions are present. Keep all tokens in environment variables or the authenticated GitHub CLI; never commit credentials.

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
