"""Bounded, read-only context from a SHA-verified website proposal.

Treat extracted previous copy as untrusted *data*, never as instructions.
No model, filesystem writes, or browser execution.
"""
from html.parser import HTMLParser
import re

MAX_CONTEXT_CHARS = 3200
KNOWN_THEMES = frozenset({"forest", "ocean", "sand", "plum", "mono"})
KNOWN_LAYOUTS = frozenset({"split", "centered", "editorial"})


class _WebsiteText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_body = False
        self.hidden = 0
        self.parts = []
        self.theme = None
        self.layout = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "html":
            if attrs.get("data-af-theme") in KNOWN_THEMES:
                self.theme = attrs["data-af-theme"]
            if attrs.get("data-af-layout") in KNOWN_LAYOUTS:
                self.layout = attrs["data-af-layout"]
        if tag == "body":
            self.in_body = True
        if tag in {"script", "style", "template"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template"} and self.hidden:
            self.hidden -= 1
        if tag == "body":
            self.in_body = False

    def handle_data(self, data):
        if not self.in_body or self.hidden:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if text and sum(map(len, self.parts)) < MAX_CONTEXT_CHARS:
            self.parts.append(text)


def inspect_previous_html(html):
    if not isinstance(html, str):
        raise ValueError("Invalid website source")
    parser = _WebsiteText()
    parser.feed(html)
    parser.close()
    return {
        "visible_text": "\n".join(parser.parts)[:MAX_CONTEXT_CHARS],
        "theme": parser.theme,
        "layout": parser.layout,
    }
