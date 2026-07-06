# Final Demo Script - Bristol Food Marketplace Resit

## 1. Start And Introduce

Open the project folder:

```powershell
cd C:\Users\dchin\Documents\bristol-food-marketplace-resit
docker compose up --build
```

Open:

```text
http://localhost:8001
```

Short introduction:

> This is my solo resit implementation of the Bristol Regional Food Network digital marketplace. The system uses Django, PostgreSQL, Redis, Celery and Docker. It supports local producers, customers, recurring orders, test-case evidence, and admin reporting.

## 2. Customer Demo

Login:

```text
cust1 / customer1
```

Show:

1. Market page.
2. Search for a product, for example `tomatoes`.
3. Filter by category, organic status, season, or allergens.
4. Show food miles, allergen warnings, producer information, stock and prices.
5. Add products to basket.
6. Open basket and show checkout form.
7. Show order history and reorder.
8. Show recurring orders.
9. Show recipes.

Test cases covered: TC-004, TC-005, TC-006, TC-007, TC-008, TC-013, TC-014, TC-015, TC-018, TC-021.

## 3. Producer Demo

Logout, then login:

```text
prod1 / producer1
```

Show:

1. Add/edit product page.
2. Product fields: category, price, stock, low-stock threshold, organic status, allergens, seasonal availability, surplus discount.
3. Incoming orders.
4. Completed orders.
5. Customer reviews.
6. Settlements and 5% commission deduction.
7. My Recipes.
8. My Bio.
9. Notifications.

Test cases covered: TC-001, TC-003, TC-009, TC-010, TC-011, TC-012, TC-016, TC-019, TC-020, TC-023, TC-024.

## 4. Admin Demo

Logout, then login:

```text
admin1 / admin123
```

Show:

1. Admin dashboard.
2. Profiles.
3. Order history.
4. Reports and commission totals.

Test cases covered: TC-022, TC-025.

## 5. Formal Test Evidence

Run:

```powershell
docker compose exec -e USE_SQLITE_FOR_TESTS=1 web python src/manage.py test marketplace
```

Expected result:

```text
Found 17 test(s).
...............
OK
```

Open:

```text
docs/task2-test-evidence.md
```

Explain:

- The formal Django test suite passes 17/17.
- TC-017 has a dedicated community group / bulk checkout path with group name, people supplied, and delivery notes.
- TC-020 has recipes plus a dedicated farm-story module producers can publish and customers can browse.

## 6. Submission Files To Mention

- `README.md` - setup, Docker ports, demo accounts and test command.
- `docs/task2-test-evidence.md` - TC-001 to TC-025 evidence matrix.
- `docs/Danai_Chinyani_Solo_Contribution_Matrix.docx` - solo contribution matrix, to complete with student ID/signature.
- `docker-compose.yaml` - containerised deployment.
- `src/marketplace/tests.py` - automated tests.
