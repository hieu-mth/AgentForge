"""Static, privacy-conscious referral website: call/Zalo, never fake checkout.

No public AgentForge API, no JS, no customer-data collection in generated HTML,
no remote fonts/scripts; no unverified product prices or delivery promises.
Owner exports generated output to a separately reviewed public host.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
from pathlib import Path

from agentforge.paths import COMPANY_DATA_DIR, PRODUCTS_DIR, ensure_local_root
from agentforge.features.mattress_sales.service import PHONE, MattressError, _text

SETTINGS = COMPANY_DATA_DIR / "mattress_site.json"
OUT = PRODUCTS_DIR / "mattress-referral-mvp"
MARKER = "<!-- agentforge-mattress-mvp-v1 -->"
MAX_SITE_BYTES = 100_000


def validate(settings):
    if not isinstance(settings, dict) or set(settings) != {
            "brand", "phone", "zalo_phone", "intro", "products"}:
        raise MattressError("Site settings fields are invalid")
    brand = _text(settings["brand"], "business name", 90)
    intro = _text(settings["intro"], "introduction", 300)
    phone = settings["phone"]
    if not isinstance(phone, str) or not PHONE.fullmatch(phone):
        raise MattressError("Confirmed contact number is required")
    zalo = settings["zalo_phone"]
    if zalo is not None and (not isinstance(zalo, str) or not PHONE.fullmatch(zalo)):
        raise MattressError("Invalid verified Zalo contact number")
    products = settings["products"]
    if not isinstance(products, list) or len(products) > 12:
        raise MattressError("Expected at most 12 confirmed product descriptions")
    verified = []
    for p in products:
        if not isinstance(p, dict) or set(p) != {"name", "description"}:
            raise MattressError("Product must contain verified name and description")
        verified.append({"name": _text(p["name"], "product", 100),
                         "description": _text(p["description"], "description", 280)})
    return {"brand": brand, "phone": phone, "zalo_phone": zalo,
            "intro": intro, "products": verified}


def render(settings):
    cfg = validate(settings)
    esc = lambda value: html.escape(value, quote=True)
    cards = "".join(
        '<article class="product"><span class="eyebrow">TÌM HIỂU SẢN PHẨM</span>'
        f'<h3>{esc(p["name"])}</h3><p>{esc(p["description"])}</p>'
        '<p class="note">Giá, tình trạng hàng và giao hàng: xác nhận khi tư vấn.</p>'
        '</article>' for p in cfg["products"])
    if not cards:
        cards = ('<article class="product empty"><h3>Đang cập nhật sản phẩm</h3>'
                 '<p>Hãy liên hệ để được tư vấn mẫu nệm, kích thước và mức giá '
                 'đã được người bán xác nhận.</p></article>')
    zalo_link = ""
    if cfg["zalo_phone"]:
        zalo_link = (
            f'<a class="button secondary" href="https://zalo.me/'
            f'{esc(cfg["zalo_phone"].removeprefix("+"))}" '
            'rel="noopener noreferrer" target="_blank">Nhắn tin Zalo</a>')
    phone_href = esc(cfg["phone"].replace(" ", ""))
    result = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{esc(cfg["brand"])} · Tư vấn chọn nệm</title>
<meta name="description" content="{esc(cfg["intro"])}">
<style>
:root{{--ink:#202d3b;--muted:#4b5a67;--accent:#27694d;--cream:#f7f6f1;--white:#fff}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--cream);color:var(--ink);font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif}}
a{{color:inherit}}
.shell{{width:min(1120px,calc(100% - 36px));margin:auto}}
header{{background:#fff;border-bottom:1px solid #e5e7e2;padding:19px 0}}
header .shell{{display:flex;align-items:center;justify-content:space-between;gap:18px}}
.brand{{font-size:19px;font-weight:800;letter-spacing:-.025em}}
.top-call{{font-size:14px;font-weight:700;color:#246046}}
.hero{{padding:85px 0 72px;background:linear-gradient(130deg,#eef5eb,#f9f5ec 65%,#f1eade)}}
.hero-grid{{display:grid;grid-template-columns:1.25fr .75fr;gap:45px;align-items:center}}
.eyebrow{{font-weight:800;letter-spacing:.12em;font-size:12px;color:#27694d}}
h1{{font-size:clamp(36px,5vw,63px);line-height:1.09;letter-spacing:-.045em;margin:17px 0 23px}}
.intro{{font-size:19px;color:#44515a;max-width:650px}}
.actions{{display:flex;flex-wrap:wrap;gap:11px;margin-top:30px}}
.button{{padding:13px 20px;border-radius:12px;font-weight:750;text-decoration:none;display:inline-block}}
.primary{{background:#246046;color:#fff}}.secondary{{background:#fff;border:2px solid #246046;color:#205b41}}
.hero-aside{{background:#fff;border:1px solid #dfe7dc;padding:30px;border-radius:25px;box-shadow:0 14px 45px #183c2910}}
.hero-aside strong{{font-size:20px}}.hero-aside li{{margin:14px 0;color:#46565d}}
section.products{{padding:72px 0 80px}}h2{{font-size:clamp(27px,3vw,39px);line-height:1.25;margin:12px 0 14px}}
.lead{{max-width:700px;color:var(--muted);margin:0 0 31px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:17px}}
.product{{background:#fff;border:1px solid #e2e7df;border-radius:19px;padding:25px}}
.product h3{{margin:11px 0 7px;font-size:21px}}.product p{{color:var(--muted)}}
.product .note{{font-size:13px;border-top:1px solid #ebeee9;padding-top:13px}}
.next{{background:#eaf1e7;padding:55px 0}}
.steps{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
.step{{padding:22px;border-left:3px solid #27694d;background:#fff;border-radius:8px}}
.step strong{{display:block;margin-bottom:8px}}
footer{{padding:30px 0;color:var(--muted);font-size:14px}}
@media(max-width:740px){{.hero-grid,.steps{{grid-template-columns:1fr}}.hero{{padding:45px 0}}
header .shell{{flex-wrap:wrap}}.hero-aside{{padding:22px}}}}
@media(prefers-reduced-motion:reduce){{*,*:before,*:after{{scroll-behavior:auto!important}}}}
</style>
</head>
<body>
{MARKER}
<header><div class="shell">
<span class="brand">{esc(cfg["brand"])}</span>
<a class="top-call" href="tel:{phone_href}">Gọi người tư vấn</a>
</div></header>
<main>
<section class="hero"><div class="shell hero-grid">
<div><span class="eyebrow">TƯ VẤN NỆM THEO NHU CẦU</span>
<h1>Chọn nệm phù hợp, có người tư vấn trực tiếp.</h1>
<p class="intro">{esc(cfg["intro"])}</p>
<div class="actions"><a class="button primary" href="tel:{phone_href}">Gọi tư vấn: {esc(cfg["phone"])}</a>
{zalo_link}</div></div>
<aside class="hero-aside"><strong>Quy trình rõ ràng</strong>
<ul><li>Trao đổi kích thước, nhu cầu sử dụng và mẫu nệm.</li>
<li>Người bán xác nhận giá và tình trạng sản phẩm.</li>
<li>Kiểm tra phạm vi, phí và thời gian giao hàng với đơn vị vận chuyển.</li>
<li>Chỉ xác nhận đơn sau khi hai bên thống nhất.</li></ul></aside>
</div></section>
<section class="products"><div class="shell">
<span class="eyebrow">DANH MỤC THAM KHẢO</span>
<h2>Mẫu nệm được người bán cung cấp</h2>
<p class="lead">Danh sách dưới đây chỉ gồm thông tin đã nhập và xác nhận.
Không tự cam kết giá, tồn kho, bảo hành hoặc khu vực giao hàng.</p>
<div class="cards">{cards}</div>
</div></section>
<section class="next"><div class="shell">
<h2>Đặt câu hỏi, chưa cần đặt cọc.</h2>
<p class="lead">Chúng tôi chưa hỗ trợ đặt hàng và thanh toán trực tuyến.
Hãy liên hệ trực tiếp; người bán sẽ báo giá và xác minh vận chuyển trước khi chốt.</p>
<div class="steps"><div class="step"><strong>01 · Trao đổi</strong>Cho biết nhu cầu, kích thước và khu vực.</div>
<div class="step"><strong>02 · Báo giá</strong>Xác minh mẫu, giá và phí giao hàng.</div>
<div class="step"><strong>03 · Xác nhận</strong>Người bán liên hệ lại để thống nhất đơn.</div></div>
</div></section>
</main>
<footer><div class="shell">{esc(cfg["brand"])} · Website giới thiệu &amp; tư vấn.
Không có biểu mẫu thu thập dữ liệu; thông tin khách được trao đổi trực tiếp khi khách chủ động liên hệ.</div></footer>
</body></html>
"""
    if len(result.encode("utf-8")) > MAX_SITE_BYTES:
        raise MattressError("Website exceeds bounded output")
    return result


def export(settings, *, confirmed=False, output_dir=None,
           replace_sha=None):
    if confirmed is not True:
        raise PermissionError("Owner must approve static site export")
    source = render(settings)
    directory = Path(output_dir) if output_dir is not None else OUT
    # Fixed local path unless tests supply an explicit isolated output.
    ensure_local_root(directory)
    dest = directory / "index.html"
    ensure_local_root(dest)
    if dest.exists():
        old = dest.read_bytes()
        if (MARKER.encode() not in old or not isinstance(replace_sha, str)
                or hashlib.sha256(old).hexdigest() != replace_sha):
            raise MattressError("Existing website requires exact owner-reviewed SHA")
    else:
        if replace_sha is not None:
            raise MattressError("Replacement SHA supplied without an existing site")
    directory.mkdir(parents=True, exist_ok=True)
    temp = directory / ("." + os.urandom(8).hex() + ".tmp")
    try:
        with temp.open("xb") as file:
            file.write(source.encode("utf-8"))
        os.replace(temp, dest)
    finally:
        temp.unlink(missing_ok=True)
    return {"status": "LOCAL_SITE_EXPORTED_NOT_PUBLISHED",
            "relative_path": dest.name,
            "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "bytes": len(source.encode("utf-8")),
            "public_url_verified": False,
            "public_form_connected": False}
