import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import weekly_i18n as i18n


class LocalizationTests(unittest.TestCase):
    def test_language_gate(self):
        self.assertFalse(i18n.valid_chinese('A privacy-first app that strips AI watermarks from content you own.'))
        self.assertFalse(i18n.valid_chinese('OpenWiki is a CLI that writes documentation.'))
        self.assertTrue(i18n.valid_chinese('用于自动生成并维护代码仓库的智能体文档，帮助开发者理解项目。'))
        self.assertTrue(i18n.valid_chinese('通过 CLI 自动整理代码仓库文档，方便开发团队维护。'))
        self.assertFalse(i18n.valid_chinese(''))

    def test_extract_json_with_markdown_fence(self):
        parsed = i18n._extract_json_object('```json\n{"items":[{"id":"0","use":"用于维护项目文档。"}]}\n```')
        self.assertEqual(parsed['items'][0]['id'], '0')

    def test_translate_cache_and_source_invalidation(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []

            def translate(items):
                calls.append(items)
                return {str(i): '用于自动生成并维护代码仓库文档，帮助开发者协作。' for i, _ in enumerate(items)}

            rows = [{'repo': 'a/b', 'track': '开发工具', 'what': '开发工具', 'use': 'Writes documentation.'}]
            out, stats = i18n.localize_rows(rows, {}, root=temp, translator=translate)
            self.assertEqual(stats['translated'], 1)
            self.assertEqual(rows[0]['use'], 'Writes documentation.')
            out, stats = i18n.localize_rows(rows, {}, root=temp, translator=translate)
            self.assertEqual(stats['cached'], 1)
            self.assertEqual(len(calls), 1)
            rows[0]['use'] = 'Writes and maintains documentation.'
            i18n.localize_rows(rows, {}, root=temp, translator=translate)
            self.assertEqual(len(calls), 2)

    def test_reject_english_without_corrupting_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            rows = [{'repo': 'a/b', 'track': '开发工具', 'what': '开发工具', 'use': 'A useful tool for software developers.'}]
            with self.assertRaises(i18n.LocalizationError):
                i18n.localize_rows(rows, {}, root=temp, translator=lambda items: {'0': 'A useful tool for software developers.'})
            self.assertFalse((Path(temp) / 'data/description-translations.json').exists())

    def test_manual_override(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'data'
            path.mkdir()
            (path / 'description-overrides.json').write_text(
                json.dumps({'a/b': '用于清理自有内容中的水印，保护用户隐私。'}, ensure_ascii=False)
            )
            rows = [{'repo': 'a/b', 'track': '开发工具', 'what': '开发工具', 'use': 'Watermark remover.'}]
            out, stats = i18n.localize_rows(rows, {}, root=temp, translator=lambda _: self.fail('unexpected API'))
            self.assertEqual(stats['manual'], 1)
            self.assertIn('水印', out[0]['use'])

    def test_missing_copilot_cli_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            rows = [{'repo': 'a/b', 'track': '开发工具', 'what': '开发工具', 'use': 'A tool to build documentation.'}]
            with patch('weekly_i18n.shutil.which', return_value=None):
                with self.assertRaises(i18n.LocalizationError):
                    i18n.localize_rows(rows, {}, root=temp)

    def test_copilot_mapping_validation(self):
        items = [{'id': '0'}, {'id': '1'}]
        parsed = {'items': [
            {'id': '0', 'use': '用于生成项目文档，帮助开发者维护代码库。'},
            {'id': '1', 'use': '用于清理自有内容中的水印，保护用户隐私。'},
        ]}
        mapped = i18n._validate_mapping(parsed, items)
        self.assertIn('0', mapped)
        self.assertIn('1', mapped)


if __name__ == '__main__':
    unittest.main()
