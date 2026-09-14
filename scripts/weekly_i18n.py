"""Chinese localization for GitHub weekly descriptions. No ranking logic here."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

HAN = re.compile(r'[\u3400-\u9fff]')
WORDS = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
TECH = {
    'ai', 'agent', 'agents', 'api', 'cli', 'sdk', 'mcp', 'llm', 'rag', 'ui', 'ux',
    'gpu', 'cpu', 'web', 'app', 'apps', 'github', 'git', 'python', 'javascript',
    'typescript', 'java', 'rust', 'swift', 'go', 'docker', 'kubernetes', 'react',
    'vue', 'node', 'sql', 'json', 'html', 'css', 'openai', 'claude', 'codex',
    'deepseek', 'gemini', 'copilot', 'linux', 'macos', 'ios', 'windows', 'openclaw',
    'openwiki', 'harness', 'mimo', 'code', 'skills', 'skill', 'workflow', 'workflows',
    'devops', 'ocr', 'tts', 'stt', 'http', 'https', 'ssh', 'gitops', 'llama', 'qwen',
    'kimi', 'hermes', 'markdown'
}
CACHE_VERSION = 2
DEFAULT_PROVIDER = 'github-copilot-cli'


class LocalizationError(RuntimeError):
    pass


def clean(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def valid_chinese(text):
    """Require Chinese prose; allow English names/acronyms, not English sentences."""
    text = clean(text)
    han = len(HAN.findall(text))
    if han < 2:
        return False
    words = WORDS.findall(text)
    ordinary = [w for w in words if w.lower() not in TECH]
    if len(ordinary) > max(3, han // 4):
        return False
    if re.search(r'[.!?]\s+[A-Z][a-z]+\s+[a-z]+', text):
        return False
    return True


def assert_chinese_uses(rows):
    bad = [r.get('repo', '<unknown>') for r in rows if not valid_chinese(r.get('use'))]
    if bad:
        raise LocalizationError('主要用途未通过中文校验：' + ', '.join(bad[:12]))


def _extract_json_object(text: str) -> dict:
    """Parse a JSON object even if Copilot wraps it in a short Markdown fence/preamble."""
    raw = str(text or '').strip()
    if not raw:
        raise LocalizationError('Copilot CLI 未返回内容')
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{', raw):
        try:
            value, _end = decoder.raw_decode(raw[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise LocalizationError('Copilot CLI 未返回可解析的 JSON 对象')


def _validate_mapping(parsed: dict, items: list[dict]) -> dict[str, str]:
    values = parsed.get('items')
    if not isinstance(values, list):
        raise LocalizationError('翻译结果未返回 items 数组')
    expected = {str(x['id']) for x in items}
    mapped: dict[str, str] = {}
    for item in values:
        if not isinstance(item, dict) or 'id' not in item or 'use' not in item:
            raise LocalizationError('翻译结果项目格式错误')
        key = str(item['id'])
        if key in mapped or key not in expected:
            raise LocalizationError('翻译结果包含重复或未知 id')
        mapped[key] = clean(item['use'])
    if set(mapped) != expected:
        raise LocalizationError('翻译结果遗漏了项目')
    for value in mapped.values():
        if not valid_chinese(value):
            raise LocalizationError('翻译结果仍包含英文句子或缺少中文')
    return mapped


def request_copilot(items, model='', retries=3):
    """Translate one bounded batch through GitHub Copilot CLI.

    In GitHub Actions, Copilot CLI authenticates with the built-in GITHUB_TOKEN.
    The workflow grants `copilot-requests: write`; no long-lived API key is stored.
    """
    if shutil.which('copilot') is None:
        raise LocalizationError('未找到 GitHub Copilot CLI，无法生成中文主要用途')

    instruction = (
        '你是开源软件技术编辑。请把输入中每个 GitHub 项目的 description 改写为准确、自然的简体中文“主要用途”。'
        '每条只写一句，约 20–65 个汉字；只依据 repo、track、what 和 description，不编造未提供的功能。'
        '保留必要的产品名以及 API、CLI、Agent、SDK 等技术词，但不要保留完整英文句子，也不要照搬营销口号。'
        '不同项目不能混淆。只输出一个 JSON 对象，不要 Markdown，不要解释。严格格式：'
        '{"items":[{"id":"0","use":"中文句子"}]}。每个输入 id 必须恰好出现一次。\n\n'
        '输入：' + json.dumps({'items': items}, ensure_ascii=False)
    )

    last = None
    for attempt in range(retries):
        cmd = ['copilot', '-p', instruction, '-s', '--no-ask-user']
        if clean(model) and clean(model).lower() not in {'auto', 'default'}:
            cmd.extend(['--model', clean(model)])
        try:
            proc = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                timeout=180,
                check=False,
            )
            if proc.returncode != 0:
                detail = clean(proc.stderr or proc.stdout)
                if len(detail) > 500:
                    detail = detail[-500:]
                raise LocalizationError(
                    'Copilot CLI 调用失败'
                    + (f'：{detail}' if detail else f'（exit {proc.returncode}）')
                )
            parsed = _extract_json_object(proc.stdout)
            return _validate_mapping(parsed, items)
        except subprocess.TimeoutExpired as exc:
            last = 'timeout'
            if attempt + 1 >= retries:
                raise LocalizationError('Copilot CLI 翻译超时') from exc
        except LocalizationError as exc:
            last = str(exc)
            if attempt + 1 >= retries:
                raise
        time.sleep(min(20, 2 ** attempt * 3))
    raise LocalizationError('Copilot CLI 翻译重试后仍失败：' + str(last))


def localize_rows(rows, config, *, root=None, translator=None):
    """Return localized copies and stats. Cache only validated, source-matched text."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    cache_path = root / 'data' / 'description-translations.json'
    override_path = root / 'data' / 'description-overrides.json'
    cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    overrides = json.loads(override_path.read_text(encoding='utf-8')) if override_path.exists() else {}
    if not isinstance(cache, dict) or not isinstance(overrides, dict):
        raise LocalizationError('翻译缓存或人工覆盖文件格式错误')

    output = [dict(r) for r in rows]
    pending = []
    stats = {'translated': 0, 'cached': 0, 'manual': 0, 'already_zh': 0, 'missing_source': 0}
    for row in output:
        repo = row['repo']
        source = clean(row.get('use_source') or row.get('use'))
        row['use_source'] = source
        manual = overrides.get(repo)
        if isinstance(manual, str) and valid_chinese(manual):
            row['use'] = clean(manual)
            stats['manual'] += 1
        elif valid_chinese(source):
            row['use'] = source
            stats['already_zh'] += 1
        elif not source or source == '详见 GitHub 官方仓库说明':
            row['use'] = '项目暂未提供具体用途说明，请查阅官方仓库文档。'
            stats['missing_source'] += 1
        elif (
            isinstance(cache.get(repo), dict)
            and cache[repo].get('source') == source
            and valid_chinese(cache[repo].get('use_zh'))
        ):
            row['use'] = cache[repo]['use_zh']
            stats['cached'] += 1
        else:
            pending.append(row)

    provider = str(config.get('translation_provider', DEFAULT_PROVIDER)).strip().lower()
    if pending and translator is None and provider not in {'github-copilot-cli', 'copilot-cli'}:
        raise LocalizationError('不支持的翻译提供方：' + provider)

    batch_size = max(1, min(16, int(config.get('translation_batch_size', 8))))
    model = str(config.get('translation_model', '') or '').strip()
    if pending:
        for start in range(0, len(pending), batch_size):
            batch = pending[start:start + batch_size]
            items = [
                {
                    'id': str(i),
                    'repo': r['repo'],
                    'track': r['track'],
                    'what': r['what'],
                    'description': r['use_source'],
                }
                for i, r in enumerate(batch)
            ]
            translated = translator(items) if translator is not None else request_copilot(items, model)
            for i, row in enumerate(batch):
                value = clean(translated[str(i)])
                if not valid_chinese(value):
                    raise LocalizationError('翻译结果不符合中文要求：' + row['repo'])
                row['use'] = value
                cache[row['repo']] = {
                    'source': row['use_source'],
                    'use_zh': value,
                    'provider': provider,
                    'model': model or 'auto',
                    'cache_version': CACHE_VERSION,
                }
                stats['translated'] += 1

    assert_chinese_uses(output)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return output, stats
