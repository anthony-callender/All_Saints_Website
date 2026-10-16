# Content Gaps & Issues Found

Items to resolve with parish staff. Nothing here was invented to fill a gap.

## Missing for newcomers
- **No "Plan Your Visit" page** existed; built from verified text on `/sunday-services`, `/nursery`, `/faqs`.
- **Parking / which entrance to use** on a first visit is not described anywhere (accessibility parking is). Ask the office.
- **Office hours** are not published. Contact page omits them until confirmed.
- **Youth meeting times**: `/faqs` says Sunday 6–8 p.m. but `/youth` does not confirm it; treated as possibly stale and kept out of the chatbot KB.
- **Spanish-language ministry**: an Associate Rector for Spanish-Language Ministry is listed, but no page describes services or times in Spanish (only the food-pantry page is bilingual).

## Outdated or misleading on the live site
- `/welcome-to-all-saints-church` still lists **Christmas 2023** service times.
- `/baptism` advertises a class on **27 April 2024**.
- `/faqs`: question and answer blocks are **out of order** (e.g. "How do I join?" sits under the baptism answer).
- `/men` lists events for April–May 2026 inline (should come from the calendar/newsletter).
- `/stewardship-2022` is titled "Stewardship 2025".
- `/newsletter` signup block shows "This newsletter signup form needs a storage option" — **the public signup is broken**.
- Sermons: newest is **19 April 2026**; ~5½ months of sermons not posted (the 31 May 2026 sermon was prepared by the legacy agent but never published).
- Two sermons list the **communications account** as author instead of the preacher (`Palm Sunday Expectations`, `The Spirit is Like the Wind`) — imported with preacher left blank.
- 22 internal links return 404 (`broken-links.md`).

## Media gaps
- Best building exterior photo is **500×334 px**; no high-resolution exterior or sanctuary-wide photo found. Hero uses the 1815 px altar photo instead.
- Most ministry photos are phone snapshots or graphics with text baked in (not reusable as page imagery).
- Staff photos exist and are good.

## Forms that need a WordPress replacement
Prayer request · praise report · child registration (`/register`) · pledge (`/give/pledge`) · home communion survey · sermon form (`/sermon-form`, replaced by the worker + `--form` input).

## Sensitive content observed (must NOT enter the chatbot KB)
- Newsletter items with member birthdays/anniversaries and memorial notices.
- Volunteer personal phone numbers and Gmail addresses (e.g. on `/men`).
- Outreach budget pages (`/asc-outreach-budget/*`) — confirm they are meant to be public.
