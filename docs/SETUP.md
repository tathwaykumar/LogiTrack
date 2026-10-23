# Setup Guide (Windows)

This guide takes you from a fresh clone to a running LogiTrack with sample data. Commands are for
**Windows PowerShell**.

**How the steps were verified.** The whole database sequence (schema, seed, the migrations, the shop seed
script, `set_demo_passwords.py`, then logging in as all four roles, signing up, and placing and paying for an
order) was run on a fresh database. `pip install -r requirements.txt` was checked in a brand-new virtual
environment. The start commands, the API docs URL and the Vite dev server were checked against this repository.
The `psql` invocations themselves were **not** run on the verification machine, because `psql` was not on its
`PATH`; they load the same files, in the same order, that the verification loaded through Python.

---

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone the repository](#2-clone-the-repository)
3. [Create the database](#3-create-the-database)
4. [Configure the backend environment](#4-configure-the-backend-environment)
5. [Install backend dependencies](#5-install-backend-dependencies)
6. [Seed and migrate the database](#6-seed-and-migrate-the-database)
7. [Add the shop demo products](#7-add-the-shop-demo-products)
8. [Give the seeded accounts a password](#8-give-the-seeded-accounts-a-password)
9. [Install frontend dependencies](#9-install-frontend-dependencies)
10. [Start the application](#10-start-the-application)
11. [Verify it works](#11-verify-it-works)
12. [Run the tests](#12-run-the-tests)
13. [Troubleshooting](#troubleshooting)

---

## 1. Prerequisites

| Tool | Version used during verification | Notes |
|---|---|---|
| Git | any recent | |
| Python | 3.13.15 | Other 3.x versions are untested. The code uses `str \| None` syntax, so 3.10 or newer is required. |
| Node.js / npm | 24.20.0 / 11.19.0 | Needed for Vite 8 and React 19. Older Node versions are untested. |
| PostgreSQL (server + `psql`) | 18.6 | `database/schema.sql` was dumped from PostgreSQL 18.6. The test suite uses `DROP DATABASE … WITH (FORCE)`, which needs PostgreSQL 13 or newer. |

During installation, note the password you set for the `postgres` superuser. The commands below assume `psql` is
on your `PATH`, typically `C:\Program Files\PostgreSQL\18\bin`. If it isn't, use the full path, for example
`& "C:\Program Files\PostgreSQL\18\bin\psql.exe" ...`.

## 2. Clone the repository

```powershell
git clone https://github.com/tathwaykumar/LogiTrack.git
cd LogiTrack
```

Run every later command from this `LogiTrack` folder unless a step says `cd backend` or `cd frontend`.

## 3. Create the database

```powershell
psql -U postgres -c "CREATE DATABASE logitrack_db;"
```

You can use another database name; just use the same name in `DATABASE_URL` in step 4.

> Using the `postgres` superuser is simplest. `schema.sql` contains `ALTER … OWNER TO postgres` statements; if you
> connect as a different role, those lines may print errors while the objects are still created (unverified).

## 4. Configure the backend environment

The backend reads two variables from `backend/.env` (via `python-dotenv`). Copy the template:

```powershell
Copy-Item backend\.env.example backend\.env
notepad backend\.env
```

Set both values:

```dotenv
DATABASE_URL=postgresql+psycopg2://postgres:<your-postgres-password>@localhost:5432/logitrack_db
JWT_SECRET_KEY=<a-long-random-secret>
```

To generate a suitable secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

- `backend/.env` is listed in `.gitignore`; never commit it.
- The backend refuses to start if either variable is missing (`RuntimeError: DATABASE_URL is required…`).
- The frontend needs no environment file.

## 5. Install backend dependencies

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
cd ..
```

- `requirements.txt` holds the pinned runtime packages (FastAPI, Uvicorn, SQLAlchemy, psycopg2-binary,
  python-dotenv, PyJWT and `pwdlib[argon2]`). `requirements-dev.txt` includes it and adds `pytest` and `httpx`.
  Install `requirements.txt` alone if you do not need the tests.
- If `Activate.ps1` is blocked, see [Troubleshooting](#troubleshooting).

## 6. Seed and migrate the database

Run these in this order, one after the other:

```powershell
psql -U postgres -d logitrack_db -f database/schema.sql
psql -U postgres -d logitrack_db -f database/seed.sql
psql -U postgres -d logitrack_db -f database/migrations/001_order_inventory_reservation.sql
psql -U postgres -d logitrack_db -f database/migrations/002_shipment_one_active_per_order.sql
psql -U postgres -d logitrack_db -f database/migrations/003_status_transition_rules.sql
psql -U postgres -d logitrack_db -f database/migrations/004_shipment_item_same_order.sql
psql -U postgres -d logitrack_db -f database/migrations/005_order_fulfilment_planning.sql
psql -U postgres -d logitrack_db -f database/migrations/006_operations_approval_and_demo_ledger.sql
psql -U postgres -d logitrack_db -f database/migrations/007_shipment_route_optional.sql
```

- `seed.sql` runs in a single transaction, loads the historical shipment data exactly as written, and advances
  every ID sequence past the seeded rows, so there is nothing else to run. It also works if you apply it *after*
  the migrations.
- The migrations are plain SQL using `IF NOT EXISTS` / `CREATE OR REPLACE`, so re-running any of them is safe.
  There is no migration-tracking table. Migrations 002 and 004 refuse to install, and change nothing, if existing
  data already breaks the rule they add.
- **Without sample data:** run `schema.sql` and the seven migrations only.
- **Migration 007** makes `shipment.route_id` nullable (a shipment no longer needs a configured route). It relaxes a constraint only and
  changes no row.
- **Migration 006** adds the Operations approval columns (`order_fulfilment.approved_at`, `approved_by_user_id`) and the
  `demo_seed_record` ledger. Paid orders that already exist are not marked approved, because their approval time is
  unknown. They appear in the operations "awaiting approval" list.
- **Migration 005** adds the fulfilment-planning tables and columns. It only adds; it changes no existing row, and
  existing orders and deliveries keep empty plan, vehicle and assignment-time fields rather than invented ones.
- **Optional settings** (read when the API starts, with safe defaults): `MAX_OPEN_DELIVERIES_PER_DRIVER` (default 3)
  and `UNPAID_ORDER_TTL_MINUTES` (default 1440, used by the operations “release abandoned orders” action).
  Restart the API after applying migration 005.

## 7. Add the shop demo products

`seed.sql` creates 8 products. This script adds 3 more (Portable Power Bank, Ergonomic Laptop Stand, Bluetooth
Speaker) with stock in the first active warehouse. It skips products that already exist.

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python seed_shop_products.py
cd ..
```

Expected output: `Added 3 Shop demo product(s).` A fresh setup therefore has **11** products.

`frontend/public/images/products` holds 12 photos. The extra *Smartphone* image is not used by any seeded product.

## 7b. Optional: demo drivers, vehicles and warehouse stock (development only)

`backend/seed_demo_data.py` adds a small demo fleet and makes sure every warehouse stocks some of the existing
catalogue, so allocation and the inventory screens have something to show:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python seed_demo_data.py --dry-run   # report only; changes nothing
python seed_demo_data.py             # prompts for the demo drivers' password (hidden)
```

- Adds up to 10 drivers (`demo_driver01`...`demo_driver10`, role DRIVER, names ending "(Demo)", `@demo.logitrack.example`
  addresses, fictional phone numbers, licence numbers `DEMO-DL-xxxx`) and 10 vehicles (`DEMO-FLT-001`...), each driver
  with one current vehicle. All are active and available; none is assigned to a shipment.
- Adds an inventory row only where a warehouse/product pair has none, until each warehouse stocks at least six
  products. Existing quantities are never changed. No products or warehouses are created.
- Re-running adds nothing. It only inserts: it never updates or deletes a row. Everything it adds is listed in
  `demo_seed_record`.
- The password is hashed with the application's own helper and is read from a hidden prompt or from the
  `LOGITRACK_DEMO_PASSWORD` environment variable. It is never stored in a file. Existing accounts keep their passwords.
- It refuses to run when `LOGITRACK_ENV` or `APP_ENV` is `production`.
- The schema has no link between drivers or vehicles and warehouses, no SKU column and no stock-movement table, so none
  of those are invented.

## 8. Give the seeded accounts a password

`seed.sql` creates these accounts, but contains **no passwords** (it stores placeholders such as `seed_hash_admin`),
so nobody can sign in until you set one:

| Username | Role |
|---|---|
| `admin01` | ADMIN |
| `manager01` | OPERATIONS_MANAGER |
| `driver01`, `driver02` | DRIVER |
| `customer01`, `customer02` | CUSTOMER |

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python set_demo_passwords.py
cd ..
```

The script asks for a password (input hidden, minimum 8 characters, entered twice) and stores its Argon2 hash on
every account that still has a placeholder. Accounts that already have a real password are left alone unless you
pass `--all`. Every selected account gets the **same** password, which is fine for local development only.
For a non-interactive run, set the `LOGITRACK_DEMO_PASSWORD` environment variable first.

**Alternatives:**
- **Customers** can register through the sign-up page (or `POST /auth/register`).
- **Staff accounts** can be created by an ADMIN with `POST /users`, then `POST /employees`, then `POST /drivers`
  (see [API_DOCUMENTATION.md](API_DOCUMENTATION.md)).

## 9. Install frontend dependencies

```powershell
cd frontend
npm install
cd ..
```

## 10. Start the application

Use **two terminals**.

**Terminal 1, backend.** It must be started from `backend/`, because its imports are relative to that folder:

```powershell
cd backend
.\venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

The API listens on **http://127.0.0.1:8000**.

**Terminal 2, frontend:**

```powershell
cd frontend
npm run dev
```

Vite serves the app on **http://localhost:5173** and proxies `/api/*` and `/auth/*` to `127.0.0.1:8000`
(`frontend/vite.config.js`).
- **The backend must run on port 8000** for the proxy to work.
- If 5173 is busy, Vite picks the next free port and prints it.

## 11. Verify it works

| Check | Expected |
|---|---|
| http://127.0.0.1:8000/ | `{"message":"LogiTrack API is running"}` |
| http://127.0.0.1:8000/docs | Swagger UI listing all endpoints |
| http://localhost:5173 | The LogiTrack sign-in page |
| Sign in as `customer01` | Lands on the **Shop** with 11 products |
| Sign in as `admin01` | Dashboard with metrics and charts; the Users page is visible |

**End-to-end smoke test** (all verified on a fresh database):
1. As `customer01`, add a product to the cart and place an order with an address in **Chennai** (for example
   *"12 Anna Salai, Chennai"*).
2. Go to **Payments** and click **Simulate successful payment** (development only; no real payment).
3. Expect *"Shipment created and driver assigned."*
4. The seed has a `Vellore → Chennai` route and an eligible driver, which is why Chennai works here.

## 12. Run the tests

See [TESTING.md](TESTING.md) for what each suite covers.

**Backend.** The tests create and drop their own database `logitrack_test` on the server named in your
`DATABASE_URL`, so your role needs the `CREATEDB` privilege; `postgres` has it. Your `logitrack_db` data is not
touched.

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m pytest tests -q
cd ..
```

To use a different test database, set `TEST_DATABASE_URL` (its database name must end in `_test`):

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg2://postgres:<password>@localhost:5432/my_logitrack_test"
```

**Frontend.** These are unit tests with Node's built-in test runner; no extra packages are needed.

```powershell
cd frontend
node --test src/lib/status.test.js
cd ..
```

On Windows, pass the test **file**: `node --test src/lib/` does not work there.

**Production build check:**

```powershell
cd frontend
npm run build
```

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `.\venv\Scripts\Activate.ps1 cannot be loaded because running scripts is disabled` | Allow local scripts for your user: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then retry. Alternatively, call `.\venv\Scripts\python.exe` directly. |
| `RuntimeError: DATABASE_URL is required…` or `JWT_SECRET_KEY is required…` | `backend\.env` is missing or incomplete (step 4). |
| `ModuleNotFoundError: No module named 'auth'` (or `models`, `database`) when starting uvicorn | Start uvicorn from inside `backend\`. |
| `psycopg2.OperationalError: … password authentication failed` or `… database "logitrack_db" does not exist` | Check the user, password, port and database name in `DATABASE_URL`, and that step 3 ran. |
| Login returns **401** for `admin01` and the other seeded users | They have no password yet. Run `python set_demo_passwords.py` (step 8). |
| `seed_shop_products.py` fails with `duplicate key value violates unique constraint "product_pkey"` | The database was seeded with an older `seed.sql` that did not advance the ID sequences. Re-create the database and load the current `seed.sql`. |
| `psql: … invalid command \restrict` while loading `schema.sql` | `schema.sql` was produced by `pg_dump` 18.6, which emits `\restrict`/`\unrestrict` meta-commands. Use the `psql` from PostgreSQL 18. It is unverified whether older clients load the rest of the file successfully. |
| The frontend loads but every request fails, or you are logged out immediately | The backend is not running on port 8000, or it crashed. Check terminal 1. |
| An order stays at **"Awaiting approval"** after payment | By design: payment does not dispatch. An Operations Manager approves it in the shipment desk (or `POST /operations/orders/{id}/approve`). |
| Approval says **"No stock is reserved for this order"** | The order predates stock reservations. Use **Recover reservation** on the shipment desk (or `POST /operations/orders/{id}/recover-reservation` with `{"confirm_stock_not_deducted": true}`) after checking its stock was not already deducted. |
| Approval works but the shipment is **"awaiting assignment"** (`PENDING_ASSIGNMENT`) | No driver and vehicle met the eligibility rules (see [ARCHITECTURE.md §5.2](ARCHITECTURE.md#52-payment-approval-shipment-and-assignment)). Run `python seed_demo_data.py` for demo drivers, or assign by hand in the shipment desk. Routes are not required. |
| Backend tests fail with `permission denied to create database` | The database role lacks `CREATEDB`. Use `postgres`, or set `TEST_DATABASE_URL` to a database you are allowed to drop and recreate. |
| Fonts look plain | The UI loads fonts from Google Fonts. Offline it falls back to system fonts, which is expected. |
