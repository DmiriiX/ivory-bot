"""Read-only, bounded Tilda product gallery discovery for Instagram previews.

The legacy posts.json is not modified. Remote media is accepted only from Tilda CDN.
A page with no confirmed gallery does not qualify as a multi-photo post.
"""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote

import httpx

PRODUCT_HOSTS = {"ivory-art.com", "www.ivory-art.com"}
IMAGE_HOSTS = {"static.tildacdn.com", "optim.tildacdn.com"}
MAX_IMAGES = 8


def approved_product_url(url):
    parsed = urlsplit(url or "")
    if (parsed.scheme != "https" or parsed.hostname not in PRODUCT_HOSTS
            or not re.match(r"^/(?:shop/)?tproduct/[-\w/]+$", parsed.path)):
        raise ValueError("Not an Ivory Art product page")
    return url


def approved_image_url(url):
    parsed = urlsplit(url or "")
    if parsed.scheme != "https" or parsed.hostname not in IMAGE_HOSTS:
        return None
    if not parsed.path or len(url) > 1200:
        return None
    return url.split("#", 1)[0]


class GalleryParser(HTMLParser):
    """Collect JSON-LD only; DOM images require a scoped selector."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._script = False
        self._jsonld = []
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._script = True
            self._buffer = []

    def handle_data(self, data):
        if self._script:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script:
            self._script = False
            try:
                self._jsonld.append(json.loads("".join(self._buffer)))
            except (ValueError, TypeError):
                pass
            self._buffer = []


def product_schema_images(schemas):
    out = []
    def walk(node):
        if isinstance(node, list):
            for entry in node: walk(entry)
        if not isinstance(node, dict):
            return
        t = node.get("@type", "")
        if isinstance(t, list): t = " ".join(t)
        if "Product" in str(t):
            imgs = node.get("image", [])
            if isinstance(imgs, (str, dict)): imgs = [imgs]
            for item in imgs:
                value = item if isinstance(item, str) else item.get("url") or item.get("contentUrl") if isinstance(item, dict) else None
                safe = approved_image_url(value)
                if safe and safe not in out: out.append(safe)
        for key in ("@graph", "mainEntity"):
            if key in node: walk(node[key])
    walk(schemas)
    return out


def extract_gallery(html_text, primary):
    parser = GalleryParser()
    parser.feed(html_text[:2_000_000])
    schema = product_schema_images(parser._jsonld)
    confirmed = list(schema)
    # Only actual product-gallery nodes, never unrelated page artwork.
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_text[:2_000_000], "html.parser")
    for element in soup.select(".t-store__prod-popup__slider img, .t-store__prod-popup__slider [data-original], .t-store__prod__slider img, .t-store__prod__slider [data-original]"):
        for key in ("data-original", "data-img-zoom-url", "data-src", "src"):
            value = approved_image_url(element.get(key))
            if value and value not in confirmed:
                confirmed.append(value)
    ordered = [primary] if approved_image_url(primary) else []
    for item in confirmed:
        if item not in ordered:
            ordered.append(item)
    return ordered[:MAX_IMAGES]


async def discover_gallery(post):
    primary = approved_image_url(post.get("photo"))
    if not primary:
        raise ValueError("Invalid primary image")
    # Explicitly curated galleries take precedence over brittle page scraping.
    manual = [approved_image_url(x) for x in post.get("gallery", []) if isinstance(x, str)]
    manual = [x for x in manual if x]
    if manual:
        return list(dict.fromkeys([primary] + manual))[:MAX_IMAGES], "catalog"
    try:
        catalog_images = await catalog_gallery(post)
        if catalog_images:
            return list(dict.fromkeys([primary] + catalog_images))[:MAX_IMAGES], "tilda_catalog"
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        if __import__("os").environ.get("IVORY_MEDIA_DEBUG") == "1":
            print("Tilda catalog fallback:", type(exc).__name__)
    candidates = []
    for key in ("public_link", "link"):
        try:
            url = approved_product_url(post.get(key))
            if url not in candidates:
                candidates.append(url)
        except ValueError:
            pass
    for url in candidates:
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
                response = await client.get(
                    url, headers={"User-Agent": "Mozilla/5.0 (compatible; IvoryArtGallery/1.0)"})
                if response.status_code in (301, 302, 307, 308):
                    from urllib.parse import urljoin
                    redirected = urljoin(url, response.headers.get("location", ""))
                    approved_product_url(redirected)
                    response = await client.get(redirected)
                if __import__("os").environ.get("IVORY_MEDIA_DEBUG") == "1":
                    text = response.text[:2_000_000]
                    print("Tilda gallery:", response.status_code, "bytes", len(response.content),
                          "gallery-marker", text.count("t-store__prod-popup__slider"),
                          "schema", text.count("application/ld+json"))
                response.raise_for_status()
                if len(response.content) > 2_000_000:
                    raise ValueError("Product page too large")
            images = extract_gallery(response.text, primary)
            if len(images) > 1:
                return images, "product_page"
        except (httpx.HTTPError, ValueError):
            continue
    return [primary], "primary_only"


# Verified from the published Ivory Art homepage store widget (2026-11-09).
STORE_PART_UID = "321076440131"
STORE_REC_ID = "467407679"
CATALOG_ENDPOINT = "https://store.tildaapi.com/api/getproductslist/"
_CATALOG_CACHE = {"at": 0.0, "galleries": {}}


def product_uid(post):
    for key in ("public_link", "link"):
        m = re.search(r"/tproduct/\d+-(\d{9,15})-", post.get(key) or "")
        if m:
            return m.group(1)
    return None


async def load_catalog_galleries():
    """Read Tilda public store catalog, bounded pagination and 15-min cache."""
    import time
    if time.monotonic() - _CATALOG_CACHE["at"] < 900:
        return _CATALOG_CACHE["galleries"]
    galleries = {}
    async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
        for page in range(1, 16):
            response = await client.get(CATALOG_ENDPOINT, params={
                "storepartuid": STORE_PART_UID,
                "recid": STORE_REC_ID,
                "getparts": "false",
                "getoptions": "true",
                "size": "100",
                "slice": str(page),
                "sort[created]": "desc",
            }, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            if len(response.content) > 4_000_000:
                raise ValueError("Catalog response too large")
            result = response.json()
            for product in result.get("products") or []:
                uid = str(product.get("uid") or "")
                try:
                    raw = product.get("gallery") or "[]"
                    images = json.loads(raw) if isinstance(raw, str) else raw
                except (ValueError, TypeError):
                    images = []
                gallery = []
                for item in images if isinstance(images, list) else []:
                    url = item.get("img") if isinstance(item, dict) else item
                    approved = approved_image_url(url)
                    if approved and approved not in gallery:
                        gallery.append(approved)
                if uid and gallery:
                    galleries[uid] = gallery[:MAX_IMAGES]
            if not result.get("nextslice"):
                break
    if __import__("os").environ.get("IVORY_MEDIA_DEBUG") == "1":
        print("Tilda catalog: entries", len(galleries),
              "multi-photo", sum(len(v) > 1 for v in galleries.values()))
    if galleries:
        _CATALOG_CACHE.update({"at": time.monotonic(), "galleries": galleries})
    return galleries


async def catalog_gallery(post):
    uid = product_uid(post)
    if not uid:
        return []
    return (await load_catalog_galleries()).get(uid, [])


def format_for_gallery(images):
    if len(images) >= 2:
        return "carousel"
    return "post"
