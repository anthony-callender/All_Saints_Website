# Duplicate Content

## 1. Squarespace "duplicate item" chains

Re-using an old post by duplicating it appends a random 5-character suffix to the slug, and duplicating the duplicate chains them (e.g. `/asy-calendar/asy-on-sundays-5rby3-nh8zb-9gzbr-…`). These are separate public URLs with near-identical content.

| Collection | URLs with chained suffixes |
|---|---|
| `/the-newsletter/` | 611 |
| `/asy-calendar/` | 304 |
| `/newsletter-archive/` | 123 |
| `/christian-education-options/` | 15 |
| `/latest-sermons/` | 6 |
| `/stewardship-2022/` | 4 |
| `/scuba-vbs-snack-donations/` | 2 |
| `/lent-2022-devotionals/` | 1 |
| `/books/` | 1 |
| `/sundaymorningoptions/` | 1 |
| `/ccmblog/` | 1 |

Most-duplicated base slugs:

| Base slug | Copies |
|---|---|
| `/asy-calendar/asy-on-sundays` | 46 |
| `/asy-calendar/thursday` | 39 |
| `/newsletter-archive/9n9atdtg3j8fgyj` | 31 |
| `/newsletter-archive/b2xwsxc53berle7` | 31 |
| `/asy-calendar/sundayschool` | 29 |
| `/asy-calendar/chosen` | 23 |
| `/newsletter-archive/9ryjkztkygsamcn` | 22 |
| `/the-newsletter/readings-and-collect` | 18 |
| `/the-newsletter/readings-and-collect-for-sunday-august16` | 18 |
| `/asy-calendar/sundayschool-fall` | 15 |
| `/asy-calendar/youthmay23` | 15 |
| `/asy-calendar/bible-study-begins` | 14 |

## 2. Identical page bodies (crawled pages)

- `/fall-ministry-launch-2023/mens-ministry-breakfast-saturday-september-16`, `/fall-ministry-launch-2023/category/adult+resources`, `/fall-ministry-launch-2023/tag/adult+resources`

## 3. Repeated page titles (crawled pages)

- **what's new this week**: `/whats-new`, `/whats-new-this-week`
- **missionary guest speaker**: `/latest-sermons/missionary-guest-speaker-1`, `/latest-sermons/missionary-guest-speaker`
- **the newsletter**: `/the-newsletter`, `/newsletter`
- **thursday evenings- women's bible study**: `/christian-education-options/thursday-evenings-womens-bible-study-7w72k`, `/christian-education-options/thursday-evenings-womens-bible-study`
- **children — christian education options**: `/christian-education-options/category/children`, `/christian-education-options/category/Children`
- **youth — christian education options**: `/christian-education-options/category/Youth`, `/christian-education-options/category/youth`
- **request prayer**: `/ccmblog/request-prayer`, `/pray-for-child`
- **adult resources — fall ministry launch 2023**: `/fall-ministry-launch-2023/category/adult+resources`, `/fall-ministry-launch-2023/tag/adult+resources`

## 4. Overlapping pages (manual review)

- Homepage variants: `/`, `/home`, `/home-page`, `/welcome-to-all-saints-church` → one homepage + Plan Your Visit.
- Children: `/children`, `/childrens-ministry`, `/childrens-church`, `/sunday-school`, `/preschool-children`, `/new-page` → one Children page.
- Announcements: `/whats-new`, `/whats-new-this-week`, `/the-newsletter`, `/newsletter-archive` → WordPress Posts (`/news/`).
- Serving: `/serve-in-the-community`, `/serving-those-in-need`, `/volunteer` → one Serve page.
- Adult formation: `/adult-discipleship`, `/christian-education-options`, `/teachings-list`, `/suggested-small-group-topics`, `/books` → one page.

**Decision:** WordPress uses one canonical page per topic; every duplicate URL gets a 301 in `redirects.csv`.
