"""Data-driven report inputs: broken internal links and duplicate content.

Writes reports/broken-links.md and reports/duplicate-content.md.
Internal links not present in the sitemap are checked with a polite HEAD/GET.

Usage: python migration/scripts/report_checks.py
"""
from __future__ import annotations

import collections
import csv
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

MIGRATION = Path(__file__).resolve().parents[1]
BASE = "https://www.allsaintswoodbridge.org"
UA = {"User-Agent": "ASC-Migration-Audit/1.0"}
CHAIN_RE = re.compile(r"(-[a-z0-9]{5})+$")


def main() -> int:
    crawl = json.loads((MIGRATION / "source/metadata/crawl.json").read_text(encoding="utf-8"))["records"]
    with (MIGRATION / "source/manifests/sitemap-urls.csv").open(encoding="utf-8") as fh:
        sitemap_paths = {urlparse(r["url"]).path.rstrip("/") or "/" for r in csv.DictReader(fh)}

    # ---- Broken links -------------------------------------------------------
    linked_from = collections.defaultdict(set)
    for rec in crawl:
        for path in rec.get("internal_links", []):
            if path.startswith(("/s/", "/static", "/cart", "/config", "/search", "/api")) or path in ("/", ""):
                continue
            linked_from[path].add(urlparse(rec["source_url"]).path)
    unknown = sorted(p for p in linked_from if p not in sitemap_paths)
    broken = []
    for path in unknown:
        time.sleep(0.3)
        try:
            resp = requests.get(BASE + path, headers=UA, timeout=20, allow_redirects=True)
            status = resp.status_code
            final = urlparse(resp.url).path
        except requests.RequestException as exc:
            status, final = 0, exc.__class__.__name__
        if status >= 400 or status == 0:
            broken.append((path, status, sorted(linked_from[path])[:4]))
        elif final.rstrip("/") != path.rstrip("/"):
            broken.append((path, f"{status} → {final}", sorted(linked_from[path])[:4]))

    lines = [
        "# Broken & Redirecting Internal Links",
        "",
        f"Checked {len(linked_from)} distinct internal link targets found in {len(crawl)} crawled pages; "
        f"{len(unknown)} were not in the sitemap and were requested individually.",
        "",
        "| Link target | Result | Linked from (sample) |",
        "|---|---|---|",
    ]
    lines += [f"| `{p}` | {s} | {', '.join(f'`{x}`' for x in src)} |" for p, s, src in broken]
    if not broken:
        lines.append("| — | none found | — |")
    lines += ["", "Squarespace file links (`/s/...`) are listed per page in `inventory.csv` → `downloadable_files` and must be re-uploaded to the Media Library during migration.", ""]
    (MIGRATION / "reports/broken-links.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"broken/redirecting: {len(broken)}")

    # ---- Duplicates ---------------------------------------------------------
    with (MIGRATION / "source/manifests/sitemap-urls.csv").open(encoding="utf-8") as fh:
        paths = [urlparse(r["url"]).path for r in csv.DictReader(fh)]
    chained = collections.Counter(p.strip("/").split("/")[0] for p in paths if p.count("/") >= 2 and CHAIN_RE.search(p.rstrip("/")))
    by_base = collections.Counter(CHAIN_RE.sub("", p.rstrip("/")) for p in paths if p.count("/") >= 2)
    worst = [(b, n) for b, n in by_base.most_common(12) if n > 3]

    bodies = collections.defaultdict(list)
    titles = collections.defaultdict(list)
    for rec in crawl:
        body = re.sub(r"\s+", " ", rec.get("body_text", "")).strip()
        if len(body) > 200:
            bodies[hashlib.sha1(body.encode()).hexdigest()].append(urlparse(rec["source_url"]).path)
        if rec.get("page_title"):
            titles[rec["page_title"].strip().lower()].append(urlparse(rec["source_url"]).path)
    same_body = [v for v in bodies.values() if len(v) > 1]
    same_title = [(t, v) for t, v in titles.items() if len(v) > 1]

    lines = [
        "# Duplicate Content",
        "",
        "## 1. Squarespace \"duplicate item\" chains",
        "",
        "Re-using an old post by duplicating it appends a random 5-character suffix to the slug, and duplicating the duplicate chains them "
        "(e.g. `/asy-calendar/asy-on-sundays-5rby3-nh8zb-9gzbr-…`). These are separate public URLs with near-identical content.",
        "",
        "| Collection | URLs with chained suffixes |",
        "|---|---|",
    ]
    lines += [f"| `/{c}/` | {n} |" for c, n in chained.most_common()]
    lines += ["", "Most-duplicated base slugs:", "", "| Base slug | Copies |", "|---|---|"]
    lines += [f"| `{b}` | {n} |" for b, n in worst]
    lines += ["", "## 2. Identical page bodies (crawled pages)", ""]
    lines += [f"- {', '.join(f'`{p}`' for p in group)}" for group in same_body] or ["- none"]
    lines += ["", "## 3. Repeated page titles (crawled pages)", ""]
    lines += [f"- **{t}**: {', '.join(f'`{p}`' for p in v)}" for t, v in same_title] or ["- none"]
    lines += [
        "",
        "## 4. Overlapping pages (manual review)",
        "",
        "- Homepage variants: `/`, `/home`, `/home-page`, `/welcome-to-all-saints-church` → one homepage + Plan Your Visit.",
        "- Children: `/children`, `/childrens-ministry`, `/childrens-church`, `/sunday-school`, `/preschool-children`, `/new-page` → one Children page.",
        "- Announcements: `/whats-new`, `/whats-new-this-week`, `/the-newsletter`, `/newsletter-archive` → WordPress Posts (`/news/`).",
        "- Serving: `/serve-in-the-community`, `/serving-those-in-need`, `/volunteer` → one Serve page.",
        "- Adult formation: `/adult-discipleship`, `/christian-education-options`, `/teachings-list`, `/suggested-small-group-topics`, `/books` → one page.",
        "",
        "**Decision:** WordPress uses one canonical page per topic; every duplicate URL gets a 301 in `redirects.csv`.",
        "",
    ]
    (MIGRATION / "reports/duplicate-content.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"chained collections: {dict(chained)}; identical bodies: {len(same_body)}; repeated titles: {len(same_title)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
