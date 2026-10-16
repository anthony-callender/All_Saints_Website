"""Classify the crawled site into the migration inventory + redirect map.

Reads:  source/manifests/sitemap-urls.csv, source/manifests/navigation.json,
        source/manifests/sermons.json, source/metadata/crawl.json
Writes: inventory.csv, inventory.json, redirects.csv

All migration judgement lives in RULES below (first match wins), so decisions
are reviewable in one place. Actions: KEEP, IMPROVE, MERGE, ARCHIVE, REDIRECT, REVIEW.

Usage: python migration/scripts/classify.py
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse

MIGRATION = Path(__file__).resolve().parents[1]
SRC = MIGRATION / "source"
BASE = "https://www.allsaintswoodbridge.org"

# (path regex, new_url, wordpress_type, action, section, notes)
# new_url may reference {slug} (the last path segment).
RULES: list[tuple[str, str, str, str, str, str]] = [
    # --- Home + newcomer path -------------------------------------------------
    (r"^/$", "/", "page (front)", "IMPROVE", "Home", "Rebuilt homepage: visitor path first, congregant updates second. KB source (service times, location)."),
    (r"^/(home|home-page)$", "/", "-", "REDIRECT", "Home", "Legacy duplicate homepage."),
    (r"^/welcome-to-all-saints-church$", "/visit/", "-", "REDIRECT", "Visit", "Holds expired Christmas 2023 schedule + newsletter list; superseded by Plan Your Visit."),
    (r"^/(sunday|sundaymorningoptions)$", "/visit/", "-", "MERGE", "Visit", "Sunday-morning details merged into Plan Your Visit."),
    (r"^/sundaymorningoptions/.+", "/visit/", "-", "ARCHIVE", "Visit", ""),
    (r"^/faqs$", "/visit/faq/", "page", "IMPROVE", "Visit", "Question/answer pairs are out of order on the live page (answers appear under the wrong questions); rebuild as accordion. KB source."),
    (r"^/(about|worship|new-folder|resources|give)$", "-", "navigation folder", "REVIEW", "Navigation", "Squarespace nav folder (not a page); replaced by WordPress menu + hub pages."),
    (r"^/search$", "/?s=", "-", "REDIRECT", "Navigation", "Native WordPress search."),
    # --- About ----------------------------------------------------------------
    (r"^/what-we-believe$", "/about/what-we-believe/", "page", "KEEP", "About", "Theology preserved verbatim. KB source."),
    (r"^/clergy-and-staff$", "/about/clergy-and-staff/", "page", "KEEP", "About", "Staff photos to migrate. KB source (names/roles only, no personal data)."),
    (r"^/our-vestry$", "/about/vestry/", "page", "KEEP", "About", ""),
    (r"^/vestry-nominees$", "/about/vestry/", "-", "ARCHIVE", "About", "Seasonal (annual meeting)."),
    (r"^/timeline$", "/about/history/", "page", "KEEP", "About", "Parish history since 1980 (roots to 1667)."),
    (r"^/new-page-3$", "/about/history/gideon-drive/", "page", "KEEP", "About", "Unhelpful legacy slug; history of current building."),
    (r"^/jerusalem-cross$", "/about/jerusalem-cross/", "page", "KEEP", "About", "Core identity content (logo symbolism). KB source."),
    (r"^/upton-family-cemetery$", "/about/history/upton-family-cemetery/", "page", "KEEP", "About", ""),
    (r"^/photo-gallery$", "/about/photo-gallery/", "page", "KEEP", "About", "Source of authentic parish photography."),
    (r"^/employment-opportunities$", "/about/employment/", "page", "REVIEW", "About", "Confirm openings are current before launch."),
    (r"^/protecting-gods-children$", "/about/safeguarding/", "page", "KEEP", "About", "Safeguarding policy. KB source."),
    # --- Worship --------------------------------------------------------------
    (r"^/sunday-services$", "/worship/sunday-services/", "page", "IMPROVE", "Worship", "Primary service-times/what-to-expect source. KB source."),
    (r"^/wednesday-morning-eucharist$", "/worship/wednesday-eucharist/", "page", "KEEP", "Worship", "KB source."),
    (r"^/latest-sermons$", "/sermons/", "sermon archive", "IMPROVE", "Worship", "Becomes Sermon CPT archive (media library layout)."),
    (r"^/latest-sermons/.+", "/sermons/{slug}/", "sermon", "KEEP", "Worship", "Imported as Sermon CPT (title, preacher, date, scripture, MP3)."),
    (r"^/prayer$", "/prayer/", "page", "IMPROVE", "Worship", "URL kept (linked from homepage). Prayer form needs a WP form plugin; requests must never enter the KB. KB source (how to request prayer only)."),
    (r"^/(pray-for-child)$", "/prayer/", "-", "REVIEW", "Worship", "Form-only page; replace with prayer form."),
    (r"^/music$", "/worship/music/", "page", "KEEP", "Worship", ""),
    (r"^/baptism$", "/worship/baptism/", "page", "IMPROVE", "Worship", "Contains expired 2024 class date. KB source (general policy)."),
    (r"^/baptism-class-for-families$", "/worship/baptism/", "-", "MERGE", "Worship", "Empty page (form/embed only)."),
    (r"^/confirmation$", "/worship/confirmation/", "page", "KEEP", "Worship", ""),
    (r"^/new-page-5$", "/ministries/children/", "-", "REVIEW", "Worship", "'First Communion Preparation' page has no text content."),
    (r"^/(holy-week-services|lent2024|lent-2026|lent-2022-devotionals|road-to-resurrection)(/.*)?$", "/worship/", "-", "ARCHIVE", "Worship", "Seasonal; recreate each year as news post or seasonal page."),
    # --- Ministries -----------------------------------------------------------
    (r"^/children$", "/ministries/children/", "page", "IMPROVE", "Ministries", "KB source."),
    (r"^/(childrens-ministry|childrens-church|sunday-school|preschool-children|new-page)$", "/ministries/children/", "-", "MERGE", "Ministries", "Duplicative children's pages consolidated."),
    (r"^/(rooted-and-growing-resources)$", "/ministries/children/curriculum/", "page", "REVIEW", "Ministries", "20 curriculum PDFs; confirm still in use."),
    (r"^/rooted-and-growing-example$", "/ministries/children/", "-", "ARCHIVE", "Ministries", ""),
    (r"^/nursery$", "/ministries/nursery/", "page", "KEEP", "Ministries", "KB source."),
    (r"^/sick-child-nursery-policy$", "/ministries/nursery/", "-", "MERGE", "Ministries", ""),
    (r"^/register$", "/ministries/nursery/", "-", "REVIEW", "Ministries", "Child registration form; needs form plugin, collects children's data (not KB)."),
    (r"^/youth$", "/ministries/youth/", "page", "KEEP", "Ministries", "KB source."),
    (r"^/asy-calendar$", "/events/", "-", "REDIRECT", "Connect", "Youth calendar collection superseded by the main Google Calendar."),
    (r"^/asy-calendar/.+", "/events/", "-", "ARCHIVE", "Connect", "412 dated youth events with chained duplicate slugs (Squarespace duplication)."),
    (r"^/adult-discipleship$", "/ministries/adult-formation/", "page", "IMPROVE", "Ministries", "Renamed to match current 'Adult Formation' language. KB source."),
    (r"^/(christian-education-options|teachings-list|suggested-small-group-topics|books|onlineresources)$", "/ministries/adult-formation/", "-", "MERGE", "Ministries", ""),
    (r"^/(christian-education-options|teachings-list|books)/.+", "/ministries/adult-formation/", "-", "ARCHIVE", "Ministries", "Past course listings."),
    (r"^/men$", "/ministries/men/", "page", "KEEP", "Ministries", "Contains a dated event list; keep events in calendar instead. KB source."),
    (r"^/women$", "/ministries/women/", "page", "KEEP", "Ministries", "KB source."),
    (r"^/(dorcas|momco|moms-prayer|kairos)$", "/ministries/women/", "-", "MERGE", "Ministries", "Sub-ministries become sections on Women's page."),
    (r"^/(ccm|ccmblog)$", "/ministries/congregation-care/", "page", "MERGE", "Ministries", "Blog-format care page (2022 'Guest User' posts) becomes one page. KB source."),
    (r"^/ccmblog/.+", "/ministries/congregation-care/", "-", "MERGE", "Ministries", ""),
    (r"^/home-communion$", "/ministries/congregation-care/", "-", "REVIEW", "Ministries", "Survey form."),
    (r"^/(serve-in-the-community|serving-those-in-need|volunteer)$", "/ministries/serve/", "page", "MERGE", "Ministries", "KB source."),
    (r"^/monthly-food-giveaway$", "/ministries/food-pantry/", "page", "KEEP", "Ministries", "Bilingual (EN/ES) content preserved. KB source."),
    (r"^/asc-outreach-budget(/.*)?$", "/ministries/serve/", "-", "REVIEW", "Ministries", "Outreach budget pages: confirm they are meant to be public."),
    (r"^/family-resources(/.*)?$", "/ministries/children/", "-", "REVIEW", "Ministries", ""),
    (r"^/(about-vbs|scuba-vbs-snack-donations|life-saving|story|graduates|graduates-2024|fallministrylaunch|fall-ministry-launch-2023)(/.*)?$", "/ministries/", "-", "ARCHIVE", "Ministries", "Seasonal/one-off event pages."),
    # --- Connect --------------------------------------------------------------
    (r"^/calendar$", "/events/", "page", "IMPROVE", "Connect", "Keep existing Google Calendar embed (communications@ calendar)."),
    (r"^/newsletter$", "/newsletter/", "page", "IMPROVE", "Connect", "Live signup block is broken ('needs a storage option'); connect to the church's email tool."),
    (r"^/the-newsletter$", "/news/", "posts page", "IMPROVE", "Connect", "Announcements/newsletter collection becomes WordPress Posts."),
    (r"^/the-newsletter/.+", "/news/", "post", "ARCHIVE", "Connect", "2,197 items. Migrate current-season announcements as Posts; older items archived (wildcard redirect)."),
    (r"^/(whats-new|whats-new-this-week)$", "/news/", "-", "REDIRECT", "Connect", ""),
    (r"^/whats-new/.+", "/news/", "-", "ARCHIVE", "Connect", "2020 items."),
    (r"^/newsletter-archive(/.*)?$", "/news/", "-", "ARCHIVE", "Connect", "289 historical issues; retain export offline."),
    # --- Give -----------------------------------------------------------------
    (r"^/giving$", "/give/", "page", "KEEP", "Give", "Online giving via existing Breeze/PayPal links (no payment system built). KB source (how to give, not giving records)."),
    (r"^/because-you-gave$", "/give/because-you-gave/", "page", "KEEP", "Give", ""),
    (r"^/pledge$", "/give/pledge/", "page", "REVIEW", "Give", "Pledge form; needs form plugin."),
    (r"^/stewardship-2022(/.*)?$", "/give/", "-", "ARCHIVE", "Give", "Slug says 2022, title says 2025."),
]

FIELDS = [
    "source_url", "page_title", "content_type", "parent_section", "navigation_label", "navigation_parent",
    "heading_structure", "body_text", "primary_images", "downloadable_files", "embedded_video", "embedded_audio",
    "internal_links", "external_links", "publish_date", "author_if_available", "seo_title_if_available",
    "meta_description_if_available", "canonical_url_if_available", "proposed_wordpress_type", "proposed_new_url",
    "migration_action", "migration_status", "notes", "word_count", "sitemap_lastmod", "crawled",
]


def classify(path: str) -> tuple[str, str, str, str, str]:
    slug = path.rstrip("/").split("/")[-1]
    for pattern, new_url, wp_type, action, section, notes in RULES:
        if re.match(pattern, path):
            return new_url.format(slug=slug), wp_type, action, section, notes
    return "", "unclassified", "REVIEW", "", "No rule matched; needs a human decision."


def content_type(path: str) -> str:
    parts = path.strip("/").split("/")
    if path == "/":
        return "homepage"
    if len(parts) == 1:
        return "page"
    return f"collection item ({parts[0]})"


def main() -> int:
    with (SRC / "manifests" / "sitemap-urls.csv").open(encoding="utf-8") as fh:
        sitemap = {row["url"]: row["lastmod"] for row in csv.DictReader(fh)}
    nav = json.loads((SRC / "manifests" / "navigation.json").read_text(encoding="utf-8"))
    crawl = {r["source_url"]: r for r in json.loads((SRC / "metadata" / "crawl.json").read_text(encoding="utf-8"))["records"]}
    sermons = {s["source_url"]: s for s in json.loads((SRC / "manifests" / "sermons.json").read_text(encoding="utf-8"))}

    nav_label: dict[str, tuple[str, str]] = {}
    for top in nav:
        for child in top["children"]:
            nav_label[child["href"].rstrip("/")] = (child["label"], top["label"])
        if top["href"]:
            nav_label.setdefault(top["href"].rstrip("/"), (top["label"], ""))

    urls = list(dict.fromkeys([f"{BASE}/", *sitemap, *(BASE + h for h in nav_label if h.startswith("/"))]))
    rows = []
    for url in urls:
        path = urlparse(url).path.rstrip("/") or "/"
        new_url, wp_type, action, section, notes = classify(path)
        rec = crawl.get(url) or crawl.get(url.rstrip("/")) or {}
        sermon = sermons.get(url, {})
        label, parent = nav_label.get(path, ("", ""))
        body = rec.get("body_text") or sermon.get("body_text", "")
        rows.append({
            "source_url": url,
            "page_title": rec.get("page_title") or sermon.get("title", ""),
            "content_type": content_type(path),
            "parent_section": section,
            "navigation_label": label,
            "navigation_parent": parent,
            "heading_structure": rec.get("heading_structure", []),
            "body_text": body,
            "primary_images": [i["src"] for i in rec.get("primary_images", [])],
            "downloadable_files": rec.get("downloadable_files", []),
            "embedded_video": rec.get("embedded_video", []),
            "embedded_audio": rec.get("embedded_audio", []) or ([sermon["audio_url"]] if sermon.get("audio_url") else []),
            "internal_links": rec.get("internal_links", []),
            "external_links": rec.get("external_links", []),
            "publish_date": rec.get("publish_date") or sermon.get("sermon_date", ""),
            "author_if_available": rec.get("author") or sermon.get("preacher", ""),
            "seo_title_if_available": rec.get("seo_title", ""),
            "meta_description_if_available": rec.get("meta_description", ""),
            "canonical_url_if_available": rec.get("canonical_url", ""),
            "proposed_wordpress_type": wp_type,
            "proposed_new_url": new_url,
            "migration_action": action,
            "migration_status": "not started",
            "notes": notes,
            "word_count": rec.get("word_count", len(body.split()) if body else 0),
            "sitemap_lastmod": sitemap.get(url, ""),
            "crawled": "yes" if rec or sermon else "sitemap only",
        })

    # JSON keeps full detail (body truncated to keep the file reviewable).
    json_rows = [{**r, "body_text": r["body_text"][:2000]} for r in rows]
    (MIGRATION / "inventory.json").write_text(json.dumps(json_rows, indent=1, ensure_ascii=False), encoding="utf-8")

    with (MIGRATION / "inventory.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for r in rows:
            flat = dict(r)
            for key in ("heading_structure", "primary_images", "downloadable_files", "embedded_video",
                        "embedded_audio", "internal_links", "external_links"):
                flat[key] = " | ".join(r[key][:15])
            flat["body_text"] = re.sub(r"\s+", " ", r["body_text"])[:280]
            writer.writerow(flat)

    write_redirects(rows)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["migration_action"]] = counts.get(r["migration_action"], 0) + 1
    print(f"{len(rows)} URLs classified: {counts}")
    unclassified = [r["source_url"] for r in rows if r["proposed_wordpress_type"] == "unclassified"]
    if unclassified:
        print("Unclassified:", *unclassified[:20], sep="\n  ")
    return 0


def write_redirects(rows: list[dict]) -> None:
    """Explicit 301s for pages; one wildcard rule per high-volume archived collection."""
    wildcard_collections = {"the-newsletter", "asy-calendar", "newsletter-archive", "christian-education-options",
                            "whats-new", "ccmblog", "scuba-vbs-snack-donations", "stewardship-2022",
                            "fall-ministry-launch-2023", "lent-2022-devotionals", "lent-2026", "teachings-list",
                            "books", "family-resources", "asc-outreach-budget", "sundaymorningoptions"}
    out, seen_wild = [], set()
    for r in rows:
        path = urlparse(r["source_url"]).path.rstrip("/") or "/"
        new = r["proposed_new_url"]
        if not new or path == "/":
            continue
        top = path.strip("/").split("/")[0]
        if path.count("/") > 1 and top in wildcard_collections:
            if top not in seen_wild:
                seen_wild.add(top)
                out.append((f"/{top}/*", new, 301, f"Archived collection ({r['migration_action']}); wildcard rule"))
            continue
        if path.rstrip("/") + "/" == new:
            continue  # URL preserved
        out.append((path, new, 301, f"{r['migration_action']}: {r['notes']}".strip(": ")[:160]))
    # Squarespace URL shortcuts discovered by report_checks.py (not in the sitemap but linked/used).
    out += [
        ("/service-videos", "https://www.youtube.com/channel/UCOouhW9_VVwiVODtl0gDvVA/streams", 301, "Legacy shortcut used on homepage"),
        ("/pgc", "/about/safeguarding/", 301, "Legacy shortcut (Protecting God's Children)"),
        ("/road", "/ministries/", 301, "Legacy shortcut to archived Road to Resurrection page"),
        ("/sermon-form", "/wp-admin/post-new.php?post_type=sermon", 302, "Hidden clergy sermon form; replaced by worker + editor review"),
    ]
    with (MIGRATION / "redirects.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["old_url", "new_url", "status_code", "reason"])
        seen: set[str] = set()
        w.writerows(row for row in out if not (row[0] in seen or seen.add(row[0])))
    print(f"{len(out)} redirect rules written")


if __name__ == "__main__":
    raise SystemExit(main())
