"""Crawl the current All Saints' Squarespace site into a raw migration dataset.

Pragmatic by design:
- sitemap.xml is the URL source of truth (plus homepage navigation).
- Standalone pages, collection index pages, and small collections are fetched.
- High-volume dated collections (newsletter items, youth calendar, newsletter
  archive) are inventoried from sitemap metadata only, plus a small recent sample.
- Sermons are read from the Squarespace collection JSON (?format=json), which
  exposes title, author (preacher), publish date, and the MP3 URL.

Outputs (relative to migration/):
  source/manifests/sitemap-urls.csv     every sitemap URL + lastmod
  source/manifests/navigation.json      header navigation as published
  source/manifests/sermons.json         structured sermon archive
  source/metadata/crawl.json            per-page extracted metadata
  source/pages/<slug>.md                readable body text per fetched page

Usage:
  python migration/scripts/crawl_site.py [--delay 0.4] [--newsletter-sample 25]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.allsaintswoodbridge.org"
HOST = "www.allsaintswoodbridge.org"
MIGRATION = Path(__file__).resolve().parents[1]
SOURCE = MIGRATION / "source"
UA = "ASC-Migration-Audit/1.0 (+parish website rebuild; contact office)"

# Collections too large (and too dated) to fetch item-by-item.
SITEMAP_ONLY = {"the-newsletter", "asy-calendar", "newsletter-archive"}
SCRIPTURE_RE = re.compile(
    r"\b((?:[1-3]\s)?[A-Z][a-z]+(?:\s(?:of\s)?[A-Z][a-z]+)?\s\d{1,3}:\d{1,3}(?:[-–]\d{1,3}(?::\d{1,3})?)?(?:,\s?\d{1,3}(?:[-–]\d{1,3})?)*)"
)
BOOKS = {
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua", "Judges", "Ruth",
    "Samuel", "Kings", "Chronicles", "Ezra", "Nehemiah", "Esther", "Job", "Psalm", "Psalms",
    "Proverbs", "Ecclesiastes", "Song", "Isaiah", "Jeremiah", "Lamentations", "Ezekiel", "Daniel",
    "Hosea", "Joel", "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
    "Haggai", "Zechariah", "Malachi", "Matthew", "Mark", "Luke", "John", "Acts", "Romans",
    "Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians", "Thessalonians",
    "Timothy", "Titus", "Philemon", "Hebrews", "James", "Peter", "Jude", "Revelation",
}

session = requests.Session()
session.headers["User-Agent"] = UA


def get(url: str, delay: float) -> requests.Response | None:
    time.sleep(delay)
    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as exc:
        print(f"  ! {url}: {exc}", file=sys.stderr)
        return None
    return resp


def slug_for(path: str) -> str:
    path = path.strip("/") or "home"
    return re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")[:120]


def scripture_refs(text: str) -> list[str]:
    refs = []
    for match in SCRIPTURE_RE.findall(text):
        words = match.split()
        book_word = words[1] if words[0].isdigit() else words[0]
        if book_word in BOOKS and match not in refs:
            refs.append(match.replace("–", "-"))
    return refs


def read_sitemap(delay: float) -> list[dict]:
    resp = get(f"{BASE}/sitemap.xml", delay)
    resp.raise_for_status()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    rows = []
    for url in ET.fromstring(resp.content).findall("s:url", ns):
        loc = url.findtext("s:loc", default="", namespaces=ns).strip()
        rows.append({"url": loc, "lastmod": url.findtext("s:lastmod", default="", namespaces=ns)})
    return rows


def extract_navigation(soup: BeautifulSoup) -> list[dict]:
    """Return [{label, href, children:[{label, href}]}] from the (Squarespace 7.0) site navigation."""
    nav = []
    root = soup.select_one("#mobileNavigation") or soup.select_one("nav")
    if root is None:
        return nav
    for item in root.find_all("div", recursive=False):
        toggle = item.select_one(".folder-toggle")
        if toggle:
            children = [
                {"label": a.get_text(" ", strip=True), "href": a.get("href", "")}
                for a in item.select(".subnav a")
            ]
            nav.append({"label": toggle.get_text(" ", strip=True), "href": toggle.get("data-href", ""), "children": children})
        else:
            a = item.find("a")
            if a:
                nav.append({"label": a.get_text(" ", strip=True), "href": a.get("href", ""), "children": []})
    return nav


def extract_page(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    meta = lambda **kw: (soup.find("meta", attrs=kw) or {}).get("content", "")  # noqa: E731
    main = soup.find("main") or soup.body or soup
    for junk in main.select("script, style, noscript, nav, .sqs-announcement-bar"):
        junk.decompose()

    headings = [f"{h.name}: {h.get_text(' ', strip=True)}" for h in main.find_all(["h1", "h2", "h3", "h4"]) if h.get_text(strip=True)]
    images, files, video, audio, internal, external = [], [], [], [], set(), set()
    for img in main.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if src.startswith(("http", "//")):
            images.append({"src": src.split("?")[0], "alt": img.get("alt", "")})
    for a in main.find_all("a", href=True):
        href = urljoin(url, a["href"])
        parsed = urlparse(href)
        if re.search(r"\.(pdf|docx?|xlsx?|pptx?)($|\?)", parsed.path, re.I) or "/s/" in parsed.path:
            files.append(href)
        elif parsed.netloc in (HOST, "allsaintswoodbridge.org"):
            internal.add(parsed.path.rstrip("/") or "/")
        elif parsed.scheme in ("http", "https"):
            external.add(href)
    raw = str(main)
    for vid in re.findall(r"(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/)([\w-]{11})", raw):
        if vid not in video:
            video.append(vid)
    for mp3 in re.findall(r"https?://[^\"'\s]+\.mp3", raw):
        if mp3 not in audio:
            audio.append(mp3)

    text = main.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    title = (soup.title.string or "").strip() if soup.title else ""
    return {
        "source_url": url,
        "page_title": title.replace(" — All Saints' Church", "").replace(" — All Saints' Church", ""),
        "seo_title": meta(property="og:title") or title,
        "meta_description": meta(name="description"),
        "canonical_url": (soup.find("link", rel="canonical") or {}).get("href", ""),
        "publish_date": meta(itemprop="datePublished") or meta(property="article:published_time"),
        "author": meta(itemprop="author") or meta(name="author"),
        "heading_structure": headings,
        "primary_images": images[:12],
        "downloadable_files": sorted(set(files)),
        "embedded_video": video,
        "embedded_audio": audio,
        "internal_links": sorted(internal),
        "external_links": sorted(external),
        "word_count": len(text.split()),
        "body_text": text,
    }


def crawl_sermons(delay: float) -> list[dict]:
    sermons, url = [], f"{BASE}/latest-sermons?format=json"
    while url:
        resp = get(url, delay)
        if resp is None or resp.status_code != 200:
            break
        data = resp.json()
        for it in data.get("items", []):
            body_html = it.get("body", "") or ""
            body_text = BeautifulSoup(body_html, "html.parser").get_text("\n", strip=True)
            blob = body_html + json.dumps(it.get("structuredContent", {}))
            mp3 = re.findall(r"https?://[^\"'\s]+\.mp3", blob)
            published = datetime.fromtimestamp(int(it["publishOn"]) / 1000, tz=timezone.utc)
            sermons.append({
                "source_url": BASE + it.get("fullUrl", ""),
                "title": it.get("title", ""),
                "preacher": (it.get("author") or {}).get("displayName", ""),
                "publish_on": published.isoformat(),
                "sermon_date": published.astimezone().date().isoformat(),
                "scripture_references": scripture_refs(body_text),
                "audio_url": mp3[0] if mp3 else "",
                "body_text": body_text,
            })
        page = data.get("pagination") or {}
        url = BASE + page["nextPageUrl"] + "&format=json" if page.get("nextPage") else None
    return sermons


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--delay", type=float, default=0.4)
    ap.add_argument("--newsletter-sample", type=int, default=25)
    args = ap.parse_args()

    for sub in ("pages", "metadata", "manifests"):
        (SOURCE / sub).mkdir(parents=True, exist_ok=True)

    print("sitemap...")
    sitemap = read_sitemap(args.delay)
    with (SOURCE / "manifests" / "sitemap-urls.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["url", "lastmod"])
        w.writeheader()
        w.writerows(sitemap)

    print("homepage + navigation...")
    home = get(BASE + "/", args.delay)
    nav = extract_navigation(BeautifulSoup(home.text, "html.parser"))
    (SOURCE / "manifests" / "navigation.json").write_text(json.dumps(nav, indent=2), encoding="utf-8")

    print("sermons (collection JSON)...")
    sermons = crawl_sermons(args.delay)
    (SOURCE / "manifests" / "sermons.json").write_text(json.dumps(sermons, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {len(sermons)} sermons")

    # Decide what to fetch.
    to_fetch: list[str] = []
    newsletter = sorted(
        (r for r in sitemap if urlparse(r["url"]).path.startswith("/the-newsletter/")),
        key=lambda r: r["lastmod"], reverse=True,
    )[: args.newsletter_sample]
    sample = {r["url"] for r in newsletter}
    for row in sitemap:
        parts = urlparse(row["url"]).path.strip("/").split("/")
        if len(parts) > 1 and parts[0] in SITEMAP_ONLY and row["url"] not in sample:
            continue
        to_fetch.append(row["url"])

    nav_hrefs = {c["href"] for n in nav for c in [n, *n["children"]] if c["href"].startswith("/")}
    for href in sorted(nav_hrefs):
        if BASE + href not in to_fetch:
            to_fetch.append(BASE + href)

    print(f"fetching {len(to_fetch)} pages...")
    records = []
    for i, url in enumerate(to_fetch, 1):
        resp = get(url, args.delay)
        status = resp.status_code if resp is not None else 0
        rec = {"source_url": url, "http_status": status, "final_url": resp.url if resp is not None else ""}
        if resp is not None and status == 200 and "text/html" in resp.headers.get("content-type", ""):
            rec.update(extract_page(url, resp.text))
            path = urlparse(url).path
            (SOURCE / "pages" / f"{slug_for(path)}.md").write_text(
                f"# {rec['page_title']}\n\nSource: {url}\n\n{rec['body_text']}\n", encoding="utf-8"
            )
        records.append(rec)
        if i % 25 == 0:
            print(f"  {i}/{len(to_fetch)}")

    (SOURCE / "metadata" / "crawl.json").write_text(
        json.dumps({"crawled_at": datetime.now(timezone.utc).isoformat(), "records": records}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"done: {len(records)} fetched, {len(sitemap)} in sitemap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
