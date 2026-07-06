# Task 2 Resit Checklist

Deadline: 13 July 2026 before 14:00 UK time.

## Verified Core Evidence

- [x] Docker stack runs with web, PostgreSQL, Redis, Celery, and Adminer
- [x] App opens at `http://localhost:8001`
- [x] Demo data can be loaded with `docker compose exec web python src/manage.py seed_data`
- [x] Formal Django tests pass: 15/15
- [x] Test-case evidence matrix created: `docs/task2-test-evidence.md`
- [x] Resit brief checked: test cases remain identical to original assessment
- [x] Solo resit position confirmed: group size can be 1 to 5 members

## Critical Test Cases

- [x] TC-001 producer registration
- [x] TC-002 customer registration
- [x] TC-003 producer product listing
- [x] TC-004 category browsing
- [x] TC-006 basket management
- [x] TC-007 single-producer checkout
- [x] TC-008 multi-producer checkout
- [x] TC-009 producer incoming orders
- [x] TC-012 weekly settlements
- [x] TC-015 allergen warnings
- [x] TC-022 secure authentication and authorisation

## High Priority Test Cases

- [x] TC-005 search
- [x] TC-010 order status updates
- [x] TC-011 inventory updates
- [x] TC-016 seasonal availability
- [x] TC-021 order history and reorder
- [x] TC-025 admin commission reporting

## Medium/Low Priority Test Cases

- [x] TC-013 food miles
- [x] TC-014 organic filtering
- [x] TC-017 community group bulk orders - dedicated checkout fields capture group name, people supplied, and bulk delivery notes
- [x] TC-018 recurring restaurant orders
- [x] TC-019 surplus produce discounts
- [x] TC-020 recipes and farm stories - recipes plus dedicated producer farm stories are implemented
- [x] TC-023 low stock notifications
- [x] TC-024 product reviews

## Final Submission Items Still To Prepare

- [ ] Public GitHub/GitLab repository link
- [ ] Commit history showing solo contribution
- [ ] Signed contribution matrix with Danai Chinyani recorded as 100%
- [ ] Final presentation/demo plan
- [ ] Screenshots or live demo evidence of Docker running and test suite passing
- [ ] AI-use declaration, if required by UWE guidance

## Suggested Demo Sequence

1. Start Docker with `docker compose up --build`.
2. Open `http://localhost:8001`.
3. Customer demo with `cust1 / customer1`: browse, filter, search, basket, checkout, order history, reorder, reviews, recurring orders.
4. Producer demo with `prod1 / producer1`: products, inventory, allergens, seasonal availability, surplus discounts, incoming/completed orders, settlements, recipes, bio, notifications.
5. Admin demo with `admin1 / admin123`: dashboard, profiles, orders, reports, commission.
6. Run `docker compose exec -e USE_SQLITE_FOR_TESTS=1 web python src/manage.py test marketplace`.
7. Demonstrate TC-017 community group checkout and TC-020 farm stories directly.
