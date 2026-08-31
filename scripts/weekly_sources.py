#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
import time
import urllib.parse
from datetime import date, datetime, timedelta

from weekly_common import (
    ARCHIVE_DIR,
    CFG,
    HISTORY_TOLERANCE_DAYS,
    MIN_GROWTH,
    ROOT,
    RUN_DATE,
    SNAPSHOT_DIR,
    TODAY,
    WINDOW_START,
    http_json,
    int_value,
    normalize_repo_name,
    rows_from_oss,
)


def load_previous_repos() -> set[str]:
    repos: set[str] = set()
    paths = [ROOT / "latest.csv", *sorted(ARCHIVE_DIR.glob("*.csv"), reverse=True)[:8]]
    for path in paths:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    name = (row.get("项目") or "").strip()
                    if name.count("/") == 1:
                        repos.add(name)
        except Exception:
            pass
    return repos


def ossinsight_trending_candidates() -> tuple[set[str], dict[str, int]]:
    """Collect every repo returned by OSSInsight's 3-month top lists.

    We intentionally do not prefilter by OSSInsight's `stars` hint. The hint is
    useful for diagnostics, but candidate discovery should stay broad so a
    source-side undercount cannot silently remove a potentially valid repo.
    """
    repos: set[str] = set()
    hints: dict[str, int] = {}
    languages = CFG.get("ossinsight_languages") or ["All"]

    for language in languages:
        url = (
            "https://api.ossinsight.io/v1/trends/repos/"
            f"?period=past_3_months&language={urllib.parse.quote(str(language))}"
        )
        try:
            rows = rows_from_oss(http_json(url))
        except Exception as exc:
            print(f"WARN: OSSInsight trends failed for {language}: {exc}")
            continue

        for row in rows:
            name = normalize_repo_name(row)
            if not name:
                continue
            repos.add(name)
            recent = int_value(row, ("stars", "stars_inc", "star_count", "stargazers"))
            if recent is not None:
                hints[name] = max(hints.get(name, 0), recent)
        time.sleep(0.12)

    return repos, hints


def github_search_new_repos() -> set[str]:
    """Repos created after WINDOW_START have an exact zero baseline."""
    repos: set[str] = set()
    q = f"created:>={WINDOW_START.isoformat()} stars:>={MIN_GROWTH} fork:false archived:false"

    for page in range(1, 11):
        url = (
            "https://api.github.com/search/repositories?"
            + urllib.parse.urlencode({
                "q": q,
                "sort": "stars",
                "order": "desc",
                "per_page": 100,
                "page": page,
            })
        )
        try:
            data = http_json(url, github=True)
        except Exception as exc:
            print(f"WARN: GitHub new-repo search failed: {exc}")
            break

        items = data.get("items") or []
        for item in items:
            name = item.get("full_name")
            if isinstance(name, str) and name.count("/") == 1:
                repos.add(name)
        if len(items) < 100:
            break
        time.sleep(0.1)

    return repos


def github_repo(name: str) -> dict | None:
    owner, repo = name.split("/", 1)
    url = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"
    try:
        return http_json(url, github=True)
    except Exception as exc:
        print(f"WARN: GitHub metadata failed for {name}: {exc}")
        return None


def parse_oss_history(name: str) -> list[tuple[date, int]]:
    owner, repo = name.split("/", 1)
    start = WINDOW_START - timedelta(days=max(HISTORY_TOLERANCE_DAYS, 3) + 2)
    url = (
        f"https://api.ossinsight.io/v1/repos/{urllib.parse.quote(owner)}/"
        f"{urllib.parse.quote(repo)}/stargazers/history/"
        f"?per=day&from={start.isoformat()}&to={TODAY.isoformat()}"
    )
    rows = rows_from_oss(http_json(url))
    points: list[tuple[date, int]] = []

    for row in rows:
        raw_date = row.get("date") or row.get("day") or row.get("period")
        stars = int_value(row, ("stargazers", "stars", "count", "total"))
        if raw_date is None or stars is None:
            continue
        try:
            d = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00")).date()
        except ValueError:
            try:
                d = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                continue
        points.append((d, stars))

    points.sort(key=lambda x: x[0])
    return points


def closest_point(points: list[tuple[date, int]], target: date):
    candidates = [p for p in points if abs((p[0] - target).days) <= HISTORY_TOLERANCE_DAYS]
    if not candidates:
        return None
    return min(candidates, key=lambda p: (abs((p[0] - target).days), p[0]))


def snapshot_current(details: dict[str, dict]) -> None:
    payload = {
        "date": RUN_DATE,
        "generated_at": datetime.now().astimezone().isoformat(),
        "repositories": {
            name: {
                "stars": int(meta.get("stargazers_count") or 0),
                "created_at": meta.get("created_at"),
            }
            for name, meta in sorted(details.items())
        },
    }
    path = SNAPSHOT_DIR / f"{RUN_DATE}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def discover_candidates() -> tuple[set[str], dict[str, int]]:
    trend_repos, hints = ossinsight_trending_candidates()
    repos = set(trend_repos)
    repos.update(github_search_new_repos())
    repos.update(load_previous_repos())
    return repos, hints
