#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import time
from datetime import date

from weekly_common import (
    ARCHIVE_DIR,
    CREATED_CUTOFF,
    DATA_DIR,
    MIN_GROWTH,
    ROOT,
    RUN_DATE,
    TODAY,
    WINDOW_START,
    classify,
)
from weekly_render import generate_csv, generate_html
from weekly_sources import (
    closest_point,
    discover_candidates,
    github_repo,
    parse_oss_history,
    snapshot_current,
)


def main() -> int:
    print(f"Run date: {RUN_DATE}")
    print(f"Window: {WINDOW_START}..{TODAY}; min growth: {MIN_GROWTH}; created >= {CREATED_CUTOFF}")

    candidate_set, trend_hints = discover_candidates()
    print(f"Candidates discovered: {len(candidate_set)}")

    details: dict[str, dict] = {}
    for index, name in enumerate(sorted(candidate_set), 1):
        meta = github_repo(name)
        if not meta or meta.get("private") or meta.get("fork") or meta.get("archived"):
            continue

        created_raw = str(meta.get("created_at") or "")[:10]
        try:
            created = date.fromisoformat(created_raw)
        except ValueError:
            continue

        current_stars = int(meta.get("stargazers_count") or 0)
        if created < CREATED_CUTOFF or current_stars < MIN_GROWTH:
            continue

        details[name] = meta
        if index % 50 == 0:
            print(f"GitHub metadata: {index}/{len(candidate_set)}")
        time.sleep(0.04)

    # Persist a weekly GitHub-current-star snapshot for auditing and future use.
    snapshot_current(details)

    results: list[dict] = []
    excluded_unverified = 0

    for index, (name, meta) in enumerate(sorted(details.items()), 1):
        created = date.fromisoformat(str(meta["created_at"])[:10])
        current_stars = int(meta.get("stargazers_count") or 0)

        # Exact special case: the repository did not exist at the window start.
        if created > WINDOW_START:
            growth = current_stars
            source = "GitHub baseline=0 (repository did not exist at window start)"
            source_date = WINDOW_START.isoformat()
        else:
            # The OSSInsight 3-month trend count is only a discovery hint. If the
            # hint is below the threshold, net growth cannot be above it.
            hint = trend_hints.get(name)
            if hint is not None and hint < MIN_GROWTH:
                continue

            try:
                points = parse_oss_history(name)
            except Exception as exc:
                print(f"WARN: history unavailable for {name}: {exc}")
                excluded_unverified += 1
                continue

            baseline = closest_point(points, WINDOW_START)
            latest = points[-1] if points else None
            if not baseline or not latest or latest[0] <= baseline[0]:
                excluded_unverified += 1
                continue

            # Reject stale history rather than mixing a stale OSSInsight value with
            # the current GitHub total. No interpolation or extrapolation is used.
            if (TODAY - latest[0]).days > 7:
                print(f"WARN: stale OSSInsight history for {name}: latest={latest[0]}")
                excluded_unverified += 1
                continue

            growth = latest[1] - baseline[1]
            source = "OSSInsight stargazers history"
            source_date = baseline[0].isoformat()

        if growth < MIN_GROWTH:
            continue

        topics = meta.get("topics") if isinstance(meta.get("topics"), list) else []
        track, what, use = classify(name, str(meta.get("description") or ""), topics)
        results.append({
            "repo": name,
            "url": str(meta.get("html_url") or f"https://github.com/{name}"),
            "track": track,
            "growth": int(growth),
            "stars": current_stars,
            "created": created.isoformat(),
            "what": what,
            "use": use,
            "source": source,
            "source_date": source_date,
        })

        if index % 25 == 0:
            print(f"Growth validation: {index}/{len(details)}")

    # Required default order: AI Agent first, then all other tracks; each by growth desc.
    ai_rows = sorted(
        (r for r in results if r["track"] == "AI Agent"),
        key=lambda r: r["growth"],
        reverse=True,
    )
    other_rows = sorted(
        (r for r in results if r["track"] != "AI Agent"),
        key=lambda r: r["growth"],
        reverse=True,
    )
    final_rows = ai_rows + other_rows
    for rank, row in enumerate(final_rows, 1):
        row["rank"] = rank

    csv_text = generate_csv(final_rows)
    html_text = generate_html(final_rows, excluded_unverified)

    dated_csv = ROOT / f"{RUN_DATE}-github-star-growth-weekly.csv"
    dated_html = ROOT / f"{RUN_DATE}-github-star-growth-weekly.html"
    latest_csv = ROOT / "latest.csv"
    index_html = ROOT / "index.html"
    archive_csv = ARCHIVE_DIR / f"{RUN_DATE}.csv"
    archive_html = ARCHIVE_DIR / f"{RUN_DATE}.html"

    for path in (dated_csv, latest_csv, archive_csv):
        path.write_text(csv_text, encoding="utf-8")
    for path in (dated_html, index_html, archive_html):
        path.write_text(html_text, encoding="utf-8")

    manifest = {
        "run_date": RUN_DATE,
        "window_start": WINDOW_START.isoformat(),
        "min_growth": MIN_GROWTH,
        "created_cutoff": CREATED_CUTOFF.isoformat(),
        "total": len(final_rows),
        "ai_agent_count": len(ai_rows),
        "excluded_unverified": excluded_unverified,
        "generator": "scripts/generate_weekly.py",
        "policy": "no interpolation / no age-based estimation",
    }
    (DATA_DIR / "latest-run.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
