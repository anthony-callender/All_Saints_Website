=== ASC Digital Ministry ===
Contributors: allsaintswoodbridge
Requires at least: 6.7
Requires PHP: 8.1
Stable tag: 1.0.0
License: GPLv2 or later

Sermons, Church Knowledge, a grounded website assistant, and the All Saints' design-system layer.

== Description ==

* **Sermon** post type (`/sermons/`) with REST-registered metadata (date, preacher, scripture, YouTube ID/URL, audio, transcript [editors only], pipeline version). Media-library archive, featured "Latest Sermon" and grids via shortcodes. Duplicate protection keyed on YouTube video ID (`GET /wp-json/asc/v1/sermons/exists`, and a 409 guard on create).
* **Church Knowledge** (private) — short verified facts with source page and "last verified" date. Indexed into `{prefix}asc_kb_chunks` on publish/update; removed on unpublish/delete.
* **Website assistant** — `POST /wp-json/asc/v1/chat`. Retrieval over Church Knowledge (cosine similarity in PHP), grounded answer with sources, safe fallback, per-IP + daily rate limits. Vanilla-JS widget: site-wide toggle or `[asc_chatbot]`.
* **Design system** — tokens + component CSS (`asc-*` classes) and block patterns: Service Times & Location, Prayer Invitation, Latest Sermon, Ministry Cards.

== Configuration ==

Set as environment variables (DDEV: `.ddev/.env`) or constants in `wp-config.php`. Never stored in the database.

* `OPENAI_API_KEY` — without it the assistant runs in offline mode (lexical retrieval, extractive answers).
* `OPENAI_CHAT_MODEL` (default `gpt-5-mini`), `OPENAI_EMBEDDING_MODEL` (default `text-embedding-3-small`)
* `ASC_CHAT_RATE_LIMIT`, `ASC_CHAT_RATE_WINDOW`, `ASC_CHAT_DAILY_CAP`, `ASC_CHAT_MAX_TOKENS`, `ASC_KB_SIMILARITY_THRESHOLD`

== Shortcodes ==

* `[asc_latest_sermon]` · `[asc_sermons count="3"]` · `[asc_sermon_archive]` · `[asc_chatbot]`

== WP-CLI ==

* `wp asc kb status` · `wp asc kb reindex [--force]` · `wp asc kb search "question"`

== Tests ==

`wp eval-file wp-content/plugins/asc-digital-ministry/tests/run-tests.php`
