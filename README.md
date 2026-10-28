# JudgeAI

Local assistant for reviewing draft criminal verdicts. The legal rules produce candidates for human review; they do not make judicial decisions.

## Components

- `src/`: FastAPI API, document extraction, asynchronous analysis, PostgreSQL persistence and precedent search.
- `packages/legal_core/`: dependency-free rules for art. 15 and art. 18, with sources and tests.
- `verdikt-web/`: React cabinet using the live API; the landing page retains illustrative demo data.

## Run locally

Python 3.11+; Node 20.19+ or 22.12+; Docker Compose.

1. Copy `.env.example` to `.env` and configure your local database and LLM settings.
2. For tests only, set `LLM_PROVIDER=fake` together with `LLM_ALLOW_FAKE=true` (without the flag the service refuses the fake model and reports an error). This returns a fixed example, independent of the input, and the result is labelled as development data.
3. Start the backend with `docker compose up --build`. For development/test tools, build with `docker compose build --build-arg INSTALL_DEV=true api` first.
4. In `verdikt-web`, run `npm ci` and `npm run dev`. Open the displayed local URL and `/app`.

The web development server proxies `/api` to `http://localhost:8000`. Set `API_PROXY_TARGET` to use a different local API. Production hosting needs a corresponding reverse proxy; Vite's development proxy is not part of the static build.

For direct Python development, install both local packages: `pip install -e '.[dev]' -e 'packages/legal_core[dev]'`.

## Working flow

Create a case with text and/or files -> upload originals as multipart `files` -> receive `202` -> poll messages until `completed` or `failed` -> display the stored `result`. Reloading the case restores its result. Hiding progress leaves the server analysis running. Each request includes only its own attachments; attach previous documents again to include them in a new request.

Supported uploads: PDF with text layer, DOCX, TXT, MD; default limit 50 MB per file. Image OCR and DOCX tables are not implemented. Extraction errors are reported in the result.

## Verification

- API: `docker compose run --rm api pytest`. Tests recreate a database ending in `_test`; they must never target the working database. Set `TEST_POSTGRES_DB` to a dedicated name if other test runs exist.
- Python lint: `ruff check src tests packages/legal_core`.
- Core: from `packages/legal_core`, `pytest` (includes coverage threshold 80%).
- Web: from `verdikt-web`, `npm test` (Node 22.18+ or 24 for built-in TypeScript execution), `npm run build`.
- Browser: the Playwright CLI function files in `verdikt-web/tests/browser/` exercise a local web server at `127.0.0.1:5178` against a dedicated API/database with fake LLM. Open that URL in a named CLI session, then use `run-code --filename=...`. They create synthetic test cases. Run `local-flow.js`, `error-flow.js`, `navigation-flow.js` and `request-files-flow.js`; screenshots are saved under `/tmp/judgeai-{desktop,mobile}.png`.

Verified on 2026-10-27: 42 API tests, 30 core tests, core coverage 99.2%, 3 web adapter tests, production build, desktop/mobile upload/result/reload and network/404/415 flows. Browser results use the fake provider, not a real model.

## Explicit limits

- No login or ownership isolation yet. The current API exposes a shared set of cases.
- No anonymizer yet. A real LLM receives the supplied text; the local demonstration uses only synthetic material.
- The model context is capped at 30,000 document characters across the request. Omitted text is reported; the result does not cover the complete documents when capped.
- All text chunks are stored; only the first `EMBEDDING_MAX_CHUNKS` receive vectors. The currently configured embedding model is unsupported by the installed FastEmbed registry, so search uses a keyword fallback until a compatible model is configured and the corpus reindexed. Existing vector dimensions must be preserved or migrated explicitly.
- Exact quotes establish provenance, not semantic truth. Categories, applicable law edition and prior conviction status must be checked by a person. Missing evidence or incomplete history yields `insufficient_data`.
- Legal checks are additive fields of the existing `schema_version=1` result. No database migration is needed for this change. Installing `legal_core` is required by the API; the Dockerfile installs it.
- Background jobs are in-process; restart marks unfinished jobs as failed. A durable queue, retry and cancellation are future work.
- DOCX export remains an explicit disabled stub. Real LLM quality, OCR, vector relevance and production deployment are not validated by these tests.

## Legal-source library

Structured sanctions of УК РФ (T5) are derived from the imported official text: `python -m src.cli.criminal_sanctions import`, then `GET /api/legal/sanctions?article=158&part=2`. The analysis uses them for the sanction maximum, ст. 15 category and the check of the imposed term (sanction bounds, ч. 1 ст. 62). See [docs/LEGAL_LIBRARY.md](docs/LEGAL_LIBRARY.md).

The criminal-pilot source library, additive migration, trusted import commands, read-only API and local corpus counts are documented in [docs/LEGAL_LIBRARY.md](docs/LEGAL_LIBRARY.md). Technical import is deliberately separate from legal verification: unreviewed sources cannot answer a verified date lookup. No automatic switch of the existing analysis engine to unreviewed legislation is performed.

Реестр зависимостей, лицензий и границ воспроизводимости T19: [docs/compliance/README.md](docs/compliance/README.md). Офлайн-проверка актуальности: `python3 tools/dependency_inventory.py --check`.


## Local authentication

Local account provisioning, ownership migration and rollback precautions: [docs/AUTH.md](docs/AUTH.md). All task status and validation evidence: [docs/TASKS.md](docs/TASKS.md).
