"""Read-only, bounded Tilda product gallery discovery for Instagram previews.

The legacy posts.json is not modified. Remote media is accepted only from Tilda CDN.
A page with no confirmed gallery does not qualify as a multi-photo post.
"""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, unquote

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
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.images = []
        self._depth = 0
        self._product_depth = 0
        self._gallery_depth = 0
        self._script = False
        self._jsonld = []
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._script = True
            self._buffer = []
        if tag == "meta" and attrs.get("property") == "og:image":
            self._add(attrs.get("content"))
        classes = attrs.get("class", "")
        # Tilda store product detail and its slider are the only supported DOM sources.
        if tag == "div" and ("t-store__prod" in classes or "js-store-prod" in classes):
            self._product_depth += 1
        if tag == "div" and ("t-slds__item" in classes or "t-store__prod-popup__slider" in classes):
            self._gallery_depth += 1
        if tag in ("img", "div", "a") and (self._product_depth or self._gallery_depth):
            for key in ("data-original", "data-img-zoom-url", "data-img-zoom", "data-src", "src", "data-original-image"):
                self._add(attrs.get(key))

    def handle_data(self, data):
        if self._script:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script:
            self._script = False
            try:
                raw = json.loads("".join(self._buffer))
                self._jsonld.append(raw)
            except (ValueError, TypeError):
                pass
            self._buffer = []

    def _add(self, url):
        if not isinstance(url, str):
            return
        url = unquote(url.replace("&amp;", "&"))
        safe = approved_image_url(url)
        if safe and safe not in self.images:
            self.images.append(safe)


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
    confirmed = schema or parser.images
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
    url = approved_product_url(post.get("public_link") or post.get("link"))
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; IvoryArtGallery/1.0)"})
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                raise ValueError("Product page too large")
        return extract_gallery(response.text, primary), "product_page"
    except (httpx.HTTPError, ValueError):
        return [primary], "primary_only"


def format_for_gallery(images):
    if len(images) >= 2:
        return "carousel"
    return "post"
