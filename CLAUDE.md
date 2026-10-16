# CLAUDE.md — All Saints' Church WordPress rebuild

Rules for anyone (human or AI) changing this repo.

1. **WordPress is the CMS.** Don't re-litigate the platform.
2. **Avada (+ Avada Builder) is the target visual builder.** Until the licensed package is installed, the core block theme is a stand-in; never substitute Elementor/Kadence/etc.
3. **No React/Next/Vue/headless public frontend.** The public site is rendered by WordPress.
4. **Semantic HTML + the token CSS layer** (`wp-content/plugins/asc-digital-ministry/assets/css`). Add components as `asc-*` classes; don't fight the theme with specificity.
5. **Vanilla JS** for interactions (`assets/js`). Progressive enhancement: pages must work without JS.
6. **Gutenberg for structured editorial content** (sermons, posts). Avada for page composition.
7. **Beth must stay self-sufficient.** If a change means a volunteer needs a developer for ordinary edits, redesign it.
8. **No ordinary content in PHP.** Page content lives in WordPress (seed data lives in `/seed` as block markup/JSON).
9. **Custom logic lives in the plugin** (`asc-digital-ministry`) **or the worker** (`worker/sermon_flywheel`).
10. **Reuse `AllSaints_Agent`** through `sermon_worker/legacy.py`. Do not edit, move, or delete it.
11. **Never hallucinate sermon metadata.** Unknown = `null`/`[]`. Keep the fidelity guards in `llm.py` and authoritative metadata precedence.
12. **Secrets stay out of Git** (`.env`, `.ddev/.env`, `tmp/` are ignored). Never log secrets.
13. **Idempotency:** YouTube video ID is the sermon key (exists endpoint + 409 guard). Keep both.
14. **No vector infrastructure** (no Pinecone/Qdrant/pgvector/Redis). JSON vectors in `wp_asc_kb_chunks` + PHP cosine is enough.
15. **Audit before migrating.** Migration decisions live in `migration/scripts/classify.py` (RULES) and are regenerated, not hand-edited in the CSV.
16. **Preserve redirects** for every moved/merged URL (`migration/redirects.csv`).
17. **Keep it weekend-sized.** Prefer simple + working over abstract + scalable.

Also: the chatbot KB holds only public, verified facts — never prayer requests, member data, pastoral notes, giving records, or volunteers' personal contacts.

## Commands
- Start: `ddev start` · Bootstrap: `ddev exec bash scripts/bootstrap.sh` · Seed: `ddev exec bash scripts/seed.sh`
- Tests: `powershell -File scripts\smoke-test.ps1` (all), `cd worker/sermon_flywheel; python -m pytest`, `ddev wp eval-file wp-content/plugins/asc-digital-ministry/tests/run-tests.php`
- Worker: `cd worker/sermon_flywheel; python -m sermon_worker.cli check|sync|process`
- Mobile check (every page at phone size, overflow/tap-target report + screenshots in `tmp/shots/mobile`): `python scripts/mobile-audit.py [--width 768] [--chat]`
- Deploy plugin to live (lint, backup, swap): `bash scripts/deploy/push-plugin.sh`
- Git Bash on Windows: prefix container paths with `MSYS_NO_PATHCONV=1`.
