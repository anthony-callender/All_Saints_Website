# Design System — "Modern Anglican"

Reverent, warm, historic, welcoming, uncluttered. Derived from the existing All Saints' identity, not a rebrand.

## Brand sources (audited)

| Source | Finding | Used as |
|---|---|---|
| Logo PNG | Jerusalem Cross: red `#ff1923`, blue `#005ca9`; black serif caps wordmark | Logo unchanged; red/blue darkened for text contrast |
| Site CSS | Navy `#0b2a60`, amber `#d78d33`, charcoal `#272727` | Secondary + accent |
| Site fonts | Adobe Garamond Pro (headings), Proxima Nova (body) | EB Garamond + Source Sans 3 (open licences, same character) |
| Jerusalem Cross page | "a very special symbol … it speaks to who we are" | Watermark on audio-only sermon art (season colour of the church year + service date); checklist bullet mark |
| Photography | Real worship, building, children, youth, food pantry | Hero + cards (no stock photos) |

## Tokens (`assets/css/tokens.css`)

| Token | Value | Notes |
|---|---|---|
| `--asc-color-background` | `#f8f5ee` | warm parchment |
| `--asc-color-text` | `#1b2433` | 14.9:1 on background |
| `--asc-color-primary` | `#b3141e` | cross red, 6.3:1 on white — buttons, eyebrows |
| `--asc-color-link` | `#00539a` | cross blue, 7.3:1 |
| `--asc-color-secondary` | `#0b2a60` | parish navy — headings, dark bands, footer |
| `--asc-color-accent` / `-soft` | `#b8741f` / `#e3b46a` | amber; decorative or on navy only |
| `--asc-font-serif` / `--asc-font-sans` | EB Garamond / Source Sans 3 | two fonts only |
| `--asc-text-*` | `clamp()` fluid scale | body 17–19 px |
| `--asc-space-*` | `clamp()` fluid spacing | xs → xl |
| `--asc-content-width` / `-wide` | 72rem / 86rem | prose limited to 68ch |
| `--asc-radius-*`, `--asc-shadow-*` | small, restrained | |

## CSS layers

```
tokens.css      variables only (+ reduced-motion)
base.css        :where() zero-specificity defaults, focus-visible, sr-only — theme settings always win
components.css  asc-* classes applied to ordinary blocks/containers (hero, service times, split, cards, prayer band, news, header, footer, calendar)
sermons.css     sermon cards (container query), archive filter, featured sermon, video facade, audio player
chatbot.css     launcher + panel; full-screen sheet on phones
```
~900 lines total. Grid/Flexbox, `clamp()`, `min()/max()`, `aspect-ratio`, `object-fit`, logical properties, `:focus-visible`, one container query, `prefers-reduced-motion`.

## Components (editor-facing)

| Component | How an editor uses it |
|---|---|
| Hero | Group block + class `asc-hero`; change photo in *Styles → Background image* |
| Service Times & Location | Synced pattern — edit once, updates Home + Plan Your Visit |
| Prayer Invitation | Synced pattern |
| Plan-your-visit split | Media & Text block + class `asc-split`; checklist = List + `asc-checklist` |
| Ministry cards | Pattern "Ministry Cards" (Group `asc-card-grid` › Group `asc-card`) |
| Latest Sermon | `[asc_latest_sermon]` — updates automatically |
| Sermon grid | `[asc_sermons count="3"]` |
| Assistant | site-wide button (toggle in settings) or `[asc_chatbot]` |

## Mapping to Avada (when the licensed theme is installed)

| Token | Avada Global Options |
|---|---|
| colors | *Colors → Color Palette* (Color 1–8: parchment, white, stone, ink, navy, red, blue, amber) |
| `--asc-font-serif` | *Typography → Headings Typography* (EB Garamond 500) |
| `--asc-font-sans` | *Typography → Body Typography* (Source Sans 3 400, 18px) |
| content widths | *Layout → Site Width* 1376px (86rem); content 1152px (72rem) |
| buttons | *Buttons → Button Style*: primary red, radius 6px, 600 weight |
| `asc-*` components | Avada container/column **CSS Class** field; save as *Avada Library → Containers* ("Service Times", "Visitor CTA", "Prayer CTA", "Ministry Cards") |

The plugin CSS is theme-agnostic, so the same classes work on Avada containers; the plugin also provides a classic-theme sermon archive template for Avada.

## Accessibility

Contrast ≥ 4.5:1 for all text pairs above; visible 3px focus ring; 44px minimum targets on buttons, filters, chat controls; semantic landmarks (`header`, `main`, `section`, `article`, `nav`); one `h1` per page; images have descriptive alt text; chat log is `role="log" aria-live="polite"`; Escape closes the assistant and returns focus; motion ≤ 180 ms and disabled under `prefers-reduced-motion`.
