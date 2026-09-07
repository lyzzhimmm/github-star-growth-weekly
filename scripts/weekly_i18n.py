"""Chinese localization for GitHub weekly descriptions. No ranking logic here."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

HAN = re.compile(r'[\u3400-\u9fff]')
WORDS = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
TECH = {'ai', 'agent', 'agents', 'api', 'cli', 'sdk', 'mcp', 'llm', 'rag', 'ui', 'ux', 'gpu', 'cpu', 'web', 'app', 'apps', 'github', 'git', 'python', 'javascript', 'typescript', 'java', 'rust', 'swift', 'go', 'docker', 'kubernetes', 'react', 'vue', 'node', 'sql', 'json', 'html', 'css', 'openai', 'claude', 'codex', 'deepseek', 'gemini', 'copilot', 'linux', 'macos', 'ios', 'windows', 'openclaw', 'openwiki', 'harness', 'mimo', 'code', 'skills', 'skill', 'workflow', 'workflows', 'devops', 'rag', 'ocr', 'tts', 'stt', 'http', 'https', 'ssh', 'gitops', 'llama', 'qwen', 'kimi', 'hermes', 'typescript', 'markdown'}
CACHE_VERSION = 1
ENDPOINT = 'https://models.github.ai/inference/chat/completions'
DEFAULT_MODEL = 'openai/gpt-4.1-mini'

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


def request_model(items, token, model=DEFAULT_MODEL, retries=4):
    """Translate a bounded batch using GitHub Models; never log credentials."""
    system = ('你是开源软件技术编辑。将每条 GitHub 项目说明改写为准确、自然的简体中文主要用途，'
              '每条一句，约 20–65 个汉字。只依据提供的名称、原文和分类，不编造能力，不照搬宣传口号。'
              '保留必要的产品名、API、CLI 等技术名词，但不要留下完整英文句子。'
              '不要把不同项目的说明混淆。仅返回 JSON 对象，格式为 '
              '{"items":[{"id":"0","use":"中文句子"}]}，每个输入 id 恰好出现一次。')
    payload = {'model': model, 'temperature': 0.1, 'max_tokens': 4096,
               'response_format': {'type': 'json_object'},
               'messages': [{'role': 'system', 'content': system},
                            {'role': 'user', 'content': json.dumps({'items': items}, ensure_ascii=False)}]}
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(ENDPOINT, data=data, headers={
            'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
            'Accept': 'application/json', 'User-Agent': 'github-star-growth-weekly/2.1'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                result = json.load(response)
            content = result['choices'][0]['message']['content']
            parsed = json.loads(content)
            values = parsed.get('items')
            if not isinstance(values, list):
                raise LocalizationError('模型未返回 items 数组')
            expected = {str(x['id']) for x in items}
            mapped = {}
            for item in values:
                key = str(item['id'])
                if key in mapped or key not in expected:
                    raise LocalizationError('模型返回了重复或未知 id')
                mapped[key] = clean(item['use'])
            if set(mapped) != expected:
                raise LocalizationError('模型遗漏了项目')
            for value in mapped.values():
                if not valid_chinese(value):
                    raise LocalizationError('模型返回的描述仍包含英文句子或缺少中文')
            return mapped
        except urllib.error.HTTPError as exc:
            last = f'HTTP {exc.code}'
            if exc.code in (401, 403):
                raise LocalizationError('GitHub Models 权限不足，请检查 models: read') from exc
            if exc.code not in (408, 429, 500, 502, 503, 504):
                raise LocalizationError('翻译服务请求失败：' + last) from exc
            retry_after = exc.headers.get('Retry-After', '')
            delay = float(retry_after) if retry_after.isdigit() else min(60, 2 ** attempt * 3)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, LocalizationError) as exc:
            last = type(exc).__name__
            delay = min(30, 2 ** attempt * 2)
        if attempt + 1 < retries:
            time.sleep(delay)
    raise LocalizationError('翻译服务重试后仍失败：' + str(last))


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
        elif isinstance(cache.get(repo), dict) and cache[repo].get('source') == source and valid_chinese(cache[repo].get('use_zh')):
            row['use'] = cache[repo]['use_zh']
            stats['cached'] += 1
        else:
            pending.append(row)
    if pending:
        token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
        if translator is None and not token:
            raise LocalizationError('缺少 GitHub Models 凭据；不能将英文原文直接发布')
        batch_size = max(1, min(16, int(config.get('translation_batch_size', 8))))
        model = str(config.get('translation_model', DEFAULT_MODEL))
        for start in range(0, len(pending), batch_size):
            batch = pending[start:start + batch_size]
            items = [{'id': str(i), 'repo': r['repo'], 'track': r['track'], 'what': r['what'], 'description': r['use_source']} for i, r in enumerate(batch)]
            if translator is None:
                translated = request_model(items, token, model)
            else:
                translated = translator(items)
            for i, row in enumerate(batch):
                value = clean(translated[str(i)])
                if not valid_chinese(value):
                    raise LocalizationError('翻译结果不符合中文要求：' + row['repo'])
                row['use'] = value
                cache[row['repo']] = {'source': row['use_source'], 'use_zh': value, 'model': model}
                stats['translated'] += 1
    assert_chinese_uses(output)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return output, stats
