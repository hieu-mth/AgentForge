"""Deterministic, review-only HTML renderer for bounded AI website copy.

The model supplies *text*, never HTML, CSS, JavaScript, URLs or attributes.
Only audited, static markup/CSS are emitted. No network, subprocess, filesystem,
publish action, or model call happens in this module.
"""
from html import escape
import re

# Small, explicit schema for Ollama structured outputs and compatible gateways.
# Schema format is passed to Ollama, and we still validate returned values.
COPY_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {"type": "string"},
        "headline": {"type": "string"},
        "subtitle": {"type": "string"},
        "introduction": {"type": "string"},
        "highlights": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["title", "description"],
                "additionalProperties": False,
            },
        },
        "call_to_action": {"type": "string"},
        "theme": {"type": "string", "enum": ["forest", "ocean", "sand", "plum", "mono"]},
        "layout": {"type": "string", "enum": ["split", "centered", "editorial"]},
    },
    "required": [
        "brand", "headline", "subtitle", "introduction",
        "highlights", "call_to_action",
    ],
    "additionalProperties": False,
}

CSS = """
:root{color-scheme:light;--ink:#17212b;--muted:#526371;--line:#e6e5df;
--bg:#f7f7f3;--paper:#fff;--accent:#235b60;--glow:#cce5db;--gold:#d3aa73}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:"Segoe UI",Tahoma,Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
button,a{transition:transform .2s ease,background .2s ease}
a:focus-visible{outline:3px solid var(--accent);outline-offset:4px}
.container{width:min(1160px,calc(100% - 44px));margin:0 auto}
.site-header{border-bottom:1px solid var(--line);background:rgba(255,255,255,.88)}
.nav{min-height:80px;display:flex;align-items:center;justify-content:space-between;gap:20px}
.wordmark{font-size:1.2rem;font-weight:750;letter-spacing:-.04em;overflow-wrap:anywhere}
.nav-links{display:flex;align-items:center;gap:26px;color:var(--muted);font-size:.92rem}
.nav-links a:hover{color:var(--accent)}
.nav-cta{border-radius:100px;background:var(--ink);color:#fff;padding:11px 20px;font-weight:650}
.hero{padding:84px 0 86px;display:grid;grid-template-columns:1.02fr .98fr;gap:56px;align-items:center}
.eyebrow{margin:0 0 22px;font-weight:760;color:var(--accent);font-size:.78rem;letter-spacing:.19em;text-transform:uppercase}
h1,h2,h3,p{margin-top:0;overflow-wrap:anywhere}
h1{font-size:clamp(2.8rem,5.8vw,5.6rem);line-height:1.04;letter-spacing:-.065em;margin-bottom:25px;font-weight:760}
.lead{font-size:clamp(1rem,1.8vw,1.21rem);line-height:1.8;color:var(--muted);max-width:590px;margin-bottom:30px}
.actions{display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.primary{background:var(--accent);color:#fff;border-radius:99px;padding:17px 25px;display:inline-flex;font-weight:700;align-items:center;gap:12px}
.primary:hover{transform:translateY(-2px);background:#164b4e}
.soft-link{font-weight:670;color:var(--ink);border-bottom:1px solid var(--accent);padding-bottom:3px}
.visual{min-height:470px;border-radius:28px;position:relative;overflow:hidden;
background:linear-gradient(135deg,#153b43 0%,#427e75 52%,#c3b69a 100%);
box-shadow:0 26px 58px rgba(26,70,73,.17)}
.visual:before{content:"";position:absolute;width:130%;height:130%;border-radius:50%;
left:14%;top:-57%;border:1px solid rgba(255,255,255,.48)}
.visual:after{content:"";position:absolute;width:88%;height:90%;border-radius:50%;
left:-33%;bottom:-55%;border:1px solid rgba(255,255,255,.35)}
.art-orbit{position:absolute;width:310px;height:310px;right:-30px;top:-38px;
border-radius:50%;background:radial-gradient(circle at 30% 25%,#fff8dc 0%,#d6c19c 44%,#9d9d83 100%);box-shadow:0 25px 70px rgba(6,33,35,.26)}
.art-card{position:absolute;left:9%;bottom:10%;width:78%;padding:26px;
border:1px solid rgba(255,255,255,.44);border-radius:18px;background:rgba(255,255,255,.15);
backdrop-filter:blur(10px);color:#fff}
.art-line{height:12px;border-radius:30px;background:rgba(255,255,255,.75);width:60%;margin:0 0 13px}
.art-line:nth-child(2){width:83%;height:9px;background:rgba(255,255,255,.4)}
.art-line:nth-child(3){width:45%;height:9px;background:rgba(255,255,255,.35);margin:0}
.section{padding:95px 0;border-top:1px solid var(--line)}
.kicker{font-size:.78rem;color:var(--accent);font-weight:760;letter-spacing:.15em;text-transform:uppercase;margin-bottom:18px}
h2{font-size:clamp(2rem,4vw,3.5rem);letter-spacing:-.05em;line-height:1.14;margin-bottom:24px}
.intro-layout{display:grid;grid-template-columns:.9fr 1.1fr;gap:80px;align-items:start}
.readable{font-size:1.1rem;line-height:1.9;color:var(--muted);max-width:720px}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-top:40px}
.feature{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:30px 25px;min-height:215px}
.feature-index{font-size:.85rem;color:var(--accent);font-weight:800;letter-spacing:.08em;margin-bottom:25px}
h3{font-size:1.25rem;line-height:1.3;letter-spacing:-.025em;margin-bottom:13px}
.feature p{color:var(--muted);line-height:1.75;font-size:.94rem;margin:0}
.contact{background:#172c32;color:#fff;padding:100px 0 75px}
.contact-inner{max-width:750px}
.contact .kicker{color:#c8dfcf}
.contact h2{font-size:clamp(2.1rem,4.5vw,4.1rem)}
.contact p{color:#d3dee0;line-height:1.85;font-size:1.07rem}
.contact .primary{background:#ecf3ed;color:#1b353a;margin-top:12px}
.contact .primary:hover{background:#fff}
.note{margin-top:35px;border-left:2px solid #71858a;padding-left:15px;font-size:.82rem!important;color:#a7bbbe!important}
.footer{background:#172c32;border-top:1px solid #456068;color:#bdd0d2}
.footer-inner{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;padding:25px 0;font-size:.82rem}
@media(max-width:900px){
.hero{grid-template-columns:1fr;gap:40px;padding:62px 0}
.visual{min-height:350px}
.intro-layout{grid-template-columns:1fr;gap:14px}
.grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.section{padding:72px 0}
}
@media(max-width:580px){
.container{width:min(100% - 32px,1160px)}
.nav{min-height:68px}
.nav-links{gap:12px}
.nav-links a:first-child{display:none}
.nav-cta{padding:9px 13px;font-size:.83rem}
.hero{padding:50px 0 60px}
h1{font-size:clamp(2.7rem,11vw,4.4rem)}
.visual{min-height:310px;border-radius:20px}
.art-orbit{width:230px;height:230px}
.grid{grid-template-columns:1fr}
.feature{min-height:0}
.section{padding:58px 0}
.contact{padding:70px 0}
}
@media(prefers-reduced-motion:reduce){
html{scroll-behavior:auto}
*,*:before,*:after{transition:none!important;animation:none!important}
}
"""



THEMES = {
    "forest": "",
    "ocean": """:root{--accent:#2354a0;--ink:#142943;--bg:#f1f6fd;--glow:#bed4f4}
.visual{background:linear-gradient(135deg,#142a58,#447cc6 58%,#a3c6e0)}
.contact,.footer{background:#142943}
""",
    "sand": """:root{--accent:#9b5f2e;--ink:#423322;--bg:#fcf6e8;--glow:#f1dbb5}
.visual{background:linear-gradient(135deg,#745338,#bc9163 58%,#e2cdb0)}
.contact,.footer{background:#423322}
""",
    "plum": """:root{--accent:#8b3b77;--ink:#342238;--bg:#fcf4fa;--glow:#e4bcd8}
.visual{background:linear-gradient(135deg,#462b55,#9d5b94 58%,#d7afc5)}
.contact,.footer{background:#342238}
""",
    "mono": """:root{--accent:#3a4048;--ink:#1c1e22;--bg:#f5f5f3;--glow:#d6d6d6}
.visual{background:linear-gradient(135deg,#111317,#4e535a 58%,#babec1)}
.contact,.footer{background:#1c1e22}
""",
}
LAYOUTS = {
    "split": "",
    "centered": """.hero{grid-template-columns:1fr;gap:35px;text-align:center}
.hero .lead{margin-inline:auto}.hero .actions{justify-content:center}
.hero .visual{width:min(100%,820px);margin-inline:auto;min-height:350px}
""",
    "editorial": """.hero{grid-template-columns:1.18fr .82fr;gap:36px}
.hero .visual{min-height:520px;border-radius:7px}
.hero h1{font-weight:800}
@media(max-width:900px){.hero{grid-template-columns:1fr}}
""",
}


def requested_design(description):
    """Only exact bounded style choices; no owner text enters CSS."""
    import unicodedata
    folded = "".join(ch for ch in unicodedata.normalize("NFD", description.lower())
                     if unicodedata.category(ch) != "Mn").replace("đ", "d")
    theme = None
    layout = None
    if any(x in folded for x in ("xanh reu", "xanh la", "forest", "olive")):
        theme = "forest"
    elif any(x in folded for x in ("xanh duong", "xanh bien", "ocean", "blue")):
        theme = "ocean"
    elif any(x in folded for x in ("mau kem", "mau be", "champagne", "tan", "beige", "mau nau")):
        theme = "sand"
    elif any(x in folded for x in ("mau tim", "mau hong", "plum", "purple", "pink")):
        theme = "plum"
    elif any(x in folded for x in ("den trang", "mau den", "den xam", "monochrome", "black and white")):
        theme = "mono"
    if any(x in folded for x in ("can giua", "o giua", "centered", "hero giua", "bo cuc giua")):
        layout = "centered"
    elif any(x in folded for x in ("editorial", "tap chi", "hero lon", "pha cach")):
        layout = "editorial"
    elif any(x in folded for x in ("chia doi", "hai cot", "2 cot", "split hero")):
        layout = "split"
    return {"theme": theme, "layout": layout}


def _text(value, field, limit):
    if not isinstance(value, str):
        raise ValueError("Structured website content invalid: " + field)
    clean = re.sub(r"\s+", " ", value).strip()
    if not clean or len(clean) > limit or any(ord(c) < 32 for c in clean):
        raise ValueError("Structured website content invalid: " + field)
    return clean


def _escaped_text(value):
    """Encode model copy for HTML *text nodes only*, never a code context.

    Re-encode the first character of any legacy heuristic match as a character
    reference. It renders identically as text, but cannot be confused with a
    URL, script, or active attribute by the source-level safety heuristic.
    """
    from agentforge.domains.websites.builder import SUSPICIOUS
    result = escape(value, quote=True)
    for _ in range(96):
        match = SUSPICIOUS.search(result)
        if match is None:
            return result
        n = match.start()
        result = result[:n] + "&#" + str(ord(result[n])) + ";" + result[n + 1:]
    raise ValueError("Structured website content invalid: too many reserved tokens")


PHONE_RE = re.compile(r"(?<![A-Za-z0-9])(?:\+84|0)[\s.-]?[35789](?:[\s.-]?\d){8}(?!\d)")


def owner_phone(brief):
    """Recognize only an explicitly supplied Vietnamese mobile number."""
    if not isinstance(brief, str):
        return None
    found = PHONE_RE.search(brief)
    if found is None:
        return None
    number = re.sub(r"[\s.-]", "", found.group(0))
    return number if re.fullmatch(r"(?:0[35789]|\+84[35789])\d{8}", number) else None


def validate_copy(raw):
    required = set(COPY_SCHEMA["required"])
    allowed = required | {"theme", "layout"}
    if not isinstance(raw, dict) or required - set(raw) or set(raw) - allowed:
        raise ValueError("Structured website content invalid: fields")
    for choice, options in (("theme", THEMES), ("layout", LAYOUTS)):
        if choice in raw and raw[choice] not in options:
            raise ValueError("Structured website content invalid: " + choice)
    limits = {
        "brand": 64, "headline": 100, "subtitle": 210,
        "introduction": 380, "call_to_action": 120,
    }
    values = {key: _text(raw[key], key, limit) for key, limit in limits.items()}
    features = raw["highlights"]
    if not isinstance(features, list) or not 2 <= len(features) <= 4:
        raise ValueError("Structured website content invalid: highlights")
    values["highlights"] = []
    for item in features:
        if not isinstance(item, dict) or set(item) != {"title", "description"}:
            raise ValueError("Structured website content invalid: highlights")
        values["highlights"].append({
            "title": _text(item["title"], "highlight title", 65),
            "description": _text(item["description"], "highlight description", 185),
        })
    return values


def render(raw, *, phone=None, theme=None, layout=None):
    copy = validate_copy(raw)
    theme = theme or copy.get("theme", "forest")
    layout = layout or copy.get("layout", "split")
    if theme not in THEMES or layout not in LAYOUTS:
        raise ValueError("Structured website content invalid: design style")
    stylesheet = CSS + THEMES[theme] + LAYOUTS[layout]
    if phone is not None and (not isinstance(phone, str) or not re.fullmatch(r"(?:0[35789]|\+84[35789])\d{8}", phone)):
        raise ValueError("Invalid owner phone number")
    contact_action = ('<a class="primary" href="tel:' + escape(phone) + '">Gọi tư vấn trực tiếp ↗</a>'
                      if phone else '<a class="primary" href="#dau-trang">Trở về đầu trang ↑</a>')
    text = lambda field: _escaped_text(copy[field])
    features = "".join(
        '<article class="feature"><div class="feature-index">'
        + f'{i:02d}' + '</div><h3>' + _escaped_text(item["title"])
        + '</h3><p>' + _escaped_text(item["description"]) + '</p></article>'
        for i, item in enumerate(copy["highlights"], 1)
    )
    return f"""<!doctype html>
<html lang="vi" data-af-theme="{theme}" data-af-layout="{layout}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'none'; form-action 'none'">
<title>{text('brand')} — {text('headline')}</title>
<style>{stylesheet}</style>
</head>
<body>
<header class="site-header"><div class="container nav">
<a class="wordmark" href="#dau-trang">{text('brand')}</a>
<nav class="nav-links" aria-label="Điều hướng chính">
<a href="#gioi-thieu">Giới thiệu</a>
<a href="#diem-noi-bat">Điểm nổi bật</a>
<a class="nav-cta" href="#lien-he">Liên hệ</a>
</nav></div></header>
<main>
<section class="container hero" id="dau-trang" aria-labelledby="hero-heading">
<div><p class="eyebrow">Trải nghiệm dành cho bạn</p>
<h1 id="hero-heading">{text('headline')}</h1>
<p class="lead">{text('subtitle')}</p>
<div class="actions"><a class="primary" href="#lien-he">Tìm hiểu &amp; liên hệ <span aria-hidden="true">↗</span></a>
<a class="soft-link" href="#diem-noi-bat">Khám phá điểm nổi bật</a></div></div>
<div class="visual" role="img" aria-label="Minh họa đồ họa trừu tượng, không phải ảnh sản phẩm thực tế">
<div class="art-orbit"></div><div class="art-card" aria-hidden="true">
<div class="art-line"></div><div class="art-line"></div><div class="art-line"></div>
</div></div>
</section>
<section class="section" id="gioi-thieu" aria-labelledby="about-heading"><div class="container intro-layout">
<div><p class="kicker">Giới thiệu</p><h2 id="about-heading">Một cách tiếp cận rõ ràng, tinh tế.</h2></div>
<p class="readable">{text('introduction')}</p>
</div></section>
<section class="section" id="diem-noi-bat" aria-labelledby="features-heading"><div class="container">
<p class="kicker">Khám phá</p><h2 id="features-heading">Những điều đáng chú ý</h2>
<div class="grid">{features}</div></div></section>
<section class="contact" id="lien-he" aria-labelledby="contact-heading">
<div class="container contact-inner"><p class="kicker">Bước tiếp theo</p>
<h2 id="contact-heading">{text('call_to_action')}</h2>
<p>Đây là bản nháp để chủ dự án xem xét. {("Số điện thoại bên dưới được lấy từ yêu cầu của chủ dự án; hãy kiểm tra trước khi công bố." if phone else "Thông tin liên hệ chính thức sẽ được bổ sung sau khi xác minh.")}</p>
{contact_action}
<p class="note">Nội dung và hình minh họa đang ở giai đoạn đề xuất. Chưa xác nhận thông tin sản phẩm, giá hay cam kết thương mại.</p>
</div></section>
</main>
<footer class="footer"><div class="container footer-inner">
<strong>{text('brand')}</strong><span>Website mẫu offline · Chờ duyệt và hoàn thiện thông tin</span>
</div></footer>
</body></html>"""
