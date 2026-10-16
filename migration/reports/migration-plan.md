# Migration Plan — allsaintswoodbridge.org → WordPress

Audit date: **2 October 2026**. Source: live Squarespace site (7.0 template). Data: `migration/inventory.csv` (3,182 rows), `migration/redirects.csv` (154 rules), raw crawl in `migration/source/`.

## 1. What exists today

| | Count |
|---|---|
| URLs in sitemap.xml | 3,174 (+8 from navigation) |
| Standalone pages | 91 |
| Collection items | 3,091 across 17 collections |
| Pages/items crawled and stored as text | 299 pages + 46 sermons (Squarespace JSON) |
| Downloadable files linked (PDF/DOC) | 42 |
| Distinct images referenced | 284 |
| Broken internal links (404) | 22 (`reports/broken-links.md`) |
| URLs that are Squarespace "duplicate-item" chains | 1,069 (`reports/duplicate-content.md`) |

**The site is far smaller than its sitemap suggests.** 94% of URLs are dated items in three collections: `/the-newsletter/` (2,197), `/asy-calendar/` (412 youth events), `/newsletter-archive/` (289).

### Current main sections (live navigation)
About · Worship · Ministries · Resources · Give — no newcomer/"Visit" path. Service times live only in the homepage banner text and `/sunday-services`.

### Content types found
Static pages, sermons (audio posts), newsletter/announcement posts, youth calendar items, a Google Calendar embed (`communications@` calendar), Squarespace forms (prayer request, child registration, pledge, sermon form, home communion survey), PDFs (order of service, curriculum, catechism links), and a broken newsletter signup block.

## 2. Useful content (what we migrate)

**106 URLs** are KEEP/IMPROVE/MERGE: 46 sermons, 32 pages that become WordPress pages, and 28 pages merged into others.

| Action | URLs | Meaning |
|---|---|---|
| KEEP | 65 | Move as-is (46 sermons, 19 pages: beliefs, clergy, history, Jerusalem Cross, nursery, youth, men, women, food pantry, give …) |
| IMPROVE | 11 | Move and rewrite structure (homepage, Sunday services, FAQ, prayer, children, adult formation, calendar, newsletter, sermon archive, baptism) |
| MERGE | 30 | Fold duplicates into one canonical page (5 children's pages → 1, 5 adult-formation pages → 1, 3 serve pages → 1, homepage variants …) |
| REDIRECT | 7 | No content of its own (`/home`, `/home-page`, `/whats-new*`, `/search`, …) |
| REVIEW | 21 | Needs a human decision (forms, outreach-budget pages, curriculum PDFs, job openings, empty pages) |
| ARCHIVE | 3,048 | Dated/seasonal items; not migrated as pages, kept reachable via wildcard redirects; raw export retained |

**Built in this local MVP:** 30 pages (20 converted from the live HTML into editable core blocks + 10 hand-built: Home, Plan Your Visit, Events, Contact, News, Newsletter, Congregation Care, 3 hub pages), **all 46 sermons**, 7 current announcements as Posts, 24 verified Church Knowledge entries, 10 media items (logo + real parish photography).

## 3. Proposed information architecture

See `proposed-information-architecture.md`. Summary: **Visit · About · Worship · Ministries · Connect · Give** with a persistent **Plan Your Visit** button; service times + location immediately below the homepage hero.

## 4. Key media & assets

- Logo: `ASC Simple Logo (No Background).png` — red/blue Jerusalem Cross + serif wordmark (kept unchanged).
- Real photography selected (`source/manifests/selected-photos.json`): celebrant at the altar (hero), congregation outside the Gideon Drive church, children's ministry, youth room, food-pantry volunteers, worship team. **Gap:** the best building photo is only 500×334 px (see content gaps).
- Sermon MP3s: 46 on Squarespace CDN; imported as external `asc_audio_url` for the demo; production migration should download them into the Media Library (~1.2 GB estimated at ~25 MB each).
- 42 PDFs/DOCs (order of service, Rooted & Growing curriculum, catechism) → Media Library, linked from the new pages.

## 5. Redirects

`redirects.csv` — 154 rules, all 301 unless noted: one explicit rule per migrated/merged page, one per sermon (`/latest-sermons/<slug>` → `/sermons/<slug>/`), one wildcard per archived collection (`/the-newsletter/*` → `/news/` …), and legacy shortcuts discovered in the audit (`/service-videos`, `/pgc`, `/road`). Kept URLs need no rule (e.g. `/prayer/`). Import with the *Redirection* plugin (supports wildcards/regex) or server config.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Forms (prayer, child registration, pledge) handle personal data | Rebuild with a WordPress form plugin (e.g. Gravity Forms) with email-only delivery; never feed submissions to the chatbot KB. |
| Outdated content migrates as "truth" | Only KEEP/IMPROVE content moves; KB entries carry `last verified` dates and flag after 6 months. |
| Lost SEO equity from 3,000+ dated URLs | Wildcard 301s per collection; sitemap resubmitted in Search Console. |
| MP3 hosting tied to Squarespace CDN | Download into Media Library before Squarespace is cancelled (demo uses remote URLs). |
| Avada not yet installed | Design tokens are theme-agnostic; mapping to Avada Global Options documented (`docs/design-system.md`). |
| Sermon publishing is ~5½ months behind (latest live sermon: 19 Apr 2026) | Sermon worker creates drafts automatically; editor only reviews/publishes. |

## 7. Recommendations (in order)

1. Approve the IA and the 21 REVIEW decisions with the parish staff.
2. Install Avada (licensed) and mirror the tokens in Global Options; rebuild Home/Visit sections as Avada containers using the same `asc-*` classes.
3. Rebuild the four forms in a form plugin; fix the newsletter signup (connect the church's email tool).
4. Download sermon MP3s + PDFs into the Media Library; re-point `asc_audio_url` → `asc_audio_attachment_id`.
5. Commission/collect 6–10 high-resolution photos (building exterior, sanctuary, Sunday morning welcome).
6. Launch: import redirects, switch DNS, submit sitemap, monitor 404s for 30 days.
