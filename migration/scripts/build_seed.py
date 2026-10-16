"""Build WordPress seed data (Gutenberg block markup) from the live site.

Converts Squarespace content blocks into editable core blocks (heading,
paragraph, list, quote, image, buttons). Squarespace widgets that WordPress
handles differently (summary feeds, forms, newsletter, social, code embeds)
are dropped and listed in each page's `dropped` field for the migration report.

Writes:
  seed/migrated-pages.json   pages migrated from the live site (KEEP/IMPROVE)
  seed/sermons.json          the full live sermon archive (46 items)
  seed/news.json             a handful of current announcements as Posts

Usage: python migration/scripts/build_seed.py
"""
from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seed"
BASE = "https://www.allsaintswoodbridge.org"
UA = {"User-Agent": "ASC-Migration-Audit/1.0 (+parish website rebuild)"}

# new path -> (source path, title override or None)
PAGES = {
    "about/what-we-believe": ("/what-we-believe", "What We Believe"),
    "about/clergy-and-staff": ("/clergy-and-staff", "Clergy & Staff"),
    "about/history": ("/timeline", "Our History"),
    "about/jerusalem-cross": ("/jerusalem-cross", "The Jerusalem Cross"),
    "about/vestry": ("/our-vestry", "Our Vestry"),
    "about/safeguarding": ("/protecting-gods-children", "Safeguarding"),
    "worship/sunday-services": ("/sunday-services", "Sunday Services"),
    "worship/wednesday-eucharist": ("/wednesday-morning-eucharist", "Wednesday Eucharist"),
    "worship/baptism": ("/baptism", "Baptism"),
    "worship/music": ("/music", "Music"),
    "prayer": ("/prayer", "Prayer"),
    "ministries/children": ("/children", "Children"),
    "ministries/nursery": ("/nursery", "Nursery"),
    "ministries/youth": ("/youth", "Youth"),
    "ministries/adult-formation": ("/adult-discipleship", "Adult Formation"),
    "ministries/men": ("/men", "Men"),
    "ministries/women": ("/women", "Women"),
    "ministries/serve": ("/serve-in-the-community", "Serve in the Community"),
    "ministries/food-pantry": ("/monthly-food-giveaway", "Food Pantry"),
    "give": ("/giving", "Give"),
}

NEWS = [
    "festive-fall-potluck-october-18",
    "church-work-day-october-17",
    "october-adult-formation",
    "gardeners-and-budding-gardeners-needed",
    "mens-prayer-breakfast-october-17-9759y-kr385-8eec",
    "asc-bookshelf-spotlight-the-cost-of-discipleship",
    "a-pastoral-letter-from-bishop-chris-warner",
]

INLINE_OK = {"a", "strong", "em", "b", "i", "br", "sup", "sub"}
DROP_BLOCKS = {
    "summary-block": "news/summary feed (replaced by WordPress Latest Posts)",
    "form-block": "form (needs a WordPress form plugin)",
    "newsletter-block": "newsletter signup (connect email provider)",
    "socialaccountlinks-v2-block": "social links",
    "code-block": "custom code/embed",
    "embed-block": "embed",
    "calendar-block": "calendar",
    "search-block": "search",
}


def get(url: str) -> str:
    time.sleep(0.4)
    resp = requests.get(url, headers=UA, timeout=30)
    resp.raise_for_status()
    return resp.text


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def inline_html(node: Tag) -> str:
    """Inner HTML restricted to safe inline tags; links made absolute."""
    out = []
    for child in node.children:
        if isinstance(child, NavigableString):
            out.append(esc(str(child)))
        elif isinstance(child, Tag):
            inner = inline_html(child)
            name = {"b": "strong", "i": "em"}.get(child.name, child.name)
            if child.name == "br":
                out.append("<br>")
            elif child.name == "a" and child.get("href"):
                href = child["href"]
                if href.startswith("/"):
                    href = BASE + href
                out.append(f'<a href="{html.escape(href)}">{inner}</a>')
            elif name in INLINE_OK:
                out.append(f"<{name}>{inner}</{name}>")
            elif child.name in ("p", "div", "h3", "h4") and "".join(out).strip():
                out.append("<br>" + inner)  # keep block-level breaks inside list items
            else:
                out.append(inner)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def block(name: str, inner: str, attrs: dict | None = None) -> str:
    a = (" " + json.dumps(attrs, separators=(",", ":"))) if attrs else ""
    return f"<!-- wp:{name}{a} -->\n{inner}\n<!-- /wp:{name} -->"


def para(text: str) -> str:
    return block("paragraph", f"<p>{text}</p>")


def heading(text: str, level: int) -> str:
    level = min(max(level, 2), 4)
    attrs = None if level == 2 else {"level": level}
    return block("heading", f'<h{level} class="wp-block-heading">{text}</h{level}>', attrs)


def list_block(items: list[str], ordered: bool) -> str:
    inner = "".join(block("list-item", f"<li>{i}</li>") for i in items if i)
    tag = "ol" if ordered else "ul"
    return block("list", f'<{tag} class="wp-block-list">{inner}</{tag}>', {"ordered": True} if ordered else None)


def image(src: str, alt: str, caption: str = "") -> str:
    src = ("https:" + src) if src.startswith("//") else src
    src = src.split("?")[0] + "?format=1500w"
    cap = f'<figcaption class="wp-element-caption">{caption}</figcaption>' if caption else ""
    return block("image", f'<figure class="wp-block-image size-large"><img src="{html.escape(src)}" alt="{html.escape(alt)}"/>{cap}</figure>', {"sizeSlug": "large"})


def convert(container: Tag) -> tuple[list[str], list[str]]:
    blocks, dropped = [], []
    for sqs in container.select(".sqs-block"):
        classes = set(sqs.get("class", []))
        drop = next((reason for cls, reason in DROP_BLOCKS.items() if cls in classes), None)
        if drop:
            dropped.append(drop)
            continue
        if "image-block" in classes:
            img = sqs.find("img")
            if img and (img.get("data-src") or img.get("src")):
                parts = [inline_html(el) for el in sqs.select(".image-title, .image-subtitle, .image-caption") if el.get_text(strip=True)]
                caption = "<br>".join(dict.fromkeys(parts))
                caption_text = BeautifulSoup(caption, "html.parser").get_text(" ", strip=True)
                alt = img.get("alt", "") or re.sub(r"\s*Email$", "", caption_text)
                blocks.append(image(img.get("data-src") or img["src"], alt, caption))
            continue
        if "button-block" in classes:
            a = sqs.find("a")
            if a and a.get("href"):
                href = BASE + a["href"] if a["href"].startswith("/") else a["href"]
                btn = block("button", f'<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="{html.escape(href)}">{esc(a.get_text(" ", strip=True))}</a></div>')
                blocks.append(block("buttons", f'<div class="wp-block-buttons">{btn}</div>'))
            continue
        if "quote-block" in classes:
            q = sqs.find("blockquote")
            cite = sqs.find("figcaption")
            if q:
                text = inline_html(q).strip("“” ")
                c = f"<cite>{inline_html(cite).lstrip('— ')}</cite>" if cite else ""
                blocks.append(block("quote", f'<blockquote class="wp-block-quote">{para(text)}{c}</blockquote>'))
            continue
        content = sqs.select_one(".sqs-html-content") or sqs.select_one(".sqs-block-content")
        if not content:
            continue
        for el in content.find_all(["h1", "h2", "h3", "h4", "p", "ul", "ol", "blockquote"], recursive=True):
            if el.find_parent(["ul", "ol", "blockquote"]) and el.name not in ("ul", "ol"):
                continue
            if el.name in ("ul", "ol"):
                if el.find_parent(["ul", "ol"]):
                    continue
                blocks.append(list_block([inline_html(li) for li in el.find_all("li", recursive=False)], el.name == "ol"))
                continue
            text = inline_html(el)
            if not text or text in ("&nbsp;",):
                continue
            if el.name in ("h1", "h2", "h3", "h4"):
                blocks.append(heading(text, int(el.name[1]) + (1 if el.name == "h1" else 0)))
            elif el.name == "blockquote":
                blocks.append(block("quote", f'<blockquote class="wp-block-quote">{para(text)}</blockquote>'))
            else:
                blocks.append(para(text))
    return blocks, sorted(set(dropped))


def migrate_pages() -> list[dict]:
    pages = []
    for path, (source, title) in PAGES.items():
        soup = BeautifulSoup(get(BASE + source), "html.parser")
        main = soup.select_one("main#page") or soup.find("main") or soup
        blocks, dropped = convert(main)
        # The page title is rendered by the theme; drop a leading duplicate heading.
        if blocks and blocks[0].startswith("<!-- wp:heading") and title.lower().split()[0] in blocks[0].lower():
            blocks = blocks[1:]
        pages.append({"path": path, "title": title, "source_url": BASE + source, "content": "\n\n".join(blocks), "dropped": dropped})
        print(f"  {path}: {len(blocks)} blocks, dropped {dropped}")
    return pages


SERIES_RE = re.compile(r"^(?P<series>.+?)\s*[—–-]\s*Sermon\s+\w+$")


def sermons() -> list[dict]:
    raw = json.loads((ROOT / "migration/source/manifests/sermons.json").read_text(encoding="utf-8"))
    out = []
    for s in raw:
        lines = [l.strip() for l in s["body_text"].splitlines() if l.strip()]
        # Body: date, title, preacher, "Download", then optional "<ref> (ESV)" + verses.
        content = []
        if "Download" in lines:
            rest = lines[lines.index("Download") + 1:]
            passages: list[tuple[str, list[str]]] = []
            buf = ""
            for line in rest:
                if line.endswith("(ESV)"):
                    if passages and buf:
                        passages[-1][1].append(buf)
                    buf = ""
                    passages.append((line.replace("(ESV)", "").strip(), []))
                elif not passages:
                    continue
                elif re.fullmatch(r"\d{1,3}", line):
                    if buf:
                        passages[-1][1].append(buf)
                    buf = f"<sup>{line}</sup> "
                elif line.lower().startswith("scripture quotations"):
                    break
                else:
                    buf += esc(line) + " "
            if passages and buf:
                passages[-1][1].append(buf)
            if passages:
                content.append(heading("Scripture", 2))
                for ref, verses in passages:
                    quote = "".join(para(v.strip()) for v in verses)
                    content.append(block("quote", f'<blockquote class="wp-block-quote">{quote}<cite>{esc(ref)} (ESV)</cite></blockquote>'))
                content.append(block("paragraph", '<p class="has-small-font-size">Scripture quotations are from the ESV® Bible, copyright © 2001 by Crossway. Used by permission. All rights reserved.</p>', {"fontSize": "small"}))
        preacher = s["preacher"]
        notes = []
        if preacher.lower().startswith("communications"):
            notes.append("Live site lists the communications account as author; preacher unknown.")
            preacher = ""
        series = SERIES_RE.match(s["title"])
        out.append({
            "title": s["title"],
            "slug": s["source_url"].rstrip("/").split("/")[-1],
            "sermon_date": s["sermon_date"],
            "preacher": preacher,
            "scripture_references": s["scripture_references"],
            "series": series.group("series") if series else "",
            "audio_url": s["audio_url"],
            "source_url": s["source_url"],
            "content": "\n\n".join(content),
            "notes": notes,
        })
    return out


def news() -> list[dict]:
    posts = []
    for slug in NEWS:
        soup = BeautifulSoup(get(f"{BASE}/the-newsletter/{slug}"), "html.parser")
        article = soup.select_one("article") or soup.find("main")
        title = (soup.find("meta", property="og:title") or {}).get("content", slug).split(" — ")[0]
        date = (soup.find("meta", itemprop="datePublished") or {}).get("content", "")
        body = article.select_one(".blog-item-content") or article
        blocks, dropped = convert(body)
        img = (soup.find("meta", property="og:image") or {}).get("content", "")
        posts.append({"title": title, "slug": slug, "date": date, "content": "\n\n".join(blocks),
                      "image": img, "source_url": f"{BASE}/the-newsletter/{slug}", "dropped": dropped})
        print(f"  news {slug}: {len(blocks)} blocks")
    return posts


def main() -> int:
    SEED.mkdir(exist_ok=True)
    print("pages...")
    (SEED / "migrated-pages.json").write_text(json.dumps(migrate_pages(), indent=1, ensure_ascii=False), encoding="utf-8")
    print("sermons...")
    s = sermons()
    (SEED / "sermons.json").write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  {len(s)} sermons")
    print("news...")
    (SEED / "news.json").write_text(json.dumps(news(), indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
