"""AI-directed offline web design compiler, not a hard-coded page template.

The model chooses section count/order, copy, typography family, palette, hero
composition, density, cards, and decorative art through a bounded JSON spec.
Trusted code owns markup/CSS. No HTML/CSS/JS from the model is executed.
"""
import json
import re
from html import escape

from agentforge.features.websites.structured_builder import _escaped_text

SITE_FORMAT = "agentforge.design.v1"
KINDS = ("features", "story", "steps", "faq", "gallery", "comparison", "callout")
VARIANTS = ("grid", "split", "list", "accent")
FONTS = ("modern", "editorial", "rounded", "technical")
HEROS = ("split", "centered", "stacked", "editorial")
ARTS = ("orbit", "geometry", "gradient", "minimal", "none")
DENSITIES = ("airy", "balanced", "compact")
CARDS = ("elevated", "bordered", "flat")

def _object(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(required or properties), "additionalProperties": False}

def _enum(values):
    return {"type": "string", "enum": list(values)}

ITEM_SCHEMA = _object({"title": {"type": "string"}, "body": {"type": "string"}})
SECTION_SCHEMA = _object({
    "kind": _enum(KINDS),
    "variant": _enum(VARIANTS),
    "eyebrow": {"type": "string"},
    "title": {"type": "string"},
    "intro": {"type": "string"},
    "items": {"type": "array", "minItems": 0, "maxItems": 4, "items": ITEM_SCHEMA},
})
STYLE_SCHEMA = _object({
    "background": {"type": "string"},
    "surface": {"type": "string"},
    "accent": {"type": "string"},
    "font": _enum(FONTS),
    "hero_layout": _enum(HEROS),
    "art": _enum(ARTS),
    "density": _enum(DENSITIES),
    "cards": _enum(CARDS),
    "radius": {"type": "integer", "minimum": 0, "maximum": 28},
})
HERO_SCHEMA = _object({
    "eyebrow": {"type": "string"},
    "headline": {"type": "string"},
    "description": {"type": "string"},
    "primary_action": {"type": "string"},
    "secondary_action": {"type": "string"},
})
DESIGN_SCHEMA = _object({
    "brand": {"type": "string"},
    "page_title": {"type": "string"},
    "description": {"type": "string"},
    "style": STYLE_SCHEMA,
    "hero": HERO_SCHEMA,
    "sections": {"type": "array", "minItems": 2, "maxItems": 7, "items": SECTION_SCHEMA},
})

COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")

def _text(value, name, maximum, *, empty=False):
    if not isinstance(value, str):
        raise ValueError("AI_DESIGN_INVALID: " + name)
    cleaned = re.sub(r"\s+", " ", value).strip()
    if (len(cleaned) > maximum or (not cleaned and not empty)
            or any(ord(char) < 32 for char in cleaned)):
        raise ValueError("AI_DESIGN_INVALID: " + name)
    return cleaned

def _shape(value, keys, name):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("AI_DESIGN_INVALID: " + name)
    return value

def _choice(value, options, name):
    if not isinstance(value, str) or value not in options:
        raise ValueError("AI_DESIGN_INVALID: " + name)
    return value

def _color(value, name):
    if not isinstance(value, str) or not COLOR.fullmatch(value):
        raise ValueError("AI_DESIGN_INVALID: " + name)
    return value.lower()

def validate_spec(raw):
    """Strictly validate untrusted model JSON; no silent shape coercion."""
    _shape(raw, DESIGN_SCHEMA["properties"], "root")
    clean = {key: _text(raw[key], key, maximum) for key, maximum in (
        ("brand", 64), ("page_title", 110), ("description", 210))}
    style = _shape(raw["style"], STYLE_SCHEMA["properties"], "style")
    clean["style"] = {key: _color(style[key], key)
                      for key in ("background", "surface", "accent")}
    for key, values in (("font", FONTS), ("hero_layout", HEROS), ("art", ARTS),
                        ("density", DENSITIES), ("cards", CARDS)):
        clean["style"][key] = _choice(style[key], values, key)
    if type(style["radius"]) is not int or not 0 <= style["radius"] <= 28:
        raise ValueError("AI_DESIGN_INVALID: radius")
    clean["style"]["radius"] = style["radius"]
    hero = _shape(raw["hero"], HERO_SCHEMA["properties"], "hero")
    clean["hero"] = {key: _text(hero[key], key, maximum, empty=key in ("eyebrow", "secondary_action"))
                     for key, maximum in (("eyebrow", 75), ("headline", 110),
                     ("description", 300), ("primary_action", 54),
                     ("secondary_action", 54))}
    sections = raw["sections"]
    if not isinstance(sections, list) or not 2 <= len(sections) <= 7:
        raise ValueError("AI_DESIGN_INVALID: sections")
    clean["sections"] = []
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise ValueError("AI_DESIGN_INVALID: section")
        _shape(section, SECTION_SCHEMA["properties"], "section")
        item_list = section["items"]
        if not isinstance(item_list, list) or len(item_list) > 4:
            raise ValueError("AI_DESIGN_INVALID: section items")
        kind = _choice(section["kind"], KINDS, "section kind")
        if kind in ("features", "steps", "faq", "gallery", "comparison") and not 2 <= len(item_list) <= 4:
            raise ValueError("AI_DESIGN_INVALID: section item count")
        if kind in ("story", "callout") and len(item_list) > 2:
            raise ValueError("AI_DESIGN_INVALID: section item count")
        section_result = {
            "kind": kind,
            "variant": _choice(section["variant"], VARIANTS, "section variant"),
            "eyebrow": _text(section["eyebrow"], "eyebrow", 70, empty=True),
            "title": _text(section["title"], "section title", 120),
            "intro": _text(section["intro"], "section intro", 340, empty=True),
            "items": [],
        }
        for item in item_list:
            _shape(item, ITEM_SCHEMA["properties"], "item")
            section_result["items"].append({
                "title": _text(item["title"], "item title", 105),
                "body": _text(item["body"], "item body", 240),
            })
        clean["sections"].append(section_result)
    return clean

def _luminance(color):
    rgb = [int(color[index:index+2], 16) / 255 for index in (1, 3, 5)]
    channel = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return .2126 * channel[0] + .7152 * channel[1] + .0722 * channel[2]

def _contrast(first, second):
    left, right = _luminance(first), _luminance(second)
    return (max(left, right) + .05) / (min(left, right) + .05)


def _best_text(background):
    brightness = _luminance(background)
    dark = "#17212b"
    light = "#ffffff"
    dark_contrast = (brightness + .05) / (_luminance(dark) + .05)
    light_contrast = (1.0 + .05) / (brightness + .05)
    return dark if dark_contrast >= light_contrast else light

def _safe(value):
    return _escaped_text(value)

BASE_CSS = """
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--background);color:var(--ink);font-family:var(--family);
-webkit-font-smoothing:antialiased;line-height:1.6}
a{color:inherit;text-decoration:none}a:focus-visible{outline:3px solid var(--accent);outline-offset:4px}
h1,h2,h3,p{margin-top:0;overflow-wrap:anywhere}h1,h2,h3{line-height:1.12;letter-spacing:-.04em}
.wrapper{max-width:1160px;width:calc(100% - 48px);margin:auto}
header{border-bottom:1px solid var(--line)}.topbar{display:flex;min-height:76px;align-items:center;
gap:24px;justify-content:space-between}.brand{font-size:1.3rem;font-weight:800;letter-spacing:-.04em}
.navigation{display:flex;gap:18px;align-items:center;font-size:.88rem}.navigation a:hover{text-decoration:underline}
.button{background:var(--accent);color:var(--accent-ink);border-radius:var(--radius);
padding:14px 22px;display:inline-flex;align-items:center;font-weight:700;gap:9px;line-height:1.3}
.button:hover{filter:brightness(.94);transform:translateY(-2px)}.button.ghost{border:1px solid var(--line);
background:transparent;color:var(--ink)}.button:focus-visible{outline-offset:4px}
.hero{display:grid;grid-template-columns:1.1fr .9fr;gap:clamp(24px,5vw,72px);align-items:center;
padding:var(--spacing) 0}.hero h1{font-size:clamp(2.6rem,6vw,5.6rem);line-height:1.06;margin-bottom:24px}
.hero p.summary{color:var(--ink);opacity:.8;font-size:clamp(1rem,1.8vw,1.2rem);max-width:580px}
.eyebrow{font-size:.8rem;letter-spacing:.14em;font-weight:800;text-transform:uppercase;
margin:0 0 18px;color:var(--label-ink)}.actions{display:flex;gap:14px;flex-wrap:wrap;margin-top:32px}
.hero-art{min-height:360px;border-radius:var(--art-radius);overflow:hidden;
position:relative;background:linear-gradient(145deg,var(--accent),var(--surface))}
.hero-art:before,.hero-art:after{content:"";position:absolute;display:block}
.art-orbit:before{width:80%;aspect-ratio:1;border:1px solid rgba(255,255,255,.5);
border-radius:50%;left:28%;top:-30%}.art-orbit:after{width:53%;aspect-ratio:1;border-radius:50%;
background:rgba(255,255,255,.24);left:-12%;bottom:-30%}
.art-geometry:before{width:60%;height:60%;background:rgba(255,255,255,.25);
transform:rotate(32deg);right:-10%;top:-20%}
.art-geometry:after{width:64%;height:38%;border:2px solid rgba(255,255,255,.7);
transform:rotate(-19deg);bottom:10%;left:12%}
.art-gradient{background:linear-gradient(110deg,var(--surface),var(--accent),var(--ink))}
.art-gradient:before{width:80%;height:80%;left:10%;top:10%;
background:radial-gradient(circle,rgba(255,255,255,.4),transparent 66%)}
.art-minimal{background:var(--surface);border:1px solid var(--line)}
.art-minimal:after{height:2px;width:70%;top:49%;left:15%;background:var(--accent)}
.hero-centered{grid-template-columns:1fr;text-align:center}.hero-centered .actions{justify-content:center}
.hero-centered .summary{margin-inline:auto}
.hero-centered .hero-art{width:min(100%,850px);margin:auto}
.hero-stacked{grid-template-columns:1fr}.hero-stacked .hero-art{min-height:220px}
.hero-editorial{grid-template-columns:1.3fr .7fr}.hero-editorial .hero-art{min-height:485px}
.section{padding:var(--spacing) 0;border-top:1px solid var(--line)}
.section h2{font-size:clamp(2rem,3.8vw,3.6rem);max-width:800px;margin:0 0 22px}
.section .intro{font-size:1.05rem;opacity:.78;max-width:760px;margin-bottom:26px}
.items{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}
.item{padding:24px;border:1px solid var(--line);border-radius:var(--radius);
background:var(--surface);color:var(--surface-ink)}
.item h3{font-size:1.2rem;margin:0 0 12px}.item p{margin:0;opacity:.84}
.item-no{font-size:.75rem;font-weight:800;letter-spacing:.1em;opacity:.6;margin-bottom:15px}
.variant-list .items{grid-template-columns:1fr}.variant-list .item{display:grid;
grid-template-columns:110px 1fr;gap:16px;align-items:start}
.variant-split .items{grid-template-columns:repeat(2,minmax(0,1fr))}
.variant-accent{background:var(--surface);color:var(--surface-ink)}
.variant-accent .item{background:var(--background);color:var(--ink)}
.section--story .items,.section--callout .items{grid-template-columns:1fr}
.section--story .item,.section--callout .item{max-width:800px}
.section--faq .items,.section--steps .items{grid-template-columns:repeat(2,minmax(0,1fr))}
.section--gallery .item{min-height:210px;background:linear-gradient(155deg,var(--surface),var(--accent));
color:var(--surface-ink);display:flex;flex-direction:column;justify-content:end}
.section--comparison .item{border-left:4px solid var(--accent)}
.contact{padding:var(--spacing) 0;background:var(--ink);color:var(--background)}
.contact-inner{max-width:820px}.contact h2{font-size:clamp(2.2rem,4.5vw,4.2rem)}
.contact p{opacity:.82}.contact .eyebrow{color:var(--surface)}
footer{padding:25px 0;background:var(--ink);color:var(--background);border-top:1px solid rgba(255,255,255,.15)}
.footer-row{display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap;font-size:.83rem}
@media(max-width:900px){.hero,.hero-editorial{grid-template-columns:1fr}.items{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.wrapper{width:calc(100% - 32px)}.topbar{min-height:66px}
.navigation{gap:9px;font-size:.78rem}.navigation a:nth-child(n+3){display:none}
.hero,.hero-editorial{grid-template-columns:1fr;padding:54px 0}
.hero h1{font-size:clamp(2.45rem,10vw,4rem)}.hero-art{min-height:270px}
.items,.variant-list .items,.variant-split .items,.section--faq .items,
.section--steps .items{grid-template-columns:1fr}.variant-list .item{grid-template-columns:1fr}
.section{padding:56px 0}.item{padding:22px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}
*,*:before,*:after{transition:none!important;animation:none!important}}
"""
FONT_STACKS = {
    "modern": '"Segoe UI",Tahoma,Arial,sans-serif',
    "editorial": 'Georgia,"Times New Roman",serif',
    "rounded": '"Trebuchet MS","Segoe UI",sans-serif',
    "technical": 'Consolas,"Segoe UI",monospace',
}
SPACING = {"airy": "105px", "balanced": "76px", "compact": "52px"}

def render(spec, *, phone=None):
    data = validate_spec(spec)
    if phone is not None and (not isinstance(phone, str) or
            re.fullmatch(r"(?:0[35789]|\+84[35789])\d{8}", phone) is None):
        raise ValueError("Invalid owner phone number")
    style = data["style"]
    bg, surface, accent = (style[k] for k in ("background", "surface", "accent"))
    ink, surface_ink, accent_ink = (_best_text(c) for c in (bg, surface, accent))
    radius = style["radius"]
    # Preserve model palette, but never sacrifice small text readability.
    label_ink = accent if _contrast(accent, bg) >= 4.5 else ink
    vars_css = (":root{--background:" + bg + ";--surface:" + surface +
                ";--accent:" + accent + ";--label-ink:" + label_ink + ";--ink:" + ink +
                ";--surface-ink:" + surface_ink + ";--accent-ink:" + accent_ink +
                ";--line:" + ("#d2d3d3" if ink=="#17212b" else "#59616c") +
                ";--family:" + FONT_STACKS[style["font"]] +
                ";--radius:" + str(radius) + "px;--art-radius:" + str(radius+6) +
                "px;--spacing:" + SPACING[style["density"]] + "}")
    css = vars_css + BASE_CSS
    hero = data["hero"]
    hero_layout = style["hero_layout"] if style["art"] != "none" else "centered"
    art_html = ('<div class="hero-art art-' + style["art"] +
                '" role="img" aria-label="Minh họa trang trí bằng CSS, không phải ảnh sản phẩm"></div>'
                if style["art"] != "none" else '')
    secondary_html = ('<a class="button ghost" href="#sec-1">' +
                      _safe(hero["secondary_action"]) + '</a>'
                      if hero["secondary_action"] else '')
    sections = data["sections"]
    nav = "".join('<a href="#sec-' + str(index) + '">' + _safe(section["title"]) + '</a>'
                  for index, section in enumerate(sections[:2], 1))
    content = []
    for index, section in enumerate(sections, 1):
        item_html = ""
        for j, item in enumerate(section["items"], 1):
            item_html += (
                '<article class="item"><div class="item-no">' + f"{j:02}" +
                '</div><h3>' + _safe(item["title"]) + '</h3><p>' +
                _safe(item["body"]) + '</p></article>'
            )
        intro = '<p class="intro">' + _safe(section["intro"]) + '</p>' if section["intro"] else ""
        items_html = '<div class="items">' + item_html + '</div>' if item_html else ""
        content.append(
            '<section class="section section--' + section["kind"] +
            ' variant-' + section["variant"] + '" id="sec-' + str(index) +
            '" aria-labelledby="section-heading-' + str(index) + '"><div class="wrapper">' +
            ('<p class="eyebrow">' + _safe(section["eyebrow"]) + '</p>' if section["eyebrow"] else '') +
            '<h2 id="section-heading-' + str(index) + '">' + _safe(section["title"]) +
            '</h2>' + intro + items_html + '</div></section>'
        )
    primary = ("tel:" + escape(phone, quote=True)) if phone else "#contact"
    contact_action = ('<a class="button" href="tel:' + escape(phone, quote=True) +
                      '">Gọi tư vấn trực tiếp</a>' if phone else
                      '<a class="button" href="#top">Trở về đầu trang</a>')
    disclaimer = ("Số điện thoại được lấy từ yêu cầu của Owner và cần kiểm tra trước khi công bố."
                  if phone else "Chưa có thông tin liên hệ đã xác minh; Owner cần bổ sung trước khi sử dụng.")
    return ('<!doctype html><html lang="vi" data-af-version="designer-v1"'
            ' data-af-layout="' + hero_layout + '"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="color-scheme" content="light dark">'
            '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;;'
            ' style-src &#39;unsafe-inline&#39;; img-src &#39;self&#39;; base-uri &#39;none&#39;;'
            ' form-action &#39;none&#39;">'
            '<meta name="description" content="' + _safe(data["description"]) + '">'
            '<title>' + _safe(data["page_title"]) + '</title><style>' + css + '</style>'
            '</head><body id="top"><header><div class="wrapper topbar">'
            '<a class="brand" href="#top">' + _safe(data["brand"]) + '</a>'
            '<nav class="navigation" aria-label="Điều hướng">' + nav +
            '<a href="#contact">Liên hệ</a></nav></div></header><main>'
            '<section class="wrapper hero hero-' + hero_layout +
            '" aria-labelledby="hero-heading"><div class="hero-copy">' +
            ('<p class="eyebrow">' + _safe(hero["eyebrow"]) + '</p>' if hero["eyebrow"] else '') +
            '<h1 id="hero-heading">' + _safe(hero["headline"]) + '</h1>'
            '<p class="summary">' + _safe(hero["description"]) + '</p>'
            '<div class="actions"><a class="button" href="' + primary + '">' +
            _safe(hero["primary_action"]) + '</a>' + secondary_html + '</div></div>' +
            art_html + '</section>'
            + "".join(content) +
            '<section class="contact" id="contact"><div class="wrapper contact-inner">'
            '<p class="eyebrow">Liên hệ</p><h2>Trao đổi để tìm giải pháp phù hợp</h2><p>' +
            _safe(disclaimer) + '</p>' + contact_action +
            '</div></section></main><footer><div class="wrapper footer-row"><strong>' +
            _safe(data["brand"]) + '</strong><span>Website bản nháp offline · Chờ Owner xác minh</span>'
            '</div></footer></body></html>')

def encode_spec(spec):
    """Versioned, validated and non-executable design JSON for signed proposal."""
    record = {"format": SITE_FORMAT, "design": validate_spec(spec)}
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def decode_spec(text):
    """Reject mismatched/unknown versions before consuming previous design."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > 48_000:
        raise ValueError("AI_DESIGN_INVALID: design file size")
    try:
        record = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ValueError("AI_DESIGN_INVALID: JSON file") from exc
    if (not isinstance(record, dict) or set(record) != {"format", "design"}
            or record["format"] != SITE_FORMAT):
        raise ValueError("AI_DESIGN_INVALID: design format")
    return validate_spec(record["design"])
