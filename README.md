# Bristol Regional Food Network Marketplace

Solo resit project for UFCFTR-30-3 Distributed and Enterprise Software Development.

This Django/Docker application implements a digital marketplace for local Bristol-area food producers and customers. It supports producer and customer registration, product listings, category browsing, search, basket checkout, multi-producer orders, producer order management, settlements, security controls, food miles, surplus discounts, recipes, order history, reviews, recurring orders, notifications, and admin reports.

## Run With Docker

1. Create a local environment file:

```bash
cp .env.example .env
```

On Windows PowerShell, use:

```powershell
Copy-Item .env.example .env
```

2. Build and start the containers:

```bash
docker compose up --build
```

3. In another terminal, load demo data if needed:

```bash
docker compose exec web python src/manage.py seed_data
```

4. Open the application:

```text
http://localhost:8001
```

## Demo Accounts

Use usernames, not email addresses:

| Role | Username | Password |
|---|---|---|
| Admin | `admin1` | `admin123` |
| Producer | `prod1` | `producer1` |
| Producer | `prod2` | `producer1` |
| Customer | `cust1` | `customer1` |

## Services

The host ports avoid common local conflicts:

- `web`: Django application at `http://localhost:8001`
- `db`: PostgreSQL 15 on host port `5433`, container port `5432`
- `redis`: Redis broker on host port `6380`, container port `6379`
- `celery`: background worker and scheduler for recurring orders
- `adminer`: database viewer at `http://localhost:8081`

## Tests

Run the formal Django test suite with deterministic test settings:

```bash
docker compose exec -e USE_SQLITE_FOR_TESTS=1 web python src/manage.py test marketplace
```

Latest verified result:

```text
Found 17 test(s).
System check identified no issues (0 silenced).
.................
Ran 17 tests in 31.049s
OK
```

Additional assessment evidence is documented in:

```text
docs/task2-test-evidence.md
```

## Assessment Notes

- This resit uses the same Bristol Regional Food Network case study and the same TC-001 to TC-025 test cases as the original assessment.
- Payment features use test/simulated payment data only.
- Source code, Docker setup, README, commit history, and signed contribution matrix are required for Task 2.
- As this is a solo resit project, the contribution matrix should record Danai Chinyani as responsible for 100% of the work, with evidence from commits and project tasks.
- If AI assistance is declared, state that it was used for planning, review, debugging support, styling guidance, and drafting guidance, then check the university rules before submission.

## Local Test Option

If you want to run the Django tests without Docker:

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
set USE_SQLITE_FOR_TESTS=1
.venv\Scripts\python src\manage.py test marketplace
```
