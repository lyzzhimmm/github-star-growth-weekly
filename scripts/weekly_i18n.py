"""Simplified-Chinese localization for weekly project descriptions.

The ranking/data pipeline is intentionally independent from localization. English
repository descriptions are translated locally with Argos Translate in GitHub
Actions, so publication does not depend on a hosted LLM/API credential.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HAN = re.compile(r"[\u3400-\u9fff]")
WORDS = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
TECH = {
    "ai", "agent", "agents", "api", "cli", "sdk", "mcp", "llm", "rag", "ui", "ux",
    "gpu", "cpu", "web", "app", "apps", "github", "git", "python", "javascript",
    "typescript", "java", "rust", "swift", "go", "docker", "kubernetes", "react",
    "vue", "node", "sql", "json", "html", "css", "openai", "claude", "codex",
    "deepseek", "gemini", "copilot", "linux", "macos", "ios", "windows", "openclaw",
    "openwiki", "harness", "mimo", "code", "skills", "skill", "workflow", "workflows",
    "devops", "ocr", "tts", "stt", "http", "https", "ssh", "gitops", "llama", "qwen",
    "kimi", "hermes", "markdown",
}
CACHE_VERSION = 3
DEFAULT_PROVIDER = "argos-offline"
_ARGOS_READY = False


class LocalizationError(RuntimeError):
    pass


def clean(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_chinese(text: str) -> str:
    """Light punctuation cleanup only; never invent project capabilities."""
    text = clean(text)
    text = text.replace(",", "，").replace(";", "；")
    text = re.sub(r"(?<!\d)\.(?!\d)", "。", text)
    text = re.sub(r"\s*([，。！？；：])\s*", r"\1", text)
    if text and text[-1] not in "。！？":
        text += "。"
    return text


def valid_chinese(text) -> bool:
    """Require Chinese prose; allow names/acronyms, reject English-only sentences."""
    text = clean(text)
    han = len(HAN.findall(text))
    if han < 2:
        return False
    words = WORDS.findall(text)
    ordinary = [word for word in words if word.lower() not in TECH]
    if len(ordinary) > max(3, han // 4):
        return False
    if re.search(r"[.!?]\s+[A-Z][a-z]+\s+[a-z]+", text):
        return False
    return True


def assert_chinese_uses(rows) -> None:
    bad = [row.get("repo", "<unknown>") for row in rows if not valid_chinese(row.get("use"))]
    if bad:
        raise LocalizationError("主要用途未通过中文校验：" + ", ".join(bad[:12]))


def _fallback_use(row: dict) -> str:
    """Truthful Chinese fallback used only when machine translation is unusable."""
    what = clean(row.get("what")) or "开源项目"
    return normalize_chinese(f"{what}，具体主要用途请以项目官方仓库说明为准")


def _ensure_argos_model() -> None:
    global _ARGOS_READY
    if _ARGOS_READY:
        return
    try:
        import argostranslate.package as package
        import argostranslate.translate as translate
    except ImportError as exc:
        raise LocalizationError("未安装 Argos Translate，无法生成中文主要用途") from exc

    def has_pair() -> bool:
        installed = translate.get_installed_languages()
        source = next((lang for lang in installed if lang.code == "en"), None)
        target = next((lang for lang in installed if lang.code == "zh"), None)
        if not source or not target:
            return False
        try:
            source.get_translation(target)
            return True
        except Exception:
            return False

    if not has_pair():
        try:
            package.update_package_index()
            candidates = [
                item for item in package.get_available_packages()
                if item.from_code == "en" and item.to_code == "zh"
            ]
            if not candidates:
                raise LocalizationError("Argos Translate 没有可用的 en→zh 语言包")
            language_package = candidates[0]
            package.install_from_path(language_package.download())
        except LocalizationError:
            raise
        except Exception as exc:
            raise LocalizationError("Argos Translate en→zh 语言包安装失败") from exc
        if not has_pair():
            raise LocalizationError("Argos Translate en→zh 语言包安装后仍不可用")

    _ARGOS_READY = True


def request_argos(items: list[dict]) -> dict[str, str]:
    """Translate a bounded set locally; no token or hosted inference API is used."""
    _ensure_argos_model()
    try:
        import argostranslate.translate as translate
    except ImportError as exc:
        raise LocalizationError("未安装 Argos Translate") from exc

    mapped: dict[str, str] = {}
    for item in items:
        key = str(item["id"])
        source = clean(item.get("description"))
        if not source:
            mapped[key] = _fallback_use(item)
            continue
        try:
            value = normalize_chinese(translate.translate(source, "en", "zh"))
        except Exception:
            value = ""
        if not valid_chinese(value):
            value = _fallback_use(item)
        if not valid_chinese(value):
            raise LocalizationError("离线翻译结果未通过中文校验：" + clean(item.get("repo")))
        mapped[key] = value
    return mapped


def localize_rows(rows, config, *, root=None, translator=None):
    """Return localized copies and stats. Cache only validated, source-matched text."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    cache_path = root / "data" / "description-translations.json"
    override_path = root / "data" / "description-overrides.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    overrides = json.loads(override_path.read_text(encoding="utf-8")) if override_path.exists() else {}
    if not isinstance(cache, dict) or not isinstance(overrides, dict):
        raise LocalizationError("翻译缓存或人工覆盖文件格式错误")

    output = [dict(row) for row in rows]
    pending: list[dict] = []
    stats = {
        "translated": 0,
        "cached": 0,
        "manual": 0,
        "already_zh": 0,
        "missing_source": 0,
        "fallback": 0,
    }

    for row in output:
        repo = row["repo"]
        source = clean(row.get("use_source") or row.get("use"))
        row["use_source"] = source
        manual = overrides.get(repo)
        if isinstance(manual, str) and valid_chinese(manual):
            row["use"] = normalize_chinese(manual)
            stats["manual"] += 1
        elif valid_chinese(source):
            row["use"] = normalize_chinese(source)
            stats["already_zh"] += 1
        elif not source or source == "详见 GitHub 官方仓库说明":
            row["use"] = "项目暂未提供具体用途说明，请查阅官方仓库文档。"
            stats["missing_source"] += 1
        elif (
            isinstance(cache.get(repo), dict)
            and cache[repo].get("source") == source
            and valid_chinese(cache[repo].get("use_zh"))
        ):
            row["use"] = normalize_chinese(cache[repo]["use_zh"])
            stats["cached"] += 1
        else:
            pending.append(row)

    provider = str(config.get("translation_provider", DEFAULT_PROVIDER)).strip().lower()
    if pending and translator is None and provider not in {"argos-offline", "argos"}:
        raise LocalizationError("不支持的翻译提供方：" + provider)

    batch_size = max(1, min(32, int(config.get("translation_batch_size", 16))))
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        items = [
            {
                "id": str(index),
                "repo": row["repo"],
                "track": row["track"],
                "what": row["what"],
                "description": row["use_source"],
            }
            for index, row in enumerate(batch)
        ]
        translated = translator(items) if translator is not None else request_argos(items)
        for index, row in enumerate(batch):
            value = normalize_chinese(translated[str(index)])
            if not valid_chinese(value):
                value = _fallback_use(row)
                stats["fallback"] += 1
            if not valid_chinese(value):
                raise LocalizationError("翻译结果不符合中文要求：" + row["repo"])
            row["use"] = value
            cache[row["repo"]] = {
                "source": row["use_source"],
                "use_zh": value,
                "provider": provider,
                "cache_version": CACHE_VERSION,
            }
            stats["translated"] += 1

    assert_chinese_uses(output)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output, stats
