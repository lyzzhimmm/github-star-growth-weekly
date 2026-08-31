#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"

DEFAULT_CONFIG = {
    "min_growth": 3000,
    "window_days": 90,
    "created_within_months": 36,
    "history_tolerance_days": 3,
    "timezone": "Asia/Shanghai",
    "ossinsight_languages": [
        "All", "Python", "TypeScript", "JavaScript", "Go", "Rust", "Java",
        "C++", "C", "Swift", "Shell", "HTML", "CSS", "Dart", "Kotlin", "PHP"
    ],
}

TRACKS = [
    "AI Agent", "Coding Agent", "模型/推理", "前端框架", "数据库",
    "开发工具", "基础设施", "音视频", "多模态", "机器人",
]

USER_AGENT = "github-star-growth-weekly/2.0"


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            cfg.update(raw)
    return cfg


CFG = load_config()
MIN_GROWTH = int(CFG["min_growth"])
WINDOW_DAYS = int(CFG["window_days"])
CREATED_MONTHS = int(CFG["created_within_months"])
HISTORY_TOLERANCE_DAYS = int(CFG["history_tolerance_days"])
TZ = ZoneInfo(str(CFG.get("timezone", "Asia/Shanghai")))
TODAY = datetime.now(TZ).date()
RUN_DATE = TODAY.isoformat()
WINDOW_START = TODAY - timedelta(days=WINDOW_DAYS)


def subtract_months(d: date, months: int) -> date:
    year = d.year
    month = d.month - months
    while month <= 0:
        year -= 1
        month += 12
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(d.day, last_day))


CREATED_CUTOFF = subtract_months(TODAY, CREATED_MONTHS)
ARCHIVE_DIR = ROOT / "archive"
DATA_DIR = ROOT / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    try:
        return subprocess.check_output(
            ["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        print("ERROR: no GITHUB_TOKEN/GH_TOKEN and `gh auth token` is unavailable.", file=sys.stderr)
        sys.exit(2)


TOKEN = get_token()


def http_json(url: str, *, github: bool = False, timeout: int = 30, retries: int = 3):
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if github:
        headers.update({
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    last_error = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 404, 422):
                break
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed: {url}: {last_error}")


def rows_from_oss(data) -> list[dict]:
    if not isinstance(data, dict):
        return []
    payload = data.get("data")
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return [r for r in payload["rows"] if isinstance(r, dict)]
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(data.get("rows"), list):
        return [r for r in data["rows"] if isinstance(r, dict)]
    return []


def normalize_repo_name(row: dict) -> str | None:
    for key in ("repo_name", "repo", "name_with_owner", "nameWithOwner", "repository"):
        value = row.get(key)
        if isinstance(value, str) and value.count("/") == 1:
            return value.strip()
    owner = row.get("owner")
    repo = row.get("name") or row.get("repo")
    if isinstance(owner, str) and isinstance(repo, str):
        return f"{owner}/{repo}"
    return None


def int_value(row: dict, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            return int(float(str(value).replace(",", "")))
        except ValueError:
            continue
    return None


def classify(name: str, description: str, topics: list[str]) -> tuple[str, str, str]:
    combined = f"{name} {description} {' '.join(topics)}".lower()
    if any(k in combined for k in ("coding agent", "code-agent", "claude-code", "codex", "copilot", "coding-assistant", "vibe coding", "code assistant")):
        track, what = "Coding Agent", "开源 AI 编程 Agent / 编程辅助工具"
    elif any(k in combined for k in ("agent", "autonomous", "workflow", "swarm", "crew", "orchestrat", "assistant", "agentic", "mcp", "skills")):
        track, what = "AI Agent", "开源 AI Agent 与自动化工作流项目"
    elif any(k in combined for k in ("inference", "llm", "transformer", "fine-tuning", "quantization", "moe", "gguf", "reasoning", "model")):
        track, what = "模型/推理", "开源大模型、训练或推理项目"
    elif any(k in combined for k in ("multimodal", "vision", "ocr", "image", "diffusion", "3d", "vlm")):
        track, what = "多模态", "开源多模态、图像或视觉项目"
    elif any(k in combined for k in ("audio", "video", "voice", "tts", "stt", "speech", "music")):
        track, what = "音视频", "开源音视频、语音或多媒体工具"
    elif any(k in combined for k in ("database", "vector", "postgres", "redis", "sql", "storage", "rag")):
        track, what = "数据库", "开源数据库、检索或数据基础设施"
    elif any(k in combined for k in ("robot", "robotics", "drone", "ros", "embodied")):
        track, what = "机器人", "开源机器人、具身智能或硬件项目"
    elif any(k in combined for k in ("react", "vue", "frontend", "ui", "component", "tailwind", "webgl")):
        track, what = "前端框架", "开源前端框架、UI 或交互工具"
    elif any(k in combined for k in ("kubernetes", "docker", "cloud", "proxy", "network", "infra", "runtime")):
        track, what = "基础设施", "开源云原生、运行时或系统基础设施"
    else:
        track, what = "开发工具", "开源开发者工具与效率项目"

    use = re.sub(r"[\r\n\t]+", " ", description or "").strip() or "详见 GitHub 官方仓库说明"
    if len(use) > 96:
        use = use[:93] + "..."
    return track, what, use
