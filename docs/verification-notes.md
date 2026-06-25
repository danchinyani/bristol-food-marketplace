# Verification Notes

Date checked: 25 June 2026.

## Automated Checks

- `python src/manage.py check` passed with no issues.
- `python src/manage.py test marketplace` passed: 13 tests run, 13 passed.

The test run used `USE_SQLITE_FOR_TESTS=1` so local checks can run without Docker/PostgreSQL/Redis. Docker remains configured to use PostgreSQL and Redis for the actual application.

## Fixes Made During Setup

- Added a clean `.env.example`.
- Added `.gitignore` for local environment, cache, database, and media files.
- Added a solo-resit README with Docker instructions.
- Added local SQLite test switch for easier automated checks.
- Added eager Celery mode during local tests so notification tasks do not require Redis.
- Fixed recurring checkout creation from the checkout form.
- Fixed producer order views so templates receive one-off, recurring, and completed order data correctly.
- Updated existing tests to match current seasonal/allergen product fields.

## Next Manual Demo Checks

- Run with Docker using `docker compose up --build`.
- Seed sample data with `docker compose exec web python src/manage.py seed_data`.
- Walk through TC-001 to TC-009, TC-012, TC-015, and TC-022 first.
- Prepare screenshots or notes for any test case demonstrated verbally.

