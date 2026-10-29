# Generated dependency inventory

Source inventory only; not a resolved runtime SBOM or legal approval.

- Python declared packages (runtime/dev/build, deduplicated): **20**; exact installed versions: **0 verified**.
- npm lock entries: **139**; development entries: **118**.
- Official legal archives: **8**; image declarations: **2**; model: **sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2**, revision unresolved.

## npm license metadata

| Declaration | Entries |
|---|---:|
| 0BSD | 1 |
| Apache-2.0 | 3 |
| BSD-3-Clause | 1 |
| CC-BY-4.0 | 1 |
| ISC | 5 |
| MIT | 128 |

## Python declarations

| Package | Constraints (not installed versions) | Upstream license |
|---|---|---|
| alembic | alembic>=1.13.1 | MIT |
| argon2-cffi | argon2-cffi>=23.1.0 | MIT |
| asyncpg | asyncpg>=0.29.0 | Apache-2.0 |
| fastapi | fastapi>=0.110.0 | MIT |
| fastembed | fastembed>=0.3.0 | Apache-2.0 |
| httpx | httpx>=0.27.0 | BSD-3-Clause |
| pdfplumber | pdfplumber>=0.11.0 | MIT |
| pgvector | pgvector>=0.3.0 | MIT |
| pydantic | pydantic>=2.6.0 | MIT |
| pydantic-settings | pydantic-settings>=2.2.1 | MIT |
| pytest | pytest>=8.0 | MIT |
| pytest-asyncio | pytest-asyncio>=0.24 | Apache-2.0 |
| pytest-cov | pytest-cov>=5.0 | MIT |
| python-docx | python-docx>=1.1.0 | MIT |
| python-multipart | python-multipart>=0.0.9 | Apache-2.0 |
| ruff | ruff>=0.6 | MIT |
| setuptools | setuptools>=68 | MIT |
| sqlalchemy | sqlalchemy[asyncio]>=2.0.29 | MIT |
| uvicorn | uvicorn[standard]>=0.29.0 | BSD-3-Clause |
| wheel | wheel | MIT |

## Document preview runtime

- LibreOffice Writer: MPL-2.0; incorporated Apache-2.0 and additional bundled notices. Built Debian bookworm preview image: /usr/share/doc/libreoffice-common/copyright; primary notice inspected, transitive notices remain in image
- Liberation fonts: GPL version 2 with the font embedding and distribution exceptions in the package notice. Built Debian bookworm preview image: /usr/share/doc/fonts-liberation/copyright; primary notice inspected, transitive notices remain in image
- DejaVu fonts: Bitstream Vera license; DejaVu changes are public domain. Built Debian bookworm preview image: /usr/share/doc/fonts-dejavu-core/copyright; primary notice inspected, transitive notices remain in image
- Carlito fonts: OFL-1.1. Built Debian bookworm preview image: /usr/share/doc/fonts-crosextra-carlito/copyright; primary notice inspected, transitive notices remain in image
- Caladea fonts: OFL-1.1. Built Debian bookworm preview image: /usr/share/doc/fonts-crosextra-caladea/copyright; primary notice inspected, transitive notices remain in image

## Open decisions and release blockers

- Python direct dependencies are declared ranges; resolved transitive versions and wheel hashes are not captured.
- Container tags and OS/build dependencies are not pinned to immutable image digests and package snapshots.
- Model revision and weight hashes are not pinned; remote service model identity is not a local open-source weight license.
- npm license fields are lockfile metadata; installed package notices and redistribution obligations still need release review.
- No project LICENSE is selected; owner approval is required before choosing or publishing one.
- No external corpus permissions, private sample redistribution or production-provider privacy approval is granted by this inventory.

Regenerate: `python3 tools/dependency_inventory.py`; verify: `python3 tools/dependency_inventory.py --check`.
