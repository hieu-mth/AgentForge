"""C8C: local static checks and opt-in preview copies for product revisions.

Checks are HTML/CSS heuristics, NOT an HTML validator, browser test, security
scanner, or proof of visual quality. No model, browser, shell or network calls.
"""

import argparse
import json
import re
from html.parser import HTMLParser

from agentforge import product_builder as builder
from agentforge import product_revision as revision
from agentforge import web_assets


class _Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = None
        self.viewport = False
        self.charset = False
        self.in_title = False
        self.title = []
        self.headings = []
        self.ids = []
        self.fragment_links = []
        self.image_missing_alt = 0
        self.events = []
        self.dangerous_uris = []
        self.local_assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.lang = attrs.get('lang')
        if tag == 'title':
            self.in_title = True
        if tag == 'meta':
            if (attrs.get('name') or '').lower() == 'viewport':
                self.viewport = 'width=device-width' in (attrs.get('content') or '').lower().replace(' ', '')
            if (attrs.get('charset') or '').lower() == 'utf-8':
                self.charset = True
        if tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
            self.headings.append(int(tag[1]))
        if attrs.get('id'):
            self.ids.append(attrs['id'])
        if tag == 'a' and (attrs.get('href') or '').startswith('#'):
            self.fragment_links.append(attrs['href'][1:])
        if tag == 'img' and 'alt' not in attrs:
            self.image_missing_alt += 1
        for key, value in attrs.items():
            if key.startswith('on') and len(key) > 2:
                self.events.append(f'{tag}[{key}]')
            if key in {'href', 'src', 'action', 'formaction', 'poster', 'xlink:href'} and isinstance(value, str):
                stripped = value.strip().lower()
                if re.match(r'(?:javascript|data|vbscript):', stripped) or stripped.startswith(('http://', 'https://', '//')):
                    self.dangerous_uris.append(f'{tag}[{key}]')
                elif key in {'src', 'href'} and stripped and not stripped.startswith('#') and tag in {'script', 'link', 'img'}:
                    self.local_assets.append(value)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)


def analyze(html):
    """Return useful issues. WARN is advisory; FAIL is obvious unsafe/broken input."""
    if not isinstance(html, str):
        raise ValueError('HTML must be text')
    findings = []

    def add(rule, severity, message):
        findings.append({'rule': rule, 'severity': severity, 'message': message})

    try:
        builder._standalone_html(html)
    except ValueError as exc:
        add('document_complete', 'FAIL', str(exc))
    if not re.match(r'(?is)^\s*<!doctype\s+html\s*>', html):
        add('doctype', 'WARN', 'Add <!doctype html> for standards-mode rendering')
    if builder.SUSPICIOUS.search(html):
        add('unsafe_content', 'FAIL', 'Potential remote resource or active API pattern found (heuristic, not a security scan)')

    parser = _Document()
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, TypeError) as exc:
        add('html_parse', 'FAIL', f'HTML parser rejected content: {exc}')

    if parser.events:
        add('inline_events', 'FAIL', 'Inline HTML event handlers found: ' + ', '.join(sorted(set(parser.events))[:5]))
    if parser.dangerous_uris:
        add('unsafe_uris', 'FAIL', 'Active or remote HTML URI attributes found: ' + ', '.join(sorted(set(parser.dangerous_uris))[:5]))
    # V2 previews copy approved raster assets; other local scripts/styles
    # are still outside the C8B single-file revision contract.
    unsupported = [ref for ref in parser.local_assets
                   if not (ref.startswith('assets/') and
                           web_assets.NAME_RE.fullmatch(ref[7:]))]
    if unsupported:
        add('local_assets', 'WARN', 'Unsupported local asset reference: ' + ', '.join(sorted(set(unsupported))[:5]))
    if not parser.lang:
        add('html_lang', 'WARN', 'Set the html lang attribute, e.g. lang="vi"')
    if not parser.viewport:
        add('viewport', 'WARN', 'Add <meta name="viewport" content="width=device-width, initial-scale=1">')
    if not parser.charset:
        add('charset', 'WARN', 'Declare <meta charset="utf-8"> for predictable Vietnamese text display')
    if not ''.join(parser.title).strip():
        add('title', 'WARN', 'Add a descriptive nonempty <title>')
    if parser.headings.count(1) != 1:
        add('h1', 'WARN', f'Use exactly one <h1> (found {parser.headings.count(1)})')
    if any(b - a > 1 for a, b in zip(parser.headings, parser.headings[1:])):
        add('heading_order', 'WARN', 'Avoid skipping heading levels (e.g. h2 directly to h4)')
    duplicates = {value for value in parser.ids if parser.ids.count(value) > 1}
    if duplicates:
        add('duplicate_ids', 'WARN', 'Duplicate element IDs: ' + ', '.join(sorted(duplicates)[:5]))
    broken = sorted({target for target in parser.fragment_links if target and target not in parser.ids})
    if broken:
        add('broken_fragments', 'WARN', 'Links target missing IDs: ' + ', '.join(broken[:5]))
    if '' in parser.fragment_links:
        add('placeholder_links', 'WARN', 'A link uses href="#"; replace with a working anchor or label as a placeholder')
    if parser.image_missing_alt:
        add('image_alt', 'WARN', f'{parser.image_missing_alt} image(s) missing alt attributes')
    if not re.search(r'(?i)@media\b|clamp\s*\(|minmax\s*\(|grid-template-columns\s*:|flex-wrap\s*:|width\s*:\s*min\s*\(', html):
        add('responsive_hint', 'WARN', 'No common responsive CSS patterns detected; verify small screens in browser DevTools')

    failures = sum(x['severity'] == 'FAIL' for x in findings)
    warnings = sum(x['severity'] == 'WARN' for x in findings)
    return {'status': 'FAIL' if failures else 'WARN' if warnings else 'PASS',
            'failures': failures, 'warnings': warnings, 'findings': findings,
            'static_analysis_only': True, 'browser_rendered': False,
            'security_verified': False, 'execution_authorized': False,
            'deployment_authorized': False}


def _checked_assets(result, slug, html):
    # C8D must refuse broken local images instead of reporting a false PASS.
    try:
        images = web_assets.verify_references(slug, html)
    except (OSError, ValueError, PermissionError) as exc:
        result['findings'].append({'rule': 'local_image_invalid', 'severity': 'FAIL',
                                   'message': 'Referenced local image missing or invalid: ' + str(exc)[:180]})
        result['failures'] += 1
        result['status'] = 'FAIL'
        return result
    result['local_image_count'] = len(images)
    return result


def check_project(slug):
    """Read the existing product without writing any files; report broken HTML."""
    slug = builder._check_slug(slug)
    path = builder.PRODUCTS / slug / 'index.html'
    builder._check_path_chain(path)
    if not path.is_file():
        raise FileNotFoundError('Product index.html not found')
    raw = path.read_bytes()
    if not raw or len(raw) > builder.MAX_FILE_BYTES:
        raise ValueError('Product index.html is empty or too large for static checking')
    html = raw.decode('utf-8')
    result = _checked_assets(analyze(html), slug, html)
    return {'target': 'project', 'project_slug': slug, 'file': 'index.html',
            'sha256': revision._hash(raw), **result}


def check_revision(revision_id):
    """Read a hashed proposal; refuse stale revisions before reporting quality."""
    doc, _, receipt = revision._read_revision(revision_id)
    if receipt.exists():
        raise RuntimeError('Revision already applied; use check project_slug')
    revision._require_current(doc)
    html = doc['files'][0]['content']
    result = _checked_assets(analyze(html), doc['project_slug'], html)
    return {'target': 'revision', 'revision_id': revision_id,
            'project_slug': doc['project_slug'], 'file': 'index.html',
            'sha256': doc['sha256'], 'base_sha256': doc['base_sha256'], **result}


def preview_revision(revision_id):
    """Write a review-only HTML copy under ignored data; NEVER launch a browser."""
    result = check_revision(revision_id)
    if result['status'] == 'FAIL':
        raise ValueError('Static checks found FAIL issues; preview refused')
    doc, _, receipt = revision._read_revision(revision_id)
    if receipt.exists():
        raise RuntimeError('Revision already applied; cannot generate preview')
    revision._require_current(doc)
    html = doc['files'][0]['content']
    contents = html.encode('utf-8')
    root = builder.ROOT / 'data' / 'company' / 'product_builder' / 'previews' / revision_id
    path = root / 'index.html'
    builder._check_path_chain(path)
    root.mkdir(parents=True, exist_ok=True)
    builder._check_path_chain(path)
    if path.exists():
        if path.read_bytes() != contents:
            raise FileExistsError('Existing preview differs from approved proposal; no overwrite')
        state = 'EXISTING_VERIFIED_PREVIEW'
    else:
        with path.open('xb') as file:
            file.write(contents)
        state = 'PREVIEW_FILE_CREATED_NOT_EXECUTED'
    if path.read_bytes() != contents:
        raise IOError('Preview integrity verification failed')
    # Include only referenced, validated local raster assets. Never copy
    # arbitrary paths or execute source during a preview.
    for name in web_assets.references(html):
        data, _ = web_assets.read_image(doc['project_slug'], name)
        photo = root / 'assets' / name
        builder._check_path_chain(photo)
        photo.parent.mkdir(parents=True, exist_ok=True)
        builder._check_path_chain(photo)
        if photo.exists():
            if photo.read_bytes() != data:
                raise FileExistsError('Existing preview asset differs: ' + name)
        else:
            with photo.open('xb') as output:
                output.write(data)
        if photo.read_bytes() != data:
            raise IOError('Preview asset integrity verification failed')
    return {'status': state, 'preview_path': str(path), 'revision_id': revision_id,
            'project_slug': doc['project_slug'], 'sha256': revision._hash(contents),
            'quality_status': result['status'], 'warnings': result['warnings'],
            'browser_opened': False, 'execution_authorized': False,
            'deployment_authorized': False}


def main():
    parser = argparse.ArgumentParser(description='C8C static checks / owner-opened preview (no browser automation)')
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('check', help='Read-only quality checks of existing product')
    p.add_argument('slug')
    p = sub.add_parser('check-revision', help='Read-only quality checks of proposed revision')
    p.add_argument('revision_id')
    p = sub.add_parser('preview-revision', help='Write preview copy under data/, never launch browser')
    p.add_argument('revision_id')
    args = parser.parse_args()
    if args.action == 'check':
        result = check_project(args.slug)
    elif args.action == 'check-revision':
        result = check_revision(args.revision_id)
    else:
        result = preview_revision(args.revision_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('status') == 'FAIL':
        parser.exit(status=2)


if __name__ == '__main__':
    main()
