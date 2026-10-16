# Proposed Information Architecture

Based on the inventory, not the initial hypothesis. Changes from the hypothesis: no separate "Leadership" page (Vestry lives under About), no "Service Times" page (it is a reusable section that appears on Home and Plan Your Visit), "Sunday Worship" keeps the existing *Sunday Services* name, and **Food Pantry** gets its own page because it is the church's most active public-facing ministry (bilingual EN/ES).

```
HOME  /
│   hero → service times & location → plan your visit → latest sermon
│   → life at All Saints' (4 cards) → what's happening → prayer
│
├── VISIT
│   ├── Plan Your Visit ............ /visit/                      NEW (merges /welcome-…, /sunday, /sundaymorningoptions)
│   ├── Sunday Services ............ /worship/sunday-services/    (was /sunday-services)
│   ├── Wednesday Eucharist ........ /worship/wednesday-eucharist/
│   ├── Directions & Accessibility . /visit/#directions
│   └── FAQ ........................ /visit/faq/                  PLANNED: rebuild as accordion (live Q/A out of order)
│
├── ABOUT  /about/
│   ├── What We Believe ............ /about/what-we-believe/
│   ├── Clergy & Staff ............. /about/clergy-and-staff/
│   ├── Our Vestry ................. /about/vestry/
│   ├── Our History ................ /about/history/  (+ /gideon-drive/, /upton-family-cemetery/)
│   ├── The Jerusalem Cross ........ /about/jerusalem-cross/
│   └── Safeguarding ............... /about/safeguarding/
│
├── WORSHIP  /worship/
│   ├── Sunday Services
│   ├── Sermons .................... /sermons/  (Sermon CPT archive)
│   ├── Prayer ..................... /prayer/   (URL kept)
│   ├── Baptism .................... /worship/baptism/
│   └── Music ...................... /worship/music/
│
├── MINISTRIES  /ministries/
│   ├── Children ................... /ministries/children/   (merges 5 pages)
│   ├── Nursery .................... /ministries/nursery/
│   ├── Youth ...................... /ministries/youth/
│   ├── Adult Formation ............ /ministries/adult-formation/  (merges 5 pages)
│   ├── Men ........................ /ministries/men/
│   ├── Women ...................... /ministries/women/  (Dorcas, MomCo, Moms in Prayer, Kairos as sections)
│   ├── Congregation Care .......... /ministries/congregation-care/
│   ├── Serve in the Community ..... /ministries/serve/
│   └── Food Pantry ................ /ministries/food-pantry/
│
├── CONNECT
│   ├── Events Calendar ............ /events/      (existing Google Calendar embed)
│   ├── News ....................... /news/        (WordPress Posts; replaces /the-newsletter, /whats-new*)
│   ├── Newsletter ................. /newsletter/
│   └── Contact .................... /contact/
│
└── GIVE  /give/   (Breeze + PayPal links; /give/because-you-gave/, /give/pledge/)

Header CTA: [Plan Your Visit]      Footer: address · times · explore · YouTube · Facebook · Report misconduct
```

## Two audiences

| First-time visitor (top of homepage) | Existing congregant (lower homepage + Connect) |
|---|---|
| Service times + location in the first screen | Latest sermon (auto-updates) |
| Plan Your Visit: dress, communion, children, accessibility | What's happening (latest 3 posts) + calendar |
| What we believe | Newsletter, ministries, prayer, giving |

## Navigation rules for editors

- Six top-level items maximum; new pages go *under* a section.
- Hub pages (`/about/`, `/worship/`, `/ministries/`) list their child pages automatically (Page List block), so a new child page appears without editing the hub.
- Seasonal content (Lent, Holy Week, VBS) is a **Post** or a child page that is archived afterwards — not a new top-level page.
