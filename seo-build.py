#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seo-build.py — Fresh Straws SPA static-page generator.

Vì site là SPA 1 file (index.html) chạy trên GitHub Pages, các URL sạch vốn rơi
vào 404.html và trả HTTP 404 (Google không index). Script này sinh một file HTML
tĩnh THẬT cho mỗi route (=> trả 200), nhúng sẵn <title>, meta description,
canonical, Open Graph và JSON-LD đúng cho từng trang; đồng thời tạo lại sitemap.xml.

QUY TRÌNH DEPLOY (thay cho "cp index.html 404.html"):
  1) Sửa nội dung trong index.html (bản nguồn duy nhất).
  2) Chạy:  python3 seo-build.py
  3) git add -A && git commit && git push origin main

Script đọc index.html làm nguồn, tự strip các khối JSON-LD nó đã chèn trước đó
(idempotent) rồi sinh lại toàn bộ.
"""
import re, os, html as htmllib, json, datetime, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "index.html")
ORIGIN = "https://freshstraws.vn"
LOGO = ORIGIN + "/images/logo-fresh-straws.png"
DEFAULT_IMG = ORIGIN + "/images/banner-3.jpg"
TODAY = "2026-08-05"

ARTICLE_DATES = {
    "/tin-tuc/tai-sao-chon-ong-hut-co-bang": "2026-06-19",
    "/tin-tuc/phan-biet-trai-cay-say-deo-gion-thang-hoa": "2026-07-28",
    "/tin-tuc/huong-dan-dat-hang-oem-odm-san-pham-xanh": "2026-08-01",
    "/tin-tuc/xu-huong-tieu-dung-xanh-va-co-hoi-xuat-khau-2026": "2026-08-04",
}

def attr(s):
    """text an toàn cho content=\"...\" (escape & < > ")"""
    s = htmllib.unescape(s or "").strip()
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))

def ctext(s):
    """text cho <title> (không cần escape dấu ")"""
    s = htmllib.unescape(s or "").strip()
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def plain(s):
    """text thuần cho JSON-LD"""
    return re.sub(r"\s+", " ", htmllib.unescape(s or "")).strip()

# ---------- Đọc nguồn + trích dữ liệu route ----------
html = open(SRC, encoding="utf-8").read()

# strip các khối JSON-LD do script chèn trước đó (idempotent)
html = re.sub(r"\n?\s*<!--SEO-JSONLD-->.*?<!--/SEO-JSONLD-->", "", html, flags=re.S)

# titles map trong JS
m = re.search(r"const titles = (\{.*?\});", html, re.S)
titles = json.loads(m.group(1)) if m else {}

# search-data (fallback mô tả)
m = re.search(r'id="search-data">(\[.*?\])</script>', html, re.S)
searchdata = json.loads(m.group(1)) if m else []
sd_desc = {it["href"]: it.get("description", "") for it in searchdata}

# tách từng spa-page
blocks = html.split('<div class="spa-page"')
routes = []          # (path, title, desc, kind, img)
seen = set()
for b in blocks[1:]:
    mp = re.search(r'data-path="([^"]+)"', b[:200])
    if not mp:
        continue
    path = mp.group(1)
    if path in seen:
        continue
    seen.add(path)
    seg = b[:6000]
    mh = re.search(r"<h1>(.*?)</h1>", seg, re.S)
    h1 = mh.group(1).strip() if mh else ""
    # mô tả: hero <p> đầu tiên trước </section>, fallback search-data
    hero = seg.split("</section>", 1)[0]
    mpp = re.search(r"<p>(.*?)</p>", hero, re.S)
    desc = mpp.group(1).strip() if mpp else ""
    if not desc:
        desc = sd_desc.get(path, "")
    is_product = "product-detail-hero" in seg
    is_article = path.startswith("/tin-tuc/") and path != "/tin-tuc"
    # ảnh: product-detail-image cho trang sản phẩm
    img = DEFAULT_IMG
    mi = re.search(r'<div class="product-detail-image"><img src="([^"]+)"', seg)
    if mi:
        img = ORIGIN + mi.group(1)
    kind = "article" if is_article else ("product" if is_product else "page")
    routes.append({"path": path, "h1": h1, "desc": desc, "kind": kind, "img": img})

# ---------- JSON-LD sitewide (Organization + WebSite) ----------
org = {
    "@context": "https://schema.org", "@type": "Organization",
    "name": "Công ty Cổ phần Fresh Straws Việt Nam",
    "alternateName": "Fresh Straws Việt Nam",
    "url": ORIGIN + "/", "logo": LOGO,
    "description": "Nhà sản xuất và xuất khẩu ống hút cỏ bàng, trái cây sấy, trái cây đóng lon, đông lạnh/IQF, nước ép, sữa chua sấy thăng hoa và purée. Nhận OEM/ODM.",
    "address": {"@type": "PostalAddress", "streetAddress": "743 Hồng Bàng, Phường Bình Tây",
                "addressLocality": "Hồ Chí Minh", "addressCountry": "VN"},
    "contactPoint": {"@type": "ContactPoint", "telephone": "+84-708-735-327",
                     "email": "contact@freshstraws.com", "contactType": "sales",
                     "areaServed": "VN", "availableLanguage": ["vi", "en"]},
}
website = {"@context": "https://schema.org", "@type": "WebSite",
           "name": "Fresh Straws Việt Nam", "url": ORIGIN + "/"}

def ld_block(objs):
    parts = ["<!--SEO-JSONLD-->"]
    for o in objs:
        parts.append('<script type="application/ld+json">' +
                     json.dumps(o, ensure_ascii=False) + "</script>")
    parts.append("<!--/SEO-JSONLD-->")
    return "\n    ".join(parts)

# chèn sitewide vào <head> của template (áp dụng cho mọi file)
template = html.replace("</head>", "    " + ld_block([org, website]) + "\n  </head>", 1)

route_paths = {r["path"] for r in routes}
name_of = {r["path"]: plain(r["h1"]) or plain(titles.get(r["path"], "")).split(" | ")[0]
           for r in routes}
name_of["/"] = "Trang chủ"

def breadcrumb(path):
    items, acc = [], ""
    crumbs = ["/"]
    for part in [p for p in path.split("/") if p]:
        acc += "/" + part
        crumbs.append(acc)
    out = []
    pos = 1
    for c in crumbs:
        if c != "/" and c not in route_paths:
            continue
        nm = name_of.get(c, c)
        url = ORIGIN + "/" if c == "/" else ORIGIN + c + "/"
        out.append({"@type": "ListItem", "position": pos, "name": nm, "item": url})
        pos += 1
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": out}

def canon(path):
    return ORIGIN + "/" if path == "/" else ORIGIN + path + "/"

def set_prop(h, prop, val):
    return re.sub(r'(<meta property="' + re.escape(prop) + r'" content=")[^"]*(">)',
                  lambda mm: mm.group(1) + val + mm.group(2), h, count=1)

def set_name(h, name, val):
    return re.sub(r'(<meta name="' + re.escape(name) + r'" content=")[^"]*(">)',
                  lambda mm: mm.group(1) + val + mm.group(2), h, count=1)

# ---------- Sinh file cho từng route ----------
written = 0
for r in routes:
    path, kind = r["path"], r["kind"]
    title = titles.get(path) or ((plain(r["h1"]) + " | Fresh Straws Việt Nam") if r["h1"] else
                                 "Fresh Straws Việt Nam")
    desc = plain(r["desc"])
    if not desc:
        desc = "Fresh Straws Việt Nam — nhà sản xuất và xuất khẩu nông sản chế biến và sản phẩm xanh. Nhận OEM/ODM."
    url = canon(path)
    page = template
    page = re.sub(r"<title>.*?</title>", lambda mm: "<title>" + ctext(title) + "</title>",
                  page, count=1, flags=re.S)
    page = set_name(page, "description", attr(desc))
    page = re.sub(r'(<link rel="canonical" href=")[^"]*(">)',
                  lambda mm: mm.group(1) + url + mm.group(2), page, count=1)
    page = set_prop(page, "og:title", attr(title))
    page = set_prop(page, "og:description", attr(desc))
    page = set_prop(page, "og:url", url)
    page = set_prop(page, "og:image", r["img"])
    page = set_name(page, "twitter:title", attr(title))
    page = set_name(page, "twitter:description", attr(desc))
    page = set_name(page, "twitter:image", r["img"])
    # og:type
    page = set_prop(page, "og:type", "article" if kind == "article" else "website")

    # JSON-LD per-page
    objs = []
    if path != "/":
        objs.append(breadcrumb(path))
    if kind == "product":
        objs.append({"@context": "https://schema.org", "@type": "Product",
                     "name": plain(r["h1"]), "description": desc, "image": r["img"],
                     "brand": {"@type": "Brand", "name": "Fresh Straws"}, "url": url})
    elif kind == "article":
        d = ARTICLE_DATES.get(path, TODAY)
        objs.append({"@context": "https://schema.org", "@type": "Article",
                     "headline": plain(r["h1"]), "description": desc, "image": r["img"],
                     "datePublished": d, "dateModified": d,
                     "author": {"@type": "Organization", "name": "Fresh Straws Việt Nam"},
                     "publisher": {"@type": "Organization", "name": "Fresh Straws Việt Nam",
                                   "logo": {"@type": "ImageObject", "url": LOGO}},
                     "mainEntityOfPage": url})
    if objs:
        page = page.replace("</head>", "    " + ld_block(objs) + "\n  </head>", 1)

    # ghi file
    if path == "/":
        outpath = os.path.join(ROOT, "index.html")
    else:
        d = os.path.join(ROOT, path.strip("/"))
        os.makedirs(d, exist_ok=True)
        outpath = os.path.join(d, "index.html")
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(page)
    written += 1

# 404.html = bản homepage (fallback SPA cho URL lạ)
shutil.copyfile(os.path.join(ROOT, "index.html"), os.path.join(ROOT, "404.html"))

# ---------- Sitemap ----------
def priority(r):
    if r["path"] == "/": return "1.0"
    if r["kind"] in ("product", "article"): return "0.6"
    return "0.8"
def lastmod(r):
    return ARTICLE_DATES.get(r["path"], TODAY)
def freq(r):
    return "monthly" if r["kind"] in ("product",) else "weekly"

urls = []
for r in sorted(routes, key=lambda x: (x["path"] != "/", x["path"])):
    urls.append(
        f'  <url><loc>{canon(r["path"])}</loc><lastmod>{lastmod(r)}</lastmod>'
        f'<changefreq>{freq(r)}</changefreq><priority>{priority(r)}</priority></url>')
sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemap.org/schemas/sitemap/0.9">\n'
           + "\n".join(urls) + "\n</urlset>\n")
# namespace chuẩn:
sitemap = sitemap.replace("http://www.sitemap.org", "http://www.sitemaps.org")
with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
    f.write(sitemap)

print(f"Đã sinh {written} trang tĩnh + 404.html + sitemap.xml ({len(urls)} URL).")
