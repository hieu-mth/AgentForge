"""Shared offline presentation kit for new web builds and V2 revisions.

Deterministic HTML processing only. No LLM, browser, network or disk writes.
All generated HTML must still pass Product Builder's untrusted-source checks.
"""
import re

# Built-in vector illustration is original, offline and NOT a product photo.
# Replaced by owner-supplied local photos when available.
BEDROOM_ART = """<figure class="af-v2-photo" aria-label="Minh họa phòng ngủ sang trọng">
<svg role="img" aria-label="Minh họa chiếc giường và không gian nghỉ ngơi"
viewBox="0 0 840 510" width="840" height="510">
<defs>
<linearGradient id="afwall" x2="0" y2="1"><stop stop-color="#e6d9c3"/>
<stop offset="1" stop-color="#faf5eb"/></linearGradient>
<linearGradient id="afbed" x2="0" y2="1"><stop stop-color="#fffef9"/>
<stop offset="1" stop-color="#c8b9a3"/></linearGradient>
</defs>
<rect width="840" height="510" fill="url(#afwall)"/>
<rect x="0" y="360" width="840" height="150" fill="#b99f80"/>
<path d="M0 360H840" stroke="#a58b70" stroke-width="5"/>
<rect x="80" y="65" width="205" height="200" rx="7" fill="#927f67"/>
<rect x="91" y="75" width="183" height="181" fill="#f9f4ea"/>
<path d="M181 75V256M91 165H274" stroke="#ad9c81" stroke-width="7"/>
<path d="M91 75H274V256H91" fill="#b0bcaf" opacity=".2"/>
<rect x="600" y="65" width="144" height="185" rx="65" fill="#c9b79b"/>
<rect x="611" y="76" width="122" height="163" rx="59" fill="#efe5d6"/>
<rect x="605" y="345" width="133" height="82" rx="9" fill="#6c624f"/>
<rect x="654" y="259" width="12" height="86" fill="#8b7558"/>
<path d="M624 275Q659 228 696 275Z" fill="#f4eddc"/>
<ellipse cx="660" cy="345" rx="25" ry="7" fill="#d7c5a3"/>
<rect x="135" y="190" width="480" height="185" rx="24" fill="#766b5c"/>
<rect x="151" y="205" width="448" height="157" rx="21" fill="#a99986"/>
<path d="M113 360L620 360L742 458H31Z" fill="#e9ddcc"/>
<path d="M113 360L620 360L720 439H54Z" fill="url(#afbed)"/>
<path d="M150 362L610 362L668 404H102Z" fill="#f9f6ef"/>
<rect x="174" y="307" width="167" height="62" rx="22" fill="#fffdf8"/>
<rect x="374" y="307" width="167" height="62" rx="22" fill="#fffdf8"/>
<path d="M86 441H706" stroke="#b7a58e" stroke-width="10" stroke-linecap="round"/>
<rect x="100" y="452" width="595" height="23" rx="10" fill="#6f6454"/>
<path d="M121 475V491M674 475V491" stroke="#615546" stroke-width="14"/>
<rect x="22" y="482" width="800" height="5" fill="#ac9476" opacity=".5"/>
</svg><figcaption>Minh họa phong cách phòng ngủ — không phải ảnh mẫu nệm thật.</figcaption></figure>"""

DESIGN_CSS = """<style id="agentforge-web-design-v2">
:root{--af-cream:#f8f3ea;--af-dark:#302e29;--af-wood:#75604b;--af-gold:#b39265}
html{scroll-behavior:smooth}
body{margin:0;background:var(--af-cream);color:var(--af-dark);
font-family:"Segoe UI",Tahoma,Arial,sans-serif;line-height:1.65;
-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
*,*::before,*::after{box-sizing:border-box}
h1,h2,h3{font-family:"Segoe UI",Tahoma,Arial,sans-serif;font-weight:600;
letter-spacing:-.035em;line-height:1.18;overflow-wrap:break-word}
h1{font-size:clamp(2.2rem,5vw,4.7rem)}
h2{font-size:clamp(1.6rem,3vw,2.7rem)}
p,li{line-height:1.7}
img,svg{max-width:100%;height:auto}
a{transition:color .25s ease,background .25s ease,transform .25s ease}
a:focus-visible,button:focus-visible{outline:3px solid var(--af-gold);outline-offset:4px}
a:hover,button:hover{transform:translateY(-2px)}
button,[class*="btn"],[class*="button"],a[href^="#lien-he"],a[href^="tel:"]{
transition:transform .25s ease,box-shadow .25s ease}
header,main,footer{max-width:100%}
section{scroll-margin-top:5rem}
.af-v2-photo{margin:2rem auto 2.5rem;max-width:970px;position:relative;
overflow:hidden;border-radius:24px;background:#e8dcc8;
box-shadow:0 28px 68px rgba(70,50,35,.14)}
.af-v2-photo svg,.af-v2-photo img{display:block;width:100%;height:auto;object-fit:cover}
.af-v2-photo figcaption{font-size:.78rem;color:#65594e;padding:.6rem 1rem;background:#f6efe4}
@keyframes af-v2-enter{from{opacity:0;transform:translateY(13px)}
to{opacity:1;transform:translateY(0)}}
main>section,main>.af-v2-photo{animation:af-v2-enter .65s ease both}
@media(max-width:680px){body{font-size:16px}section{scroll-margin-top:3rem}
.af-v2-photo{border-radius:14px;margin:1.2rem auto}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}
*,*::before,*::after{animation:none!important;transition:none!important}}
</style>"""


# Neutral fallback art for new projects without a model-provided visual.
# It is illustrative, not a real product image.
GENERIC_ART = """<figure class="af-v2-photo" aria-label="Minh họa đồ họa trang trí">
<svg role="img" aria-label="Minh họa hình học trừu tượng tông kem và nâu"
viewBox="0 0 840 480" width="840" height="480">
<rect width="840" height="480" fill="#eee4d4"/>
<circle cx="640" cy="112" r="185" fill="#d4c1aa"/>
<circle cx="682" cy="130" r="105" fill="#e9ddcd"/>
<rect x="118" y="94" width="355" height="300" rx="30" fill="#fdfaf4"/>
<path d="M175 340L305 175L411 306" fill="none" stroke="#9b8164" stroke-width="16" stroke-linecap="round"/>
<circle cx="310" cy="176" r="28" fill="#bd9b70"/>
<path d="M0 410Q190 350 395 420T840 385V480H0Z" fill="#c0a78d"/>
</svg><figcaption>Minh họa đồ họa trang trí — không phải ảnh sản phẩm thực tế.</figcaption></figure>"""

def upgrade_html(raw, images, *, fallback_art=BEDROOM_ART):
    """Add conservative V2 polish without executing or trusting model output."""
    from agentforge.product_builder import _standalone_html
    html = _standalone_html(raw)
    if not re.search(r'(?is)<head(?:\s|>)', html):
        raise ValueError("V2 requires a complete HTML head")
    if re.search(r'(?i)<html\b[^>]*\blang\s*=', html):
        html = re.sub(r'(?i)(<html\b[^>]*\blang\s*=)["\x27]?[^\s>"\x27]+["\x27]?',
                      lambda m: m.group(1) + '"vi"', html, count=1)
    else:
        html = re.sub(r'(?i)<html(?=[\s>])', '<html lang="vi"', html, count=1)
    if not re.search(r'(?is)<meta\s+charset\s*=\s*["\x27]?utf-8', html):
        html = re.sub(r'(?i)<head\s*>', '<head><meta charset="utf-8">', html, count=1)
    if not re.search(r'(?i)<meta\s+name\s*=\s*["\x27]viewport', html):
        html = re.sub(r'(?i)<head\s*>',
            '<head><meta name="viewport" content="width=device-width, initial-scale=1">',
            html, count=1)
    html = re.sub(r'(?i)</head\s*>', DESIGN_CSS + '</head>', html, count=1)

    # A REAL local photo is preferred when present; an original inline SVG
    # is otherwise the offline visual fallback (not mislabelled as merchandise).
    if images and not re.search(r'(?i)<img\b[^>]*src=["\x27]assets/', html):
        name = next((a["name"] for a in images if a["name"].startswith("hero.")),
                    images[0]["name"])
        art = (f'<figure class="af-v2-photo"><img src="assets/{name}" '
               'alt="Ảnh tư vấn nệm do chủ cửa hàng cung cấp" width="960" '
               'height="580" loading="eager"><figcaption>Ảnh minh họa do '
               'chủ cửa hàng cung cấp.</figcaption></figure>')
    elif not images and not re.search(r'(?i)<(?:img|svg|picture)\b', html):
        art = fallback_art
    else:
        art = ""
    if art:
        if re.search(r'(?i)</h1\s*>', html):
            html = re.sub(r'(?i)</h1\s*>', '</h1>' + art, html, count=1)
        elif re.search(r'(?i)<main(?:\s|>)', html):
            html = re.sub(r'(?i)<main(?=[\s>])[^>]*>',
                          lambda m: m.group(0) + art, html, count=1)
        else:
            html = re.sub(r'(?i)<body[^>]*>',
                          lambda m: m.group(0) + art, html, count=1)
    return html


