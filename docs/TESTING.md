# Testing

This document describes the tests that **exist** in the repository, how to run them, and what they do not cover.
Recommendations are kept in a separate, clearly labelled section at the end.

## Summary

| Suite | Location | Framework | Tests | Result observed |
|---|---|---|---|---|
| Backend integration | `backend/tests/` | pytest 9.1.1 + FastAPI `TestClient` (httpx 0.28.1), against a real PostgreSQL database | 186 | **186 passed** (9 warnings) |
| Frontend unit | `frontend/src/lib/status.test.js`, `frontend/src/services/apiClient.test.js` | Node.js built-in `node:test` | 6 | **6 passed** |
| Frontend build | `npm run build` (Vite) | | | Build succeeded |

The results above were observed on the development machine (Windows, Python 3.13.15, Node 24.20.0,
PostgreSQL 18.6) when this documentation was written. They are a record of that run, not a guarantee for other
environments.

The 7 backend warnings are deprecation notices:
- Pydantic warns about the class-based `Config` used by five request models in `backend/main.py`.
- Starlette's test client warns about using `httpx`.

## Running the tests

**Backend.** Run from `backend/` with the virtual environment active (see [SETUP.md](SETUP.md#12-run-the-tests)):

```powershell
python -m pytest tests -q      # whole suite
python -m pytest tests -v      # one line per test
python -m pytest tests/test_status_rules.py -k delivered   # a subset
```

**Frontend:**

```powershell
cd frontend
node --test src/lib/status.test.js
npm run build
```

There is no `npm test` script in `package.json`.

## Backend test configuration

`backend/tests/conftest.py` builds an **isolated, disposable database** for every pytest session:

1. It reads `TEST_DATABASE_URL` from the environment or, if that is unset, `DATABASE_URL` from `backend/.env`,
   replacing the database name with **`logitrack_test`**.
2. **Safety check:** it refuses to run unless the database name ends in `_test`, so the development database cannot
   be used by accident.
3. It runs `DROP DATABASE IF EXISTS logitrack_test WITH (FORCE)` and `CREATE DATABASE`, which needs the `CREATEDB`
   privilege and PostgreSQL 13 or newer.
4. It loads `database/schema.sql` (skipping `psql` meta-commands such as `\restrict`), then every file in
   `database/migrations/` in name order.
5. It sets `DATABASE_URL` for the app to the test database **before** importing `main`.
   `JWT_SECRET_KEY` comes from `.env` or a test-only fallback.

Per test:
- An autouse fixture **truncates every table** (`RESTART IDENTITY CASCADE`) and inserts the five roles `ADMIN`,
  `OPERATIONS_MANAGER`, `DRIVER`, `CUSTOMER` and `WAREHOUSE_MANAGER`.
- A `Factory` fixture (`make`) builds only the rows each test needs: users with JWTs, customers, warehouses,
  products, stock, routes, vehicles, drivers with vehicle assignments, and "legacy" orders without reservations.
- `seed.sql` is not used by these fixtures; `test_database_setup.py` loads it separately (see below).

Because the schema comes from the real SQL files, the tests exercise the real CHECK constraints, partial unique
index, triggers and stored functions.

## What each backend suite covers

### `test_fulfilment.py` (22 tests): checkout, reservations, payment and fulfilment

| Area | Tests |
|---|---|
| Checkout and reservations | Reservation recorded and stock deducted; checkout failure (insufficient stock, and a forced failure after the reservation is written) rolls back stock, reservations and the order; one order supplied by several warehouses, choosing the origin with the most units. |
| Payment simulator | Successful payment creates exactly one shipment, a tracking event and a delivery; repeated success is idempotent; failed payment creates nothing and a later success works. |
| Missing data | Orders without reservations (approval refused until stock is recovered) or with incomplete reservations (`RESERVATION_INCOMPLETE`). A missing route is not an error: the order ships without one. |
| Driver assignment | No eligible driver, parametrised over six ineligibility reasons; vehicle shared with another driver; least-loaded driver chosen; operations assigning later via `POST /shipments/{id}/assign-driver`. |
| Security | Unauthenticated and wrong-role requests; one customer cannot pay for another customer's order. |
| Concurrency | Six simultaneous successful payments produce one shipment; simultaneous driver assignment produces one delivery. |

### `test_shipment_rules.py` (34 tests): one active shipment per order, route selection

| Area | Tests |
|---|---|
| Partial unique index | The database rejects a second active shipment (cancelled duplicates are allowed); `POST /shipments` returns 409 for a duplicate; other integrity errors are not reported as duplicates. |
| Cancellation | A cancelled shipment can be replaced; payment replaces only cancelled shipments and respects an existing active shipment. |
| Concurrency | Concurrent `POST /shipments` lets exactly one succeed. Concurrent payment and manual creation leave one active shipment; this is repeated five times and is a regression test for a deadlock. |
| Route matching | Valid destination matches (case-insensitive, PIN codes, street-name false matches); unmatched, same-city, inactive and ambiguous routes simply leave the shipment without a route (no estimate), and the paid order still ships. |

### `test_status_rules.py` (21 tests): shipment and delivery status consistency

| Area | Tests |
|---|---|
| Single source of truth | Tracking progression keeps the delivery in step; a driver's `/shipments`, `/deliveries` and timelines agree for every shipment; the delivery endpoint moves the shipment too. |
| Valid transitions | Checkpoint events and skipped stages; failed attempt then successful retry; cancellation from an open stage. |
| Invalid transitions | Backward moves rejected on all three endpoints (parametrised); `FAILED` only during a delivery attempt; a delivery cannot be set back to `PENDING`; invalid status (422) and missing delivery (404). |
| Closed shipments | `DELIVERED` and `CANCELLED` shipments cannot change through any endpoint, with history intact. |
| Database-level bypasses | Direct `UPDATE`, the stored procedure `update_shipment_status`, direct `INSERT` into tracking, and incompatible delivery rows are all rejected with SQLSTATE `LT409`. |
| Concurrency | Eight concurrent "delivered" confirmations record one event; concurrent deliver and cancel leave a consistent result. |
| Access rules | Drivers are limited to their assigned shipments. |
| Migration 003 | Reconciles legacy inconsistent delivery rows without changing tracking history. |

### Frontend `apiClient.test.js` (2 tests)

API error text: plain messages pass through; validation arrays, database text and bare status codes become friendly sentences.

### Frontend `status.test.js` (4 tests)

These cover `frontend/src/lib/status.js`, the shared status definitions used by the Dashboard, Deliveries and
Tracking pages:
- every delivery falls in exactly one group, and the groups add up to the total;
- the dashboard's "open" count agrees with the delivery board;
- unknown statuses are not dropped;
- tracking options never go backwards, and closed shipments offer none.

### `test_api_fixes.py` (20 tests): API defects found while documenting the project

| Area | Tests |
|---|---|
| Search routes | `GET /orders/search` and `GET /customers/search` are reachable and filter; numeric IDs still reach the detail routes; a non-numeric ID matches no route (404). |
| Missing records | 14 endpoints (parametrised) return 404 with `{"detail": "... not found"}` instead of 200 with an error body. |
| Database errors | Duplicate payment and duplicate stock row return 409; a bad foreign key, an invalid order status, a negative capacity and a malformed interval return 422; the message names the rule and contains no SQL. |
| Driver access | A driver can read only their own order, shipment details and shipment search results; another driver gets 403 or an empty list. |
| Defaults | Registration fills `users.created_at`; `POST /shipments` fills `shipment_date`; route duration is returned as text by both `POST /routes` and `GET /routes`. |
| Migration 004 | The database rejects a shipment item whose order is not the shipment's order. |
| `set_demo_passwords.py` | Replaces only placeholder hashes (a real hash is untouched unless `include_real_hashes`), rejects short passwords, and the new password logs in. |

### `test_models_match_schema.py` (24 tests): models equal the database

One test per table plus one for the table list. Each compares the SQLAlchemy model with the schema built from the SQL
files: columns, nullability, server defaults, primary key, foreign keys, unique constraints, CHECK constraint names
and indexes. It fails if either side changes without the other. Run against the previous `models.py` it fails for
21 of its 22 checks.

### `test_route_independence_and_recovery.py` (14 tests): routes are optional; stock recovery

A paid order with no matching route (or no routes at all) is approved, assigned and delivered; a route is recorded only when exactly one matches;
retry works without a route; unpaid and failed-payment orders cannot be approved or shipped, and `POST /shipments` cannot bypass payment;
customers never see allocation or route wording; for a paid order that predates reservations, recovery reserves exactly the order items, does not
approve it or change its status, needs explicit confirmation, reserves nothing on insufficient stock (and the exception stays visible), requires a
genuine successful payment, is idempotent, and is safe under concurrency (one reservation for repeated attempts; two orders cannot take the last
unit); shipments that predate approvals make no approval claim.

### `test_demo_seed_and_approval.py` (14 tests): demo seed, approval sequence, customer wording

Seed idempotency and dry run, every warehouse stocked while existing rows stay identical, demo drivers/vehicles meet the
schema rules (argon2 hash, unexpired licence, one current vehicle each, nothing dispatched), the seed never touches
existing drivers or passwords and refuses production; available/reserved/on-hand figures agree with persisted data and
cannot be oversold; the catalogue counts only sellable stock; payment alone creates no shipment, approval rules (unpaid,
customer, cancelled, repeated), approval assigns a real fleet pair, conflicting assignments are rejected, and customers
see calm stages while staff see the exact allocation reason and can resolve it.

### `test_fulfilment_workflow.py` (32 tests): automated fulfilment

Planning at checkout, destination-city routing and service areas, blocked plans and idempotent retry, dispatch only
after successful payment (vehicle persisted), failed payment never dispatches, cancellation and abandonment release
stock exactly once (also concurrently), warehouse choice (stock, status, route) and split-order notes, vehicle
capacity, driver open-delivery limit, manual assign/reassign rules, concurrency (no overselling, no double allocation
of a driver or vehicle), order-status sync, role-scoped tracking, warehouse overview numbers, and the shipment desk
(search, filter, sort, pagination, pending/blocked visibility, honest reporting of legacy mismatches).

### `test_database_setup.py` (5 tests): seed and migration order

Builds scratch databases (`logitrack_setupcheck_test`, dropped afterwards) and checks that:
- `seed.sql` loads and leaves a usable database in **both orders** (schema, seed, migrations and schema, migrations, seed): the expected row counts, historical statuses loaded as written, no trigger left disabled, ID sequences past the seeded rows, and the status rules active afterwards;
- migration 004 refuses to install over inconsistent data (changing nothing) and is safe to run twice;
- migration 005 changes no existing data and is safe to run twice;
- migrations 006 and 007 change no existing data, are safe to run twice, and 007 allows a shipment without a route while the foreign key still rejects a route that does not exist.

## Known gaps (current state)

These are **not** covered by any test in the repository:

- **Frontend components.** There are no component, rendering or browser end-to-end tests, and no test runner such
  as Vitest or Playwright is configured. Only `status.js` has unit tests.
- **Most generic CRUD endpoints** (products, warehouses, vehicles, maintenance, routes, employees, users, roles,
  invoices) have only the error-handling tests above, not tests of their normal behaviour.
- **Analytics and dashboard endpoints** have no tests.
- **Authentication details**: registration validation, profile updates, password change, inactive users and token
  expiry are not tested beyond the general 401/403 checks.
- **The remaining known issues** in [API_DOCUMENTATION.md](API_DOCUMENTATION.md#known-issues) are not tested
  (unvalidated free-text status values, order status not synchronised with shipment status).
- **`backend/seed_shop_products.py`** is not exercised by the tests (it was run manually on a fresh database).
- **No continuous integration** configuration exists, so tests run only when someone runs them.

## Recommended additions (not implemented)

These are suggestions only; none exist in the repository:

1. Add tests for the normal behaviour (not only the errors) of the generic CRUD endpoints.
2. Add a frontend component test setup (for example Vitest with React Testing Library) for Shop checkout and the
   payment simulator.
3. Add a CI workflow that starts PostgreSQL, runs `pytest`, `node --test` and `npm run build`.
4. Add tests for the analytics endpoints.
