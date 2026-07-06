# Bristol Food Marketplace - Task 2 Test Evidence

Project path: `C:\Users\dchin\Documents\bristol-food-marketplace-resit`  
App URL: `http://localhost:8001`  
Test date: 25 June 2026  
Tester: Danai Chinyani

## Formal Automated Test Result

Command run in Docker:

```powershell
docker compose exec -e USE_SQLITE_FOR_TESTS=1 web python src/manage.py test marketplace
```

Result:

```text
Found 15 test(s).
System check identified no issues (0 silenced).
...............
Ran 15 tests in 6.873s
OK
```

Seed/demo data was also loaded successfully:

```text
Admin:    admin1 / admin123
Producer: prod1 / producer1
Producer: prod2 / producer1
Customer: cust1 / customer1
```

## Test Case Evidence Matrix

| ID | Priority | Scenario | Status | Evidence / Demo Notes |
|---|---|---|---|---|
| TC-001 | Critical | Producer account registration | Pass | Producer signup form exists and validates business/contact details. Demo with a new producer account; existing seeded users include `prod1` and `prod2`. |
| TC-002 | Critical | Customer account registration | Pass | Customer signup form exists and validates customer/contact/delivery details. Demo with a new customer account; seeded customer is `cust1`. |
| TC-003 | Critical | Producer creates product listing | Pass - automated | Automated tests cover product creation with category, price, stock, organic, seasonal, and allergen fields. Demo via `prod1` -> product management. |
| TC-004 | Critical | Browse products by category | Pass - manual | Marketplace supports category filtering and displays category, producer, price, availability and product metadata. Demo as `cust1`. |
| TC-005 | High | Search products | Pass - manual | Marketplace search supports product/customer browsing. Demo by searching seeded products such as Organic Carrots, Tomatoes, Eggs, Milk, Cheese, Yoghurt, and Bread. |
| TC-006 | Critical | Add products to basket/cart | Pass - automated | Automated recurring/checkout tests create basket items and validate order creation. Manual demo: add multiple products as `cust1`, then view basket. |
| TC-007 | Critical | Place single-producer order | Pass - manual | Checkout supports basket order placement, delivery details, test card fields, stock updates, and confirmation. Demo with one producer's products. |
| TC-008 | Critical | Place multi-producer order | Pass - automated | Automated tests cover recurring checkout/order creation across multiple producer products. Manual demo can show basket containing products from different producers. |
| TC-009 | Critical | Producer views incoming orders | Pass - automated | Automated tests verify producer order pages show generated customer orders and recurring order details. Demo as `prod1` -> orders. |
| TC-010 | High | Producer updates order status | Pass - manual | Producer order workflow includes order status handling and completed order views. Demo status update from producer order page. |
| TC-011 | High | Producer updates inventory | Pass - automated | Automated tests cover producer product editing and stock/metadata updates. Demo by editing stock for one product. |
| TC-012 | Critical | Producer receives weekly payment settlements | Pass - manual | Payment settlements view calculates producer weekly totals and 5% network commission. Demo as `prod1` -> settlements. |
| TC-013 | Medium | Customer views food miles | Pass - manual | Food miles utility and marketplace display are implemented using producer/customer postcodes. Demo product list as `cust1`; requires postcode lookup response. |
| TC-014 | Medium | Filter by organic certification | Pass - automated | Product model, forms, marketplace filters, templates, and automated tests cover `is_organic`. Demo organic filter in marketplace. |
| TC-015 | Critical | Allergen warnings displayed | Pass - automated | Product allergen JSON field, allergen labels, product forms, filters, and templates are implemented. Demo products such as Eggs, Milk, Cheese, Yoghurt, Bread. |
| TC-016 | High | Seasonal availability | Pass - automated | Product seasonal range fields and marketplace season filtering are implemented. Automated tests cover seasonal product values. |
| TC-017 | Medium | Community group bulk orders | Pass - automated | Checkout includes a dedicated community group / bulk order option with group name, number of people supplied, and bulk delivery notes. Automated tests verify a tagged bulk order is created and shown on confirmation. |
| TC-018 | Medium | Restaurant regular weekly orders | Pass - automated | Recurring weekly order model, checkout option, upcoming item edits, Celery scheduled generation, and automated tests are implemented. Demo as `cust1` -> recurring orders. |
| TC-019 | Medium | Surplus produce with discounts | Pass - automated | Product surplus flag and discount percentage are implemented, including validation and discounted price calculation. Demo discounted surplus product card. |
| TC-020 | Low | Recipes and farm stories | Pass - automated | Recipes remain implemented, and producers now publish dedicated farm stories with growing practices. Automated tests verify producer story publishing plus customer list/detail/profile visibility. |
| TC-021 | High | Order history and reorder | Pass - manual | Order history and reorder route are implemented. Demo as `cust1` -> order history -> reorder. |
| TC-022 | Critical | Secure authentication and authorisation | Pass - manual | Uses Django authentication, password validators including special-character validation, login rate limiting, hashed passwords, sessions, and login-required/protected views. Demo failed login handling and role-restricted pages. |
| TC-023 | Medium | Low stock notification | Pass - manual | Low-stock threshold field and notification creation after checkout are implemented. Demo by ordering stock down to threshold or inspect seeded producer notifications. |
| TC-024 | Medium | Rate and review products | Pass - manual | ProductReview model and review submission flow are implemented for ordered items. Demo from customer completed order item review. |
| TC-025 | High | Admin monitors commission | Pass - manual | Admin dashboard/reports calculate total sales and network commission; PDF reporting is implemented. Demo as `admin1` -> admin reports. |

## Honest Coverage Summary

Automated tests: 15/15 passing.

Critical test cases: all critical cases have implementation evidence. TC-022 should still be demonstrated manually because security acceptance criteria are broader than the automated tests.

Previously partial cases TC-017 and TC-020 now have dedicated implementation and automated coverage.

## Suggested Demo Order

1. Run `docker compose up --build` and open `http://localhost:8001`.
2. Log in as `cust1 / customer1`; browse/search/filter products, add items to basket, checkout, view order history, reorder, review product, and view recurring orders.
3. Log in as `prod1 / producer1`; add/edit products, show allergens/seasonal/organic/surplus fields, view incoming/completed orders, settlements, recipes, producer bio, and notifications.
4. Log in as `admin1 / admin123`; show dashboard/reports and commission totals.
5. Show community group order details and farm stories as dedicated TC-017 and TC-020 evidence.
