"""C8C quality/preview checks protect approved C8B proposals and local files."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentforge import product_builder as builder
from agentforge import product_quality as quality
from agentforge import product_revision as revision

HTML = ('<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Excel cho shop</title><style>@media(max-width:600px){body{margin:0}}'
        '</style></head><body><h1>Excel cho shop</h1><a href="#cta">Xem giá</a>'
        '<section id="cta"><h2>Giá mẫu</h2><p>Tham khảo</p></section></body></html>')
NEW = HTML.replace('Tham khảo', 'Minh họa')
BRIEF = 'Change the placeholder text but preserve accessibility and layout.'


class TestProductQuality(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [
            patch.object(builder, 'ROOT', self.root),
            patch.object(builder, 'WORKSPACE', self.root / 'workspace'),
            patch.object(builder, 'PRODUCTS', self.root / 'workspace' / 'products'),
            patch.object(builder, 'PROPOSALS', self.root / 'data' / 'company' / 'product_builder' / 'proposals'),
        ]
        for p in self.patches:
            p.start()
        self.source = builder.PRODUCTS / 'shop-landing' / 'index.html'
        self.source.parent.mkdir(parents=True)
        self.source.write_text(HTML, encoding='utf-8')

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def prop(self, content=NEW):
        return revision.propose('shop-landing', BRIEF,
                                model_client=lambda prompt, *, worker_id: content)

    def test_quality_passes_well_formed_static_html(self):
        result = quality.analyze(HTML)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['warnings'], 0)
        self.assertEqual(result['failures'], 0)
        self.assertFalse(result['browser_rendered'])
        self.assertFalse(result['security_verified'])

    def test_check_project_is_read_only(self):
        before = self.source.read_bytes()
        result = quality.check_project('shop-landing')
        self.assertEqual(result['target'], 'project')
        self.assertEqual(result['sha256'], revision._hash(before))
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(self.source.read_bytes(), before)

    def test_check_revision_is_read_only(self):
        doc = self.prop()
        before = self.source.read_bytes()
        result = quality.check_revision(doc['revision_id'])
        self.assertEqual(result['target'], 'revision')
        self.assertEqual(result['sha256'], doc['sha256'])
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse((self.root / 'data' / 'company' / 'product_builder' / 'previews').exists())

    def test_preview_writes_only_ignored_data_copy(self):
        doc = self.prop()
        result = quality.preview_revision(doc['revision_id'])
        self.assertEqual(result['status'], 'PREVIEW_FILE_CREATED_NOT_EXECUTED')
        self.assertEqual(Path(result['preview_path']).read_text(encoding='utf-8'), NEW)
        self.assertEqual(self.source.read_text(encoding='utf-8'), HTML)
        self.assertFalse(result['browser_opened'])
        self.assertFalse(result['execution_authorized'])
        self.assertIn('/previews/', result['preview_path'].replace('\\', '/'))

    def test_preview_is_idempotent_if_exact_bytes_match(self):
        doc = self.prop()
        first = quality.preview_revision(doc['revision_id'])
        second = quality.preview_revision(doc['revision_id'])
        self.assertEqual(second['status'], 'EXISTING_VERIFIED_PREVIEW')
        self.assertEqual(first['preview_path'], second['preview_path'])

    def test_tampered_preview_never_overwritten(self):
        doc = self.prop()
        result = quality.preview_revision(doc['revision_id'])
        path = Path(result['preview_path'])
        path.write_text('local edits', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            quality.preview_revision(doc['revision_id'])
        self.assertEqual(path.read_text(encoding='utf-8'), 'local edits')

    def test_stale_revision_blocks_check_and_preview(self):
        doc = self.prop()
        self.source.write_text(HTML.replace('Tham khảo', 'Thay đổi'), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'STALE_REVISION'):
            quality.check_revision(doc['revision_id'])
        with self.assertRaisesRegex(RuntimeError, 'STALE_REVISION'):
            quality.preview_revision(doc['revision_id'])
        self.assertFalse((self.root / 'data' / 'company' / 'product_builder' / 'previews').exists())

    def test_applied_revision_blocks_preview(self):
        doc = self.prop()
        revision.apply(doc['revision_id'], confirm_write=True, sha256=doc['sha256'])
        with self.assertRaisesRegex(RuntimeError, 'already applied'):
            quality.check_revision(doc['revision_id'])
        with self.assertRaisesRegex(RuntimeError, 'already applied'):
            quality.preview_revision(doc['revision_id'])
        self.assertEqual(quality.check_project('shop-landing')['status'], 'PASS')

    def test_tampered_proposal_blocks_preview(self):
        import json
        doc = self.prop()
        p, _ = revision._paths(doc['revision_id'])
        data = json.loads(p.read_text(encoding='utf-8'))
        data['files'][0]['content'] = NEW.replace('Minh họa', 'Mạo danh')
        p.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(ValueError):
            quality.preview_revision(doc['revision_id'])
        self.assertFalse((self.root / 'data' / 'company' / 'product_builder' / 'previews').exists())

    def test_no_shell_network_or_model_in_preview(self):
        doc = self.prop()
        with (patch('subprocess.run') as shell,
              patch('urllib.request.urlopen') as network,
              patch('agentforge.model.generate') as model):
            quality.preview_revision(doc['revision_id'])
            shell.assert_not_called()
            network.assert_not_called()
            model.assert_not_called()

    def test_invalid_project_slug_rejected(self):
        for slug in ('../outside', 'C:secret', 'CON', 'x'):
            with self.subTest(slug=slug):
                with self.assertRaises(ValueError):
                    quality.check_project(slug)

    def test_missing_project_rejected(self):
        with self.assertRaises(FileNotFoundError):
            quality.check_project('missing-shop')

    def test_invalid_revision_id_rejected(self):
        with self.assertRaises(ValueError):
            quality.preview_revision('../outside')

    def test_malformed_html_report_is_fail_not_execution(self):
        self.source.write_text('<html><body><h1>Truncated', encoding='utf-8')
        result = quality.check_project('shop-landing')
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('document_complete', [x['rule'] for x in result['findings']])

    def test_missing_viewport_is_warning(self):
        result = quality.analyze(HTML.replace('width=device-width', 'minimum-scale=1'))
        self.assertEqual(result['status'], 'WARN')
        self.assertIn('viewport', [x['rule'] for x in result['findings']])

    def test_missing_lang_is_warning(self):
        result = quality.analyze(HTML.replace('lang="vi"', ''))
        self.assertIn('html_lang', [x['rule'] for x in result['findings']])

    def test_missing_charset_is_warning(self):
        result = quality.analyze(HTML.replace('<meta charset="utf-8">', ''))
        self.assertIn('charset', [x['rule'] for x in result['findings']])

    def test_missing_title_is_warning(self):
        result = quality.analyze(HTML.replace('Excel cho shop</title>', '</title>'))
        self.assertIn('title', [x['rule'] for x in result['findings']])

    def test_missing_doctype_is_warning(self):
        result = quality.analyze(HTML.replace('<!doctype html>', ''))
        self.assertIn('doctype', [x['rule'] for x in result['findings']])

    def test_two_h1_is_warning(self):
        result = quality.analyze(HTML.replace('<h1>Excel cho shop</h1>', '<h1>A</h1><h1>B</h1>'))
        self.assertIn('h1', [x['rule'] for x in result['findings']])

    def test_heading_skip_warning(self):
        result = quality.analyze(HTML.replace('<h2>Giá mẫu</h2>', '<h4>Giá mẫu</h4>'))
        self.assertIn('heading_order', [x['rule'] for x in result['findings']])

    def test_duplicate_ids_warning(self):
        result = quality.analyze(HTML.replace('<section id="cta">', '<section id="cta"><p id="cta">'))
        self.assertIn('duplicate_ids', [x['rule'] for x in result['findings']])

    def test_broken_fragment_warning(self):
        result = quality.analyze(HTML.replace('href="#cta"', 'href="#missing"'))
        self.assertIn('broken_fragments', [x['rule'] for x in result['findings']])

    def test_placeholder_link_warning(self):
        result = quality.analyze(HTML.replace('href="#cta"', 'href="#"'))
        self.assertIn('placeholder_links', [x['rule'] for x in result['findings']])

    def test_missing_alt_warning(self):
        result = quality.analyze(HTML.replace('<h1>Excel', '<img src="demo.png"><h1>Excel'))
        self.assertIn('image_alt', [x['rule'] for x in result['findings']])

    def test_responsive_is_only_heuristic(self):
        result = quality.analyze(HTML.replace('@media(max-width:600px)', '.fake'))
        self.assertIn('responsive_hint', [x['rule'] for x in result['findings']])
        self.assertFalse(result['browser_rendered'])

    def test_inline_event_handler_is_fail(self):
        result = quality.analyze(HTML.replace('<h1>Excel', '<h1 onclick="alert(1)">Excel'))
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('inline_events', [x['rule'] for x in result['findings']])

    def test_remote_url_is_fail(self):
        result = quality.analyze(HTML.replace('href="#cta"', 'href="https://evil.invalid"'))
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('unsafe_uris', [x['rule'] for x in result['findings']])

    def test_javascript_uri_is_fail(self):
        result = quality.analyze(HTML.replace('href="#cta"', 'href="javascript:alert(1)"'))
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('unsafe_uris', [x['rule'] for x in result['findings']])

    def test_network_js_is_fail(self):
        result = quality.analyze(HTML.replace('</body>', '<script>fetch("/api/x")</script></body>'))
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('unsafe_content', [x['rule'] for x in result['findings']])

    def test_preview_rejects_event_attributes_even_if_c8b_allows_them(self):
        malicious = NEW.replace('<h1>Excel', '<h1 onclick="alert(1)">Excel')
        doc = self.prop(content=malicious)
        self.assertEqual(quality.check_revision(doc['revision_id'])['status'], 'FAIL')
        with self.assertRaisesRegex(ValueError, 'FAIL issues'):
            quality.preview_revision(doc['revision_id'])
        self.assertFalse((self.root / 'data' / 'company' / 'product_builder' / 'previews').exists())

    def test_preview_directory_symlink_rejected(self):
        doc = self.prop()
        root = self.root / 'data' / 'company' / 'product_builder' / 'previews'
        root.parent.mkdir(parents=True, exist_ok=True)
        outside = self.root / 'outside'
        outside.mkdir()
        try:
            root.symlink_to(outside, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest('Symlinks unavailable')
        with self.assertRaises(PermissionError):
            quality.preview_revision(doc['revision_id'])
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
