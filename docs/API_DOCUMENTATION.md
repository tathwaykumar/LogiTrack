# API Documentation

LogiTrack's backend is a FastAPI application (`backend/main.py`) exposing **100 endpoints** (the registered `APIRoute`
method/path pairs, counted from the running app; recount with
`python -c "from main import app; from fastapi.routing import APIRoute; print(sum(len(r.methods - {'HEAD','OPTIONS'}) for r in app.routes if isinstance(r, APIRoute)))"`
from `backend/`). Fulfilment and operations logic lives in `backend/fulfilment.py` and `backend/operations.py`; the
routes are all in `main.py`. Sections 1–15 were produced from the code and recorded requests; section 16 and the
changes noted in sections 8–14 were written from the code and are exercised by the tests in
[TESTING.md](TESTING.md) (their example bodies are shapes, not recorded sessions). This reference was
produced from the code itself:
- the route list, permissions and request schemas were read from the running FastAPI app;
- every example below is a **real request and response** recorded against a fresh database built as described in
  [SETUP.md](SETUP.md). Long lists are shortened to their first entries (`…`).

> **Interactive docs:** with the backend running, open **http://127.0.0.1:8000/docs** (Swagger UI) or
> **http://127.0.0.1:8000/openapi.json**. Handlers declare no response models, so Swagger shows request bodies
> accurately but response bodies as untyped. Use this document for response shapes.

## Contents

- [Conventions](#conventions) · [Errors](#errors) · [Permission summary](#permission-summary) · [Known issues](#known-issues)
- [1. Health and authentication](#1-health-and-authentication)
- [2. Profile](#2-profile)
- [3. Users and roles](#3-users-and-roles)
- [4. Customers](#4-customers)
- [5. Employees and drivers](#5-employees-and-drivers)
- [6. Vehicles, assignments and maintenance](#6-vehicles-assignments-and-maintenance)
- [7. Products, warehouses and inventory](#7-products-warehouses-and-inventory)
- [8. Shop (customer storefront)](#8-shop-customer-storefront)
- [9. Orders](#9-orders)
- [10. Payments and invoices](#10-payments-and-invoices)
- [11. Routes](#11-routes)
- [12. Shipments](#12-shipments)
- [13. Tracking](#13-tracking)
- [14. Deliveries](#14-deliveries)
- [15. Dashboard and analytics](#15-dashboard-and-analytics)
- [16. Fulfilment and operations](#16-fulfilment-and-operations)

---

## Conventions

| Item | Value |
|---|---|
| Base URL (direct) | `http://127.0.0.1:8000` |
| Base URL (from the frontend) | `http://localhost:5173/api` for every path, and `http://localhost:5173/auth/...` for auth. The Vite proxy forwards both to port 8000. |
| Request bodies | JSON. Field names are `snake_case`. |
| Authentication | `Authorization: Bearer <access_token>` from `POST /auth/login`. Tokens last **60 minutes**; there is no refresh endpoint. |
| Roles | `ADMIN`, `OPERATIONS_MANAGER`, `DRIVER`, `CUSTOMER`, checked by role **name** (see [ARCHITECTURE.md §4](ARCHITECTURE.md#4-authentication-and-authorisation)). |
| Dates | ISO 8601. Timestamps have no time zone (`2026-10-22T22:07:14.657371`). |
| Money | Numbers. Some endpoints return JSON numbers from `numeric` columns (for example `55000.0`). |
| Success status | `200` unless stated. Only `POST /auth/register` and `POST /shop/checkout` return `201`. |
| Unknown body fields | Rejected (422) only by `RegisterRequest`, `ProfileUpdate`, `ShopCheckoutRequest`/`ShopCheckoutItem` and `SimulatedPaymentRequest`. All other bodies ignore unknown fields. |

"Auth" values used below:
- **Public**: no token needed.
- **Any authenticated user**: any valid token; the handler may restrict further.
- **Roles: …**: the token's role must be one of the listed roles.

## Errors

| Status | Body | When |
|---|---|---|
| 401 | `{"detail": "Not authenticated"}` | No `Authorization` header on a protected endpoint. |
| 401 | `{"detail": "Invalid or expired token"}` | Bad signature, malformed token or expired token. |
| 403 | `{"detail": "You do not have permission to access this resource"}` | The role is not allowed on this endpoint. |
| 403 | Endpoint-specific `detail` | Ownership checks (for example a customer reading another customer's order). |
| 404 | `{"detail": "... not found"}` | A record in the path does not exist. A non-numeric ID (for example `/orders/abc`) matches no route and returns `{"detail": "Not Found"}`. |
| 409 | Endpoint-specific `detail` | Business-rule conflicts: stock, duplicates, status transitions. |
| 422 | FastAPI validation body, or `{"detail": "..."}` | Invalid types or lengths, missing fields, or rule-specific validation. |
| 409 | `{"detail": "A record with this value already exists (rule: payment_order_id_key)"}` | A database uniqueness rule was violated (duplicate username, payment per order, stock row, ...). The `rule` is the name of the violated constraint. |
| 422 | `{"detail": "A referenced record does not exist, or the record is still in use (rule: fk_inventory_warehouse)"}` | A foreign key points at a record that does not exist. |
| 422 | `{"detail": "A value is not allowed by the database rules (rule: chk_order_status)"}` | A CHECK constraint failed (for example an order status outside the allowed list, or a negative capacity). |
| 422 | `{"detail": "A value has an invalid format or is out of range"}` | PostgreSQL rejected a value's format (for example a malformed interval). |
| 500 | `{"detail": "A database error occurred"}` | An unexpected database error. These are logged; no SQL or internals are returned. |

Database constraint violations are translated by one global handler, so a bad reference, a duplicate or an
out-of-range value is reported as a 4xx that names the rule, never as a bare 500.

Example of the 401 and 403 responses (real):

```http
GET /orders                     → 401 {"detail":"Not authenticated"}
GET /vehicles  (as a CUSTOMER)  → 403 {"detail":"You do not have permission to access this resource"}
```

## Permission summary

`A` = ADMIN, `O` = OPERATIONS_MANAGER, `D` = DRIVER, `C` = CUSTOMER, `any` = any authenticated user
(the handler may restrict further), `public` = no token.

| Group | Endpoints and roles |
|---|---|
| Health/auth | `GET /` public · `POST /auth/register` public · `POST /auth/login` public · `GET /db-test` A |
| Profile | `GET /profile` any · `PATCH /profile` any |
| Users/roles | `GET/POST /users` A · `GET/POST /roles` A |
| Customers | `GET /customers`, `GET /customers/{id}`, `POST /customers`, `GET /customers/{id}/order-history`, `GET /customers/search` A,O |
| Employees/drivers | `GET/POST /employees`, `PUT /employees/{id}/status` A · `GET/POST /drivers` A,O · `GET /drivers/me` D · `PUT /drivers/{id}/status` A,O,D |
| Fleet | `GET/POST /vehicles`, `PUT /vehicles/{id}/status`, `POST /assignments`, `GET/POST /maintenance` A,O · `GET /assignments` A,O,D |
| Catalogue | `GET /products` A,O,D,C · `POST /products`, `PUT /products/{id}/price`, warehouses, inventory A,O |
| Shop | all `/shop/...` C |
| Orders | `GET /orders`, `GET /orders/{id}/total`, `POST /orders`, `POST /orders/{id}/cancel` A,O,C (customers only their own) · `GET /orders/{id}` any · `GET /orders/{id}/tracking` A,O,D,C (scoped) · status, summary, financial-summary, order-items, search A,O |
| Finance | `GET /payments`, `GET /invoices` A,O,C · create and update A,O |
| Routes | `GET /routes` A,O,D,C · create and update A,O |
| Shipments | `GET /shipments`, `GET /shipments/search`, `GET /shipments/{id}/timeline`, `GET /shipments/{id}/tracking-details` any · everything else A,O |
| Tracking | `POST /tracking` A,O,D · `GET /tracking/{id}` A,O |
| Deliveries | `GET /deliveries` A,O,D,C · `POST /deliveries` A,O · `PUT /deliveries/{id}/status` A,O,D |
| Analytics | `GET /dashboard/summary`, all `/analytics/...` A,O |
| Fulfilment and operations | all `/operations/...`, `POST /shipments/{id}/assignment` A,O |

## Known issues

These remain in the current code and are documented, not fixed:

1. **Status strings are not validated by the API.** The `/…/status` endpoints pass the value to the database.
   Where the column has a CHECK constraint (orders, payments, shipments, deliveries) an invalid value is
   rejected with a 422 naming the rule. Where it does not (vehicle, driver availability, warehouse, employee,
   route, invoice) any string is stored.
2. **Error messages for database rules are generic.** A violated rule is reported with a fixed sentence plus the
   constraint name, not a field-by-field explanation.
3. **`PUT /orders/{id}/status` has no transition rules.** Since migration 005 a trigger moves an order forward when
   its shipment moves (picked up / in transit / out for delivery → `SHIPPED`, delivered → `DELIVERED`), never
   backwards and never for a cancelled order. Orders whose shipments changed before that trigger existed were not
   corrected: `GET /operations/summary` reports them under `data_consistency`.
4. **Older deliveries have no `vehicle_id` or `assigned_at`.** Since migration 005 both are stored for new
   assignments; rows created earlier keep `NULL` and are shown as "vehicle not recorded".

Fixed since the first version of this document (see [TESTING.md](TESTING.md)): the `search` routes are reachable,
missing records return 404, constraint errors return 409 or 422, drivers can only read their own orders and
shipments, `POST /routes` and `GET /routes` show the duration the same way, and `POST /shipments` and
registration now fill their timestamps.

---

## 1. Health and authentication

### `GET /`
Health check. **Auth:** Public.

```json
{"message": "LogiTrack API is running"}
```

### `POST /auth/register`
Self-registration. Always creates a **CUSTOMER** account and its `customer` profile in one transaction.
**Auth:** Public. **Success:** `201`.

| Field | Type | Rules |
|---|---|---|
| `name` | string | required, 1–100 chars, not blank |
| `username` | string | required, 3–50 chars |
| `email` | string | required, 3–100 chars, must contain `@` (stored lower-cased) |
| `phone` | string | required, 7–20 chars |
| `address` | string | required, 1–255 chars |
| `password` | string | required, 8–128 chars (stored as an Argon2 hash) |

Unknown fields are rejected.

**Errors:**
- 409 `"Username is already in use"` / `"Email is already in use"`.
- 409 `"Username or email is already in use"` (database integrity error).
- 422 validation errors.
- 500 `"Customer role is not configured"` if no `CUSTOMER` role exists.

```http
POST /auth/register
{"name":"Asha Raman","username":"asha.r","email":"asha@example.com","phone":"9876543210","address":"14 Lake Road, Chennai","password":"Example-Pass-123"}
```
```json
201 {"message":"Account created successfully","user_id":7,"customer_id":3,"username":"asha.r","role":"CUSTOMER"}
```

### `POST /auth/login`
Exchange a username and password for a JWT. **Auth:** Public.

| Field | Type | Rules |
|---|---|---|
| `username` | string | required |
| `password` | string | required |

**Errors:**
- 401 `"Invalid username or password"`: unknown user, wrong password, or a stored hash that isn't valid.
- 403 `"User account is inactive"`.

```http
POST /auth/login
{"username":"customer01","password":"<password>"}
```
```json
{"message":"Login successful","access_token":"<JWT>","token_type":"bearer","user_id":5,"username":"customer01","role_id":4}
```

### `GET /db-test`
Runs `SELECT 1` through the API's database connection. **Auth:** Roles: ADMIN.

```json
{"database":"connected","result":1}
```

---

## 2. Profile

### `GET /profile`
The caller's own account and linked profile. **Auth:** Any authenticated user.

- `profile_type` is `"CUSTOMER"`, `"EMPLOYEE"` or `null`.
- `name` and `phone` come from that profile; `address` is set for customers only.
- **Errors:** 404 `"User account not found"`.

```json
{"user_id":5,"username":"customer01","email":"customer1@example.com","profile_type":"CUSTOMER","name":"Arjun Mehta","phone":"9876543210","address":"Vellore, Tamil Nadu"}
```

### `PATCH /profile`
Update your own account. Only the fields you send are changed. **Auth:** Any authenticated user.

| Field | Rules |
|---|---|
| `username` | 1–50 chars; unique (409 `"Username is already in use"`); not blank (422) |
| `email` | 1–100 chars; must contain `@` (422); unique (409 `"Email is already in use"`) |
| `password` | 8–128 chars; **requires** `current_password` (422 if missing; 400 `"Current password is incorrect"` if wrong) |
| `current_password` | ≤128 chars |
| `name` | 1–100 chars; updates the customer or employee profile (422 if the account has neither) |
| `phone` | ≤20 chars; blank clears it; customer or employee only |
| `address` | ≤255 chars; **customers only** (422 otherwise) |

Unknown fields are rejected. The response is the same shape as `GET /profile`. The frontend logs the user out
after a password change.

```http
PATCH /profile
{"phone":"9123456780"}
```
```json
{"user_id":5,"username":"customer01","email":"customer1@example.com","profile_type":"CUSTOMER","name":"Arjun Mehta","phone":"9123456780","address":"Vellore, Tamil Nadu"}
```
```http
PATCH /profile
{"password":"New-Example-Pass-1","current_password":"wrong"}
```
```json
400 {"detail":"Current password is incorrect"}
```

---

## 3. Users and roles

### `GET /users`
All user accounts with their role names, ordered by username. **Auth:** Roles: ADMIN.

```json
[{"user_id":1,"role_id":1,"role_name":"ADMIN","username":"admin01","email":"admin@logitrack.com","created_at":"2026-10-22T22:07:11.788431","is_active":true}, "…"]
```

### `POST /users`
Create a login account with any role. Creating the matching `customer` or `employee` profile is a separate call.
**Auth:** Roles: ADMIN.

| Field | Type | Rules |
|---|---|---|
| `role_id` | int | required; must exist (404 `"Role not found"`) |
| `username` | string | required; unique with email (409 `"A user with that username or email already exists"`) |
| `email` | string | required; not format-validated |
| `password` | string | required, 8–128 chars (Argon2-hashed) |
| `is_active` | bool | default `true` |

```http
POST /users
{"role_id":4,"username":"walkin.customer","email":"walkin@example.com","password":"Example-Pass-123"}
```
```json
{"message":"User created successfully","user_id":8,"role_id":4,"username":"walkin.customer","email":"walkin@example.com","is_active":true}
```

### `GET /roles`
**Auth:** Roles: ADMIN.

```json
[{"role_id":1,"role_name":"ADMIN","description":"Full system access"},{"role_id":2,"role_name":"OPERATIONS_MANAGER","description":"Manages logistics operations"}, "…"]
```

### `POST /roles`
**Auth:** Roles: ADMIN. **Body:** `role_name` (string, required), `description` (string, optional). A duplicate
`role_name` returns 409.

The frontend only supports role IDs 1–4 (see [ARCHITECTURE.md §4](ARCHITECTURE.md#4-authentication-and-authorisation)).

```http
POST /roles
{"role_name":"WAREHOUSE_MANAGER","description":"Manages warehouse stock"}
```
```json
{"message":"Role created successfully","role_id":5,"role_name":"WAREHOUSE_MANAGER","description":"Manages warehouse stock"}
```

---

## 4. Customers

### `GET /customers`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

```json
[{"customer_id":2,"user_id":6,"name":"Priya Sharma","phone":"9876543211","address":"Chennai, Tamil Nadu"}, "…"]
```

### `GET /customers/{customer_id}`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER. **Path:** `customer_id` (int).
**Not found:** `404 {"detail":"Customer not found"}`.

```json
{"customer_id":1,"user_id":5,"name":"Arjun Mehta","phone":"9123456780","address":"Vellore, Tamil Nadu"}
```

### `POST /customers`
Attach a customer profile to an existing user. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `user_id` (int, required), `name` (string, required), `phone` and `address` (optional). A `user_id` that
doesn't exist returns 422; one that already has a customer profile returns 409.

```http
POST /customers
{"user_id":8,"name":"Walk-in Customer","phone":"9000011111","address":"3 Fort Road, Vellore"}
```
```json
{"message":"Customer created successfully","customer_id":4,"user_id":8,"name":"Walk-in Customer","phone":"9000011111","address":"3 Fort Road, Vellore"}
```

### `GET /customers/{customer_id}/order-history`
A customer's orders with total item counts, newest first. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.
**Not found:** `404 {"detail":"Customer not found"}`.

```json
{"customer_id":1,"customer_name":"Arjun Mehta","orders":[{"order_id":5,"order_date":"2026-10-22T22:07:13.837635","order_status":"PROCESSING","shipping_address":"12 Anna Salai, Chennai","total_items":3}, "…"]}
```

### `GET /customers/search`
Filter customers. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Query (all optional):** `name` (case-insensitive substring of the name), `city` (case-insensitive substring of
the address). Results are ordered by name.

```http
GET /customers/search?name=arjun
```
```json
[{"customer_id":1,"user_id":5,"name":"Arjun Mehta","phone":"9876543210","address":"Vellore, Tamil Nadu"}]
```

---

## 5. Employees and drivers

### `GET /employees`
**Auth:** Roles: ADMIN.

```json
[{"employee_id":1,"user_id":2,"name":"Rahul Verma","phone":"9876500001","department":"Operations","hire_date":"2024-06-10","salary":65000.0,"employment_status":"ACTIVE"}, "…"]
```

### `POST /employees`
**Auth:** Roles: ADMIN.

**Body:**
- `name` (required).
- `user_id`, `phone`, `department`, `hire_date` (date), `salary` (≥0, otherwise 422).
- `employment_status` (default `"ACTIVE"`).

```http
POST /employees
{"user_id":9,"name":"Ravi Kumar","phone":"9000022222","department":"Transport","hire_date":"2026-01-15","salary":28000}
```
```json
{"message":"Employee created successfully","employee_id":5,"user_id":9,"name":"Ravi Kumar","phone":"9000022222","department":"Transport","hire_date":"2026-01-15","salary":28000.0,"employment_status":"ACTIVE"}
```

### `PUT /employees/{employee_id}/status`
**Auth:** Roles: ADMIN. **Body:** `employment_status` (string; any value accepted).
**Not found:** `404 {"detail":"Employee not found"}`.

Only `ACTIVE` employees are eligible for automatic driver assignment.

```json
{"message":"Employee status updated successfully","employee_id":5,"employment_status":"ACTIVE"}
```

### `GET /drivers`
Drivers joined with their employee records, ordered by name. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

```json
[{"employee_id":3,"name":"Amit Kumar","phone":"9876500003","department":"Transport","hire_date":"2025-01-20","employment_status":"ACTIVE","license_no":"TN-DRV-1002","license_expiry":"2027-11-15","availability_status":"AVAILABLE"}, "…"]
```

### `GET /drivers/me`
The calling driver's own record, returned as a one-element list. **Auth:** Roles: DRIVER.
**Errors:** 404 `"Driver profile not found"`.

```json
[{"employee_id":2,"name":"Vikram Singh","phone":"9876500002","department":"Transport","hire_date":"2024-08-15","employment_status":"ACTIVE","license_no":"TN-DRV-1001","license_expiry":"2028-06-30","availability_status":"AVAILABLE"}]
```

### `POST /drivers`
Make an existing employee a driver. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `employee_id` (int, required), `license_no` (required, unique), `license_expiry` (date, required),
`availability_status` (default `"AVAILABLE"`).

```http
POST /drivers
{"employee_id":5,"license_no":"TN-DL-2026-0042","license_expiry":"2029-12-31"}
```
```json
{"message":"Driver created successfully","employee_id":5,"license_no":"TN-DL-2026-0042","license_expiry":"2029-12-31","availability_status":"AVAILABLE"}
```

### `PUT /drivers/{employee_id}/status`
Set a driver's availability. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER, DRIVER. A driver may only update their
own record (403 `"You do not have permission to update this driver"`).

**Body:** `availability_status` (string; any value accepted). Only `AVAILABLE` is eligible for automatic
assignment. **Not found:** `404 {"detail":"Driver not found"}`.

```json
{"message":"Driver availability updated successfully","employee_id":5,"availability_status":"AVAILABLE"}
```

---

## 6. Vehicles, assignments and maintenance

### `GET /vehicles`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

```json
[{"vehicle_id":1,"registration_no":"TN01AB1234","vehicle_type":"Mini Truck","capacity":1500.0,"fuel_type":"DIESEL","status":"ACTIVE","purchase_date":"2023-04-10"}, "…"]
```

### `POST /vehicles`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:**
- `registration_no` (required, unique), `vehicle_type` (required), `capacity` (required, >0).
- `fuel_type`, `status` (default `"ACTIVE"`), `purchase_date` (date).

```http
POST /vehicles
{"registration_no":"TN-09-AB-4521","vehicle_type":"VAN","capacity":1500,"fuel_type":"DIESEL","purchase_date":"2025-06-01"}
```
```json
{"message":"Vehicle created successfully","vehicle_id":5,"registration_no":"TN-09-AB-4521","vehicle_type":"VAN","capacity":1500.0,"fuel_type":"DIESEL","status":"ACTIVE","purchase_date":"2025-06-01"}
```

### `PUT /vehicles/{vehicle_id}/status`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER. **Body:** `status` (any string).
**Not found:** `404 {"detail":"Vehicle not found"}`.

Automatic driver assignment treats `ACTIVE` and `AVAILABLE` as in service.

```json
{"message":"Vehicle status updated successfully","vehicle_id":5,"status":"ACTIVE"}
```

### `GET /assignments`
Driver–vehicle assignments. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER, DRIVER. A driver sees only their own
(404 `"Driver profile not found"` if the caller has no employee record).

```json
[{"assignment_id":1,"driver_id":2,"vehicle_id":1,"assigned_from":"2026-01-01","assigned_to":null}]
```

### `POST /assignments`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `driver_id`, `vehicle_id`, `assigned_from` (date) required; `assigned_to` (date, optional, must be ≥
`assigned_from`, otherwise 422). Overlapping assignments are not prevented.

```http
POST /assignments
{"driver_id":5,"vehicle_id":5,"assigned_from":"2026-10-01"}
```
```json
{"message":"Vehicle assignment created successfully","assignment_id":3,"driver_id":5,"vehicle_id":5,"assigned_from":"2026-10-01","assigned_to":null}
```

### `GET /maintenance`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

```json
[{"maintenance_id":1,"vehicle_id":1,"maintenance_date":"2026-02-15","maintenance_type":"SERVICE","cost":8500.0,"description":"Regular engine and oil service"}, "…"]
```

### `POST /maintenance`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `vehicle_id`, `maintenance_date` (date), `maintenance_type`, `cost` (≥0) required; `description` optional.

```http
POST /maintenance
{"vehicle_id":5,"maintenance_date":"2026-10-10","maintenance_type":"SERVICE","cost":4200,"description":"Periodic service"}
```
```json
{"message":"Vehicle maintenance record created successfully","maintenance_id":6,"vehicle_id":5,"maintenance_date":"2026-10-10","maintenance_type":"SERVICE","cost":4200.0,"description":"Periodic service"}
```

---

## 7. Products, warehouses and inventory

### `GET /products`
The catalogue without stock figures. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER, DRIVER, CUSTOMER.

```json
[{"product_id":1,"product_name":"Laptop","category":"Electronics","unit_price":55000.0,"weight":2.2,"description":"Business laptop"}, "…"]
```

### `POST /products`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `product_name` (required), `unit_price` (required, ≥0), `category`, `weight` (>0), `description`.

```http
POST /products
{"product_name":"Desk Lamp","category":"Accessories","unit_price":1500,"weight":0.8,"description":"LED desk lamp"}
```
```json
{"message":"Product created successfully","product_id":12,"product_name":"Desk Lamp","category":"Accessories","unit_price":1500.0,"weight":0.8,"description":"LED desk lamp"}
```

### `PUT /products/{product_id}/price`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER. **Body:** `unit_price` (number, ≥0).
**Not found:** `404 {"detail":"Product not found"}`.

Existing order lines keep their own price.

```json
{"message":"Product price updated successfully","product_id":12,"product_name":"Desk Lamp","unit_price":1450.0}
```

### `GET /warehouses`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

```json
[{"warehouse_id":1,"warehouse_name":"Vellore Central Warehouse","address":"Katpadi Road","city":"Vellore","capacity":10000.0,"manager_employee_id":1,"status":"ACTIVE"}, "…"]
```

### `POST /warehouses`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `warehouse_name`, `address`, `city` required; `capacity` (>0), `manager_employee_id`, `status`
(default `"ACTIVE"`). `city` must match a route's `source` for automatic shipment creation.

```http
POST /warehouses
{"warehouse_name":"Madurai Depot","address":"22 Ring Road","city":"Madurai","capacity":5000}
```
```json
{"message":"Warehouse created successfully","warehouse_id":4,"warehouse_name":"Madurai Depot","address":"22 Ring Road","city":"Madurai","capacity":5000.0,"manager_employee_id":null,"status":"ACTIVE"}
```

### `PUT /warehouses/{warehouse_id}/status`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER. **Body:** `status` (any string).
**Not found:** `404 {"detail":"Warehouse not found"}`.

Checkout does **not** consult warehouse status.

```json
{"message":"Warehouse status updated successfully","warehouse_id":4,"status":"ACTIVE"}
```

### `GET /inventory`
Raw stock rows. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

```json
[{"warehouse_id":1,"product_id":2,"quantity":80,"reorder_level":20,"last_updated":"2026-10-22T22:07:11.788431"}, "…"]
```

### `POST /inventory`
Create the stock row for a product in a warehouse. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `warehouse_id`, `product_id`, `quantity` (≥0) required; `reorder_level` (default 0).
A duplicate (warehouse, product) pair returns **409**; a missing warehouse or product returns **422**.

```http
POST /inventory
{"warehouse_id":4,"product_id":12,"quantity":40,"reorder_level":10}
```
```json
{"message":"Inventory created successfully","warehouse_id":4,"product_id":12,"quantity":40,"reorder_level":10}
```
```http
POST /inventory
{"warehouse_id":99999,"product_id":1,"quantity":1}
```
```json
422 {"detail":"A referenced record does not exist, or the record is still in use (rule: fk_inventory_warehouse)"}
```

### `PUT /inventory/{warehouse_id}/{product_id}`
Set stock (absolute value, not a delta). **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `quantity` (int, required, ≥0), `reorder_level` (optional).
**Not found:** `404 {"detail":"Inventory record not found"}`.

```http
PUT /inventory/4/12
{"quantity":35}
```
```json
{"message":"Inventory updated successfully","warehouse_id":4,"product_id":12,"quantity":35,"reorder_level":10}
```

---

## 8. Shop (customer storefront)

### `GET /shop/products`
The catalogue with `available_stock` = sum of `inventory.quantity` across **active** warehouses (the same pool checkout
can reserve from), ordered by name.
**Auth:** Roles: CUSTOMER.

```json
[{"product_id":11,"product_name":"Bluetooth Speaker","category":"Electronics","unit_price":2800.0,"weight":0.55,"description":"Compact wireless speaker with 12-hour battery","available_stock":35}, "…"]
```

### `POST /shop/checkout`
Place an order from a cart. **Auth:** Roles: CUSTOMER (the caller must have a customer profile, otherwise 404).
**Success:** `201`. The response also carries `fulfilment: {"stage": "Awaiting payment", "dispatch": "..."}`, a
plain-language stage only; internal planning detail is available to staff in section 16.

| Field | Rules |
|---|---|
| `items` | list of 1–50 `{product_id, quantity}`; `product_id` > 0; `quantity` 1–10,000; duplicate products are summed (and the sum must be ≤10,000) |
| `shipping_address` | 1–255 chars, not blank. The customer's full delivery address. |
| `destination_city` | optional free text, up to 100 chars. Stored on the order; never required, and no route has to exist for it. |

Unknown fields are rejected.

**Side effects, all in one transaction** (see [ARCHITECTURE.md §5.1](ARCHITECTURE.md#51-customer-shop-checkout-and-inventory-reservation)):
- Locks product and inventory rows.
- Creates `orders` (`PENDING`) and `order_item` rows at current prices.
- **Deducts stock** from active warehouses (one warehouse that holds every item if there is one, otherwise several in ID order).
- Writes one `order_inventory_reservation` row per warehouse used.
- Creates an `invoice` (`ISSUED`, tax 0).
- Writes the fulfilment plan (`order_fulfilment`): the origin warehouse and why it was chosen. Routes play no part.

Payment is not collected here, and nothing is dispatched.

**Errors:**
- 404 `"Product N was not found"`.
- 409 `"Insufficient stock for <name>. Only N available."`.
- 409 `"The order could not be completed. Please refresh and try again."` (integrity error).
- 422 validation.

```http
POST /shop/checkout
{"items":[{"product_id":1,"quantity":1},{"product_id":11,"quantity":2}],"shipping_address":"12 Anna Salai, Chennai"}
```
```json
201 {"message":"Order placed successfully. Payment is pending.","order":{"order_id":5,"order_status":"PENDING","shipping_address":"12 Anna Salai, Chennai","items":[{"product_id":1,"product_name":"Laptop","quantity":1,"unit_price":55000.0,"item_total":55000.0},{"product_id":11,"product_name":"Bluetooth Speaker","quantity":2,"unit_price":2800.0,"item_total":5600.0}]},"invoice":{"invoice_id":5,"invoice_status":"ISSUED","subtotal":60600.0,"tax":0.0,"total_amount":60600.0}}
```
```json
409 {"detail":"Insufficient stock for Wireless Mouse. Only 180 available."}
```

### `GET /shop/payment-orders`
The caller's `PENDING` orders that have an invoice, with any existing payment, newest first. **Auth:** Roles: CUSTOMER.

```json
[{"order_id":5,"order_status":"PENDING","invoice_id":5,"invoice_status":"ISSUED","total_amount":60600.0,"payment_id":null,"payment_status":null}]
```

### `POST /shop/payments/simulate`
**Development-only payment simulator.** It never contacts a payment provider. It records a `SUCCESS` or `FAILED`
result. A successful payment **does not dispatch anything**: the order waits for an Operations Manager to approve it
(`POST /operations/orders/{order_id}/approve`, section 16). **Auth:** Roles: CUSTOMER.

| Field | Rules |
|---|---|
| `order_id` | int > 0; must belong to the caller (otherwise 404 `"Order not found"`) |
| `outcome` | `"SUCCESS"` or `"FAILED"` (case-insensitive; anything else gives 422) |

Unknown fields are rejected.

**Behaviour:**
- The amount is recomputed with `calculate_order_total`.
- The payment row is created or updated with method `SIMULATED_TEST_MODE` and reference `SIM-<order_id>`.
- **FAILED:** payment `FAILED`; order stays `PENDING`; invoice `ISSUED`; `fulfilment` is `null`.
- **SUCCESS** (the order must be `PENDING`, otherwise 409): payment `SUCCESS`, order `CONFIRMED`, invoice `PAID`, a
  `PAID` entry in the fulfilment log. No shipment, driver or vehicle is created. `fulfilment` is
  `{"status": "AWAITING_APPROVAL", "message": "Payment received. The order is awaiting approval by operations.", ...}`.
  The order becomes `PROCESSING` only after approval assigns a driver.
- **Repeat SUCCESS:** `already_processed: true`, no writes, and the current fulfilment state (including the stored
  `vehicle_id` once a driver is assigned).

**Errors:**
- 409 `"A successful simulated payment cannot be changed to failed"`.
- 409 `"This order cannot be paid in its current status"`.
- 409 `"Order receipt invoice is missing"`.
- 409 `"Payment simulation could not be completed"`.

```http
POST /shop/payments/simulate
{"order_id":5,"outcome":"FAILED"}
```
```json
{"message":"Simulated payment failed.","mode":"DEVELOPMENT_ONLY_SIMULATION","already_processed":false,"fulfilment":null,"payment_id":5,"payment_status":"FAILED","order_id":5,"order_status":"PENDING","invoice_id":5,"invoice_status":"ISSUED","total_amount":60600.0}
```
```http
POST /shop/payments/simulate
{"order_id":5,"outcome":"SUCCESS"}
```
```json
{"message":"Simulated payment success.","mode":"DEVELOPMENT_ONLY_SIMULATION","already_processed":false,"fulfilment":{"status":"DRIVER_ASSIGNED","message":"Shipment created and driver assigned.","shipment_id":5,"shipment_status":"CREATED","origin_warehouse_id":1,"source_warehouse_ids":[1],"driver_id":2,"vehicle_id":1},"payment_id":5,"payment_status":"SUCCESS","order_id":5,"order_status":"PROCESSING","invoice_id":5,"invoice_status":"PAID","total_amount":60600.0}
```

---

## 9. Orders

### `GET /orders`
Orders with their lines (product names included). ADMIN and OPERATIONS_MANAGER see all orders; a CUSTOMER sees
only their own (404 `"Customer profile not found"` if they have no profile). **Auth:** Roles: ADMIN,
OPERATIONS_MANAGER, CUSTOMER.

Each order also carries `order_date`, `destination_city`, `payment_status` and `stage` (`{key, label}` such as
`Awaiting payment`, `Awaiting approval`, `Preparing shipment`, `Driver assigned`, `In transit`, `Delivered`). For staff
it adds `fulfilment_status` and `fulfilment_reason`; for customers those two are `null`.

```json
[{"order_id":1,"customer_id":1,"order_status":"DELIVERED","shipping_address":"Vellore, Tamil Nadu","items":[{"product_id":1,"product_name":"Laptop","quantity":1,"unit_price":55000.0,"item_total":55000.0},{"product_id":2,"product_name":"Wireless Mouse","quantity":2,"unit_price":1200.0,"item_total":2400.0}]}, "…"]
```

### `GET /orders/{order_id}`
One order with its lines (no product names). **Auth:** Any authenticated user.

- Customers can read only their own orders (403 `"You do not have permission to access this order"`).
- A DRIVER can read only orders that contain a shipment assigned to them (403 `"You do not have permission to access this order"` otherwise). ADMIN and OPERATIONS_MANAGER can read any order.
- **Errors:** 404 `"Order not found"`.

```json
{"order_id":5,"customer_id":1,"order_status":"PROCESSING","shipping_address":"12 Anna Salai, Chennai","items":[{"product_id":1,"quantity":1,"unit_price":55000.0},{"product_id":11,"quantity":2,"unit_price":2800.0}]}
```

### `GET /orders/{order_id}/total`
Order total from the database function `calculate_order_total`. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER,
CUSTOMER (customers: own orders only, 403 otherwise). **Errors:** 404.

```json
{"order_id":5,"total":60600.0}
```

### `POST /orders`
Create an empty order header (no items, stock or invoice; compare `POST /shop/checkout`).
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER, CUSTOMER.

**Body:**
- `customer_id` (int, required): used by ADMIN and OPERATIONS_MANAGER (404 `"Customer not found"`). For a
  CUSTOMER it is required by the schema but **ignored**; the caller's own customer ID is used.
- `shipping_address` (required).
- `order_status` (default `"PENDING"`; must be one of the CHECK values, otherwise 422).

```http
POST /orders
{"customer_id":2,"shipping_address":"7 Lake View, Bangalore"}
```
```json
{"message":"Order created successfully","order_id":6,"customer_id":2,"order_status":"PENDING","shipping_address":"7 Lake View, Bangalore"}
```

### `PUT /orders/{order_id}/status`
Set an order status directly. There are no transition rules. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `order_status`. Values outside `PENDING|CONFIRMED|PROCESSING|SHIPPED|DELIVERED|CANCELLED` return **422** (`rule: chk_order_status`).
**Not found:** `404 {"detail":"Order not found"}`. Order status is not synchronised with shipment status.

```json
{"message":"Order status updated successfully","order_id":6,"order_status":"CONFIRMED"}
```

### `GET /orders/{order_id}/summary`
Order, lines and computed total. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.
**Not found:** `404 {"detail":"Order not found"}`.

```json
{"order_id":5,"customer_id":1,"order_status":"PROCESSING","shipping_address":"12 Anna Salai, Chennai","items":[{"product_id":1,"quantity":1,"unit_price":55000.0},{"product_id":11,"quantity":2,"unit_price":2800.0}],"total":60600.0}
```

### `GET /orders/{order_id}/financial-summary`
Computed total plus the order's payment and invoice (fields are `null` if missing). **Auth:** Roles: ADMIN,
OPERATIONS_MANAGER. **Not found:** `404 {"detail":"Order not found"}`.

```json
{"order_id":5,"calculated_order_total":60600.0,"payment":{"payment_id":5,"amount":60600.0,"payment_method":"SIMULATED_TEST_MODE","payment_status":"SUCCESS"},"invoice":{"invoice_id":5,"subtotal":60600.0,"tax":0.0,"total_amount":60600.0,"invoice_status":"PAID"}}
```

### `GET /order-items`
All order lines. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

```json
[{"order_id":1,"product_id":1,"quantity":1,"unit_price":55000.0},{"order_id":1,"product_id":2,"quantity":2,"unit_price":1200.0}, "…"]
```

### `POST /order-items`
Add a line to an order. Stock is **not** deducted and no reservation is written. **Auth:** Roles: ADMIN,
OPERATIONS_MANAGER.

**Body:** `order_id`, `product_id`, `quantity` (>0), `unit_price` (≥0), all required. A duplicate line or a
missing foreign key returns 422.

```http
POST /order-items
{"order_id":6,"product_id":3,"quantity":2,"unit_price":3500}
```
```json
{"message":"Order item created successfully","order_id":6,"product_id":3,"quantity":2,"unit_price":3500.0}
```

### `GET /orders/search`
Filter orders, newest first. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Query (all optional):** `status` (case-insensitive), `customer_id` (int).

```http
GET /orders/search?status=delivered
```
```json
[{"order_id":1,"customer_id":1,"order_date":"2026-08-20T10:30:00","order_status":"DELIVERED","shipping_address":"Vellore, Tamil Nadu"}]
```

---

## 10. Payments and invoices

### `GET /payments`
ADMIN and OPERATIONS_MANAGER see all payments; a CUSTOMER sees payments for their own orders. **Auth:** Roles:
ADMIN, OPERATIONS_MANAGER, CUSTOMER.

```json
[{"payment_id":1,"order_id":1,"amount":57400.0,"payment_method":"UPI","payment_status":"SUCCESS","payment_date":"2026-08-20T10:35:00","transaction_reference":"TXN10001"}, "…"]
```

### `POST /payments`
Record a payment manually (no provider involved, no effect on order, invoice or fulfilment).
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:**
- `order_id`, `amount` (>0), `payment_method`, all required.
- `payment_status` (default `"PENDING"`; must be `PENDING|SUCCESS|FAILED|REFUNDED`).
- `transaction_reference` (unique).

A second payment for the same order returns 409 (unique `order_id`).

```http
POST /payments
{"order_id":6,"amount":7000,"payment_method":"UPI","transaction_reference":"UPI-REF-0001"}
```
```json
{"message":"Payment created successfully","payment_id":6,"order_id":6,"amount":7000.0,"payment_method":"UPI","payment_status":"PENDING","transaction_reference":"UPI-REF-0001"}
```

### `PUT /payments/{payment_id}/status`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER. **Body:** `payment_status` (outside the CHECK list returns 422).
**Not found:** `404 {"detail":"Payment not found"}`. It does **not** trigger fulfilment.

```json
{"message":"Payment status updated successfully","payment_id":6,"payment_status":"SUCCESS"}
```

### `GET /invoices`
ADMIN and OPERATIONS_MANAGER see all invoices; a CUSTOMER sees invoices for their own orders. **Auth:** Roles:
ADMIN, OPERATIONS_MANAGER, CUSTOMER.

```json
[{"invoice_id":1,"order_id":1,"invoice_date":"2026-08-20T10:40:00","subtotal":57400.0,"tax":10332.0,"total_amount":67732.0,"invoice_status":"ISSUED"}, "…"]
```

### `POST /invoices`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:**
- `order_id`, `subtotal` (≥0), `tax` (≥0), `total_amount`, all required.
- `total_amount` **must equal** `subtotal + tax` (CHECK; a mismatch returns 422).
- `invoice_status` (default `"ISSUED"`).

One invoice per order (a duplicate returns 409).

```http
POST /invoices
{"order_id":6,"subtotal":7000,"tax":0,"total_amount":7000}
```
```json
{"message":"Invoice created successfully","invoice_id":6,"order_id":6,"subtotal":7000.0,"tax":0.0,"total_amount":7000.0,"invoice_status":"ISSUED"}
```

### `PUT /invoices/{invoice_id}/status`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER. **Body:** `invoice_status` (any string).
**Not found:** `404 {"detail":"Invoice not found"}`.

```json
{"message":"Invoice status updated successfully","invoice_id":6,"invoice_status":"PAID"}
```

---

## 11. Routes

### `GET /routes`
`estimated_duration` is returned as text (`"H:MM:SS"`). **Auth:** Roles: ADMIN, OPERATIONS_MANAGER, DRIVER, CUSTOMER.

```json
[{"route_id":1,"route_name":"Vellore-Chennai Route","source":"Vellore","destination":"Chennai","distance_km":140.0,"estimated_duration":"3:00:00","route_status":"ACTIVE"}, "…"]
```

### `POST /routes`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:**
- `route_name`, `source`, `destination`, `distance_km` (>0), all required.
- `estimated_duration`: a PostgreSQL interval string such as `"8 hours"`.
- `route_status` (default `"ACTIVE"`).

The response shows the duration as text (`"8:00:00"`), the same way `GET /routes` does.

```http
POST /routes
{"route_name":"Madurai-Chennai Route","source":"Madurai","destination":"Chennai","distance_km":460,"estimated_duration":"8 hours"}
```
```json
{"message":"Route created successfully","route_id":4,"route_name":"Madurai-Chennai Route","source":"Madurai","destination":"Chennai","distance_km":460.0,"estimated_duration":"8:00:00","route_status":"ACTIVE"}
```

### `PUT /routes/{route_id}/status`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER. **Body:** `route_status` (any string; only `ACTIVE` routes are used
automatically). **Not found:** `404 {"detail":"Route not found"}`.

```json
{"message":"Route status updated successfully","route_id":4,"route_status":"ACTIVE"}
```

---

## 12. Shipments

### `GET /shipments`
**Auth:** Any authenticated user. Results are scoped by role:
- **CUSTOMER:** shipments for their orders.
- **DRIVER:** shipments that have a delivery assigned to them.
- **Others:** all shipments.

```json
[{"shipment_id":1,"order_id":1,"warehouse_id":1,"route_id":1,"shipment_date":"2026-08-20T13:00:00","estimated_delivery":"2026-08-21T16:00:00","actual_delivery":"2026-08-21T15:30:00","shipment_status":"DELIVERED"}, "…"]
```

### `GET /shipment-details`
Shipments joined with customer, warehouse and route names (`route_name` is `null` for a shipment without a configured
route). **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

```json
[{"shipment_id":1,"order_id":1,"customer_name":"Arjun Mehta","warehouse_name":"Vellore Central Warehouse","route_name":"Vellore-Chennai Route","shipment_status":"DELIVERED"}, "…"]
```

### `GET /shipments/search`
Filter shipments, newest first. **Auth:** Any authenticated user. Customers are limited to their own shipments and
drivers to shipments assigned to them (a driver with no employee record gets 404).

**Query:** `status` (string, upper-cased), `warehouse_id` (int), `route_id` (int), all optional.

```http
GET /shipments/search?status=CREATED
```
```json
[{"shipment_id":6,"order_id":6,"warehouse_id":3,"route_id":3,"shipment_date":null,"estimated_delivery":"2026-11-02T18:00:00","shipment_status":"CREATED"}, "…"]
```

### `POST /shipments`
Create a shipment manually. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER. Only a **paid, uncancelled** order can be
dispatched, exactly as for approval; creating the shipment is recorded as the operations approval if none exists.

**Body:** `order_id`, `warehouse_id` (ints, required), `route_id` (int, optional: omit it for a shipment without a route; an id that does not exist gives 422), `estimated_delivery` (datetime, optional).

**Rules and side effects:**
- Locks the order first (avoids a deadlock with payment fulfilment).
- The first manual shipment for an order records the operations approval once (`approved_at`, `approved_by_user_id`, one `APPROVED` log entry); later or replacement shipments never add a second one. A request that fails (for example an unknown warehouse) records no approval.
- The shipment is created with status `CREATED` and **no** shipment items or tracking event.
- `shipment_date` defaults to the current time.

**Errors:**
- 404 `"Order not found"`.
- 409 `"This order is cancelled."`.
- 409 `"Payment has not succeeded for this order, so a shipment cannot be created."`.
- **409 `"This order already has an active (non-cancelled) shipment"`** (partial unique index).
- An invalid warehouse or route returns 422.

```http
POST /shipments
{"order_id":6,"warehouse_id":3,"route_id":3,"estimated_delivery":"2026-11-02T18:00:00"}
```
```json
{"message":"Shipment created successfully","shipment_id":6,"order_id":6,"warehouse_id":3,"route_id":3,"shipment_status":"CREATED"}
```
```json
409 {"detail":"This order already has an active (non-cancelled) shipment"}
```

### `PUT /shipments/{shipment_id}/status`
Change a shipment's status by recording a tracking event. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `status`, one of `CREATED, PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY, DELIVERED, CANCELLED`
(case-insensitive, otherwise 422).

**Rules:**
- Same status as now: 200 with `"tracking_event_created": false` and no event, even for closed shipments.
- Otherwise the transition must be allowed (forward only, `CANCELLED` from any open stage, nothing after
  `DELIVERED`/`CANCELLED`), else **409**.
- The delivery status follows automatically.

**Errors:**
- 404 `"Shipment not found"`.
- 409 transition messages, or the active-shipment conflict when reviving a cancelled shipment.

```http
PUT /shipments/5/status
{"status":"IN_TRANSIT"}
```
```json
{"message":"Shipment status updated successfully","shipment_id":5,"status":"IN_TRANSIT","tracking_id":12,"tracking_timestamp":"2026-10-22T22:07:14.668981","tracking_event_created":true}
```
```http
PUT /shipments/5/status
{"status":"PICKED_UP"}
```
```json
409 {"detail":"Shipment 5 cannot move back from IN_TRANSIT to PICKED_UP."}
```

### `POST /shipments/{shipment_id}/assign-driver`
Run automatic driver selection for a shipment awaiting assignment. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.
No body.

**Behaviour:**
- Locks the order, then the shipment.
- If a delivery already exists: 200 with `"already_assigned": true` (idempotent).
- Otherwise the shipment must be `CREATED` (409) and the order `CONFIRMED` or `PROCESSING` (409).
- If no eligible driver exists: 409 `"No eligible driver and vehicle are available. The shipment remains awaiting assignment."`.
- On success: creates a `PENDING` delivery with the chosen vehicle and `assigned_at`, and moves the order from `CONFIRMED` to `PROCESSING`.

Eligibility rules are in [ARCHITECTURE.md §5.2](ARCHITECTURE.md#52-development-only-payment-simulator-and-fulfilment).
**Errors:** 404 `"Shipment not found"`.

Successful response shape (from the code): `{"message":"Driver assigned successfully","already_assigned":false,
"shipment_id","delivery_id","driver_id","vehicle_id","order_id","order_status"}`. Recorded idempotent call:

```json
{"message":"Shipment already has a driver assigned","already_assigned":true,"shipment_id":6,"delivery_id":5,"driver_id":5,"vehicle_id":null,"order_id":6,"order_status":"CONFIRMED"}
```

### `GET /shipment-items`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

```json
[{"shipment_id":1,"order_id":1,"product_id":1,"quantity":1}, "…"]
```

### `POST /shipment-items`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `shipment_id`, `order_id`, `product_id`, `quantity` (>0), all required. `(order_id, product_id)` must be
an existing order line (otherwise 422). The item's `order_id` **must be the shipment's own order** (database rule `fk_shipment_item_shipment_order`, otherwise 422).

```http
POST /shipment-items
{"shipment_id":6,"order_id":6,"product_id":3,"quantity":2}
```
```json
{"message":"Shipment item created successfully","shipment_id":6,"order_id":6,"product_id":3,"quantity":2}
```

### `GET /shipments/{shipment_id}/timeline`
Shipment header plus its tracking events in the order they were applied (`tracking_id` ascending).
**Auth:** Any authenticated user.
- Customers: own shipments only.
- Drivers: shipments assigned to them only.
- Both get 403 `"You do not have permission to access this shipment"` otherwise.

**Errors:** 404 `"Shipment not found"`.

```json
{"shipment_id":5,"order_id":5,"shipment_status":"DELIVERED","shipment_date":"2026-10-22T22:07:13.899842","estimated_delivery":"2026-10-23T01:07:13.899842","tracking_events":[{"tracking_id":10,"status":"CREATED","location":"Vellore Central Warehouse, Vellore","tracking_timestamp":"2026-10-22T22:07:13.899842","remarks":"Driver assigned"},{"tracking_id":11,"status":"PICKED_UP","location":"Vellore Central Warehouse","tracking_timestamp":"2026-10-22T22:07:14.657371","remarks":"Collected from dock 2"}, "…"]}
```

### `GET /shipments/{shipment_id}/tracking-details`
Shipment with route, warehouse, delivery and tracking history. **Auth:** Any authenticated user. Customers get
their own shipments only and drivers only shipments assigned to them (403 `"You do not have permission to access this shipment"` otherwise). **Errors:** 404.

```json
{"shipment_id":5,"order_id":5,"shipment_status":"DELIVERED","route":{"route_name":"Vellore-Chennai Route","source":"Vellore","destination":"Chennai","distance_km":140.0},"warehouse":{"warehouse_name":"Vellore Central Warehouse","city":"Vellore"},"delivery":{"driver_id":2,"delivery_status":"DELIVERED","delivery_date":"2026-10-22T22:07:14.727634"},"tracking_history":[{"status":"CREATED","location":"Vellore Central Warehouse, Vellore","timestamp":"2026-10-22T22:07:13.899842","remarks":"Driver assigned"}, "…"]}
```

---

## 13. Tracking

### `POST /tracking`
Record a tracking event, which moves the shipment status. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER, DRIVER.
A DRIVER must be assigned to the shipment's delivery (403 `"You do not have permission to update this shipment"`).

| Field | Rules |
|---|---|
| `shipment_id` | int, required (404 `"Shipment not found"`) |
| `status` | required; one of `CREATED, PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY, DELIVERED, CANCELLED` (case-insensitive, otherwise 422 `"Invalid tracking status"`) |
| `location`, `remarks` | optional strings (≤150 / ≤255 characters in the database) |

**Rules:**
- Forward-only transitions; the same status is allowed as a checkpoint.
- `CANCELLED` is allowed from any open stage.
- **Delivered or cancelled shipments accept no events (409).**
- The shipment row is locked, so concurrent events are serialised.
- An `OUT_FOR_DELIVERY` event re-opens a `FAILED` delivery (a retry).
- `DELIVERED` sets `shipment.actual_delivery` and `delivery.delivery_date`.

```http
POST /tracking
{"shipment_id":5,"status":"PICKED_UP","location":"Vellore Central Warehouse","remarks":"Collected from dock 2"}
```
```json
{"message":"Tracking event added successfully","tracking_id":11,"shipment_id":5,"status":"PICKED_UP","shipment_status":"PICKED_UP","location":"Vellore Central Warehouse","tracking_timestamp":"2026-10-22T22:07:14.657371","remarks":"Collected from dock 2"}
```
```http
POST /tracking
{"shipment_id":5,"status":"IN_TRANSIT"}        (after the shipment was delivered)
```
```json
409 {"detail":"Shipment 5 is DELIVERED and accepts no further status updates."}
```

### `GET /tracking/{shipment_id}`
Tracking events for a shipment in the order they were applied. It returns `[]` for an unknown shipment.
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

```json
[{"tracking_id":10,"shipment_id":5,"status":"CREATED","location":"Vellore Central Warehouse, Vellore","tracking_timestamp":"2026-10-22T22:07:13.899842","remarks":"Driver assigned"}, "…"]
```

---

## 14. Deliveries

### `GET /deliveries`
**Auth:** Roles: ADMIN, OPERATIONS_MANAGER, DRIVER, CUSTOMER. Results are scoped by role:
- **DRIVER:** their own deliveries.
- **CUSTOMER:** deliveries for their orders.
- **Others:** all deliveries.

Each row has `delivery_id`, `shipment_id`, `order_id`, `shipment_status`, `driver_id`, `driver_name`, `vehicle_id`,
`vehicle_registration`, `vehicle_type`, `assigned_at`, `delivery_date`, `delivery_status` and `delivery_address`. The vehicle
fields and `assigned_at` are `null` for deliveries created before migration 005.

```json
[{"delivery_id":1,"shipment_id":1,"order_id":1,"shipment_status":"DELIVERED","driver_id":2,"driver_name":"Vikram Singh","vehicle_id":null,"vehicle_registration":null,"vehicle_type":null,"assigned_at":null,"delivery_date":"2026-08-21T15:30:00","delivery_status":"DELIVERED","delivery_address":"Vellore, Tamil Nadu"}, "…"]
```

### `POST /deliveries`
Assign a shipment to a specific driver manually. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER.

**Body:** `shipment_id`, `driver_id`, `delivery_address` (required); `delivery_status` (default `"PENDING"`).

**Rules:**
- The status must be compatible with the shipment's status (for example `PENDING` for a `CREATED` or
  `IN_TRANSIT` shipment), otherwise **409** from the database rule.
- One delivery per shipment (a duplicate returns 409).
- Driver eligibility is **not** checked here, unlike `assign-driver`.

```http
POST /deliveries
{"shipment_id":6,"driver_id":5,"delivery_address":"7 Lake View, Bangalore"}
```
```json
{"message":"Delivery created successfully","delivery_id":5,"shipment_id":6,"driver_id":5,"delivery_status":"PENDING","delivery_address":"7 Lake View, Bangalore"}
```

### `PUT /deliveries/{delivery_id}/status`
Update a delivery. **Auth:** Roles: ADMIN, OPERATIONS_MANAGER, DRIVER. A DRIVER may update only their own
deliveries (403 `"You do not have permission to update this delivery"`).

**Body:** `delivery_status`, one of `PENDING, OUT_FOR_DELIVERY, DELIVERED, FAILED, CANCELLED`
(case-insensitive, otherwise 422 `"Invalid delivery status"`).

**Rules:**

| Request | Result |
|---|---|
| Same as the current status | 200, no change. |
| The delivery is `DELIVERED` or `CANCELLED` | 409. |
| `OUT_FOR_DELIVERY`, `DELIVERED`, `CANCELLED` | Recorded as a **tracking event** on the shipment (same transition rules as `POST /tracking`); `tracking_event_created: true`. |
| `FAILED` | Only while the shipment is `OUT_FOR_DELIVERY` (409 otherwise). Updates the delivery only. |
| `PENDING` (from any other status) | 409. `PENDING` is derived from the shipment and cannot be set backwards. |

**Errors:** 404 `"Delivery not found"`; 409 as above.

```http
PUT /deliveries/4/status
{"delivery_status":"OUT_FOR_DELIVERY"}
```
```json
{"message":"Delivery status updated successfully","delivery_id":4,"delivery_status":"OUT_FOR_DELIVERY","shipment_id":5,"shipment_status":"OUT_FOR_DELIVERY","tracking_event_created":true}
```
```http
PUT /deliveries/4/status
{"delivery_status":"FAILED"}
```
```json
{"message":"Delivery status updated successfully","delivery_id":4,"delivery_status":"FAILED","shipment_id":5,"shipment_status":"OUT_FOR_DELIVERY","tracking_event_created":false}
```

---

## 15. Dashboard and analytics

All endpoints in this section: **Auth:** Roles: ADMIN, OPERATIONS_MANAGER. They take no parameters and only read data.

### `GET /dashboard/summary`
Counts. `pending_deliveries` counts deliveries with status `PENDING` only.

```json
{"total_orders":6,"total_shipments":6,"total_customers":4,"total_products":12,"successful_payments":5,"pending_deliveries":2}
```

### `GET /analytics/order-status`
Order counts per status (only statuses that occur).

```json
[{"status":"SHIPPED","count":1},{"status":"CONFIRMED","count":2}, "…"]
```

### `GET /analytics/shipment-status`
Shipment counts per status.

```json
[{"status":"IN_TRANSIT","count":1},{"status":"DELIVERED","count":2}, "…"]
```

### `GET /analytics/top-products`
Top 5 products by units ordered (all orders, any status), with `total_revenue = Σ quantity × unit_price`.

```json
[{"product_id":3,"product_name":"Mechanical Keyboard","total_quantity":3,"total_revenue":10500.0},{"product_id":1,"product_name":"Laptop","total_quantity":2,"total_revenue":110000.0}, "…"]
```

### `GET /analytics/warehouse-inventory`
Every stock row with warehouse and product names; `low_stock` is `quantity <= reorder_level`.

```json
[{"warehouse":"Bangalore Logistics Hub","product":"External SSD","quantity":30,"reorder_level":8,"low_stock":false}, "…"]
```

### `GET /analytics/driver-performance`
Per driver: total deliveries and how many are `DELIVERED`.

```json
[{"driver_id":2,"driver_name":"Vikram Singh","total_deliveries":3,"completed_deliveries":2},{"driver_id":3,"driver_name":"Amit Kumar","total_deliveries":1,"completed_deliveries":0}, "…"]
```

### `GET /analytics/revenue`
- `total_revenue` = sum of `SUCCESS` payment amounts; `successful_payments` = their count.
- `total_invoiced` = sum of invoice totals that are not `CANCELLED`.

```json
{"total_revenue":155000.0,"successful_payments":5,"total_invoiced":180172.0}
```

### `GET /analytics/low-stock`
Stock rows at or below their reorder level, lowest quantity first.

```json
[]
```
Row shape (from the code): `{"warehouse","product_id","product","quantity","reorder_level"}`.

### `GET /analytics/delivery-performance`
Delivery counts by status; `success_rate` = delivered / total × 100, rounded to 2 decimals (0 when there are no
deliveries).

```json
{"total_deliveries":5,"delivered":2,"failed":0,"pending":2,"success_rate":40.0}
```

### `GET /analytics/delayed-shipments`
Shipments whose `estimated_delivery` is in the past and whose status is not `DELIVERED` or `CANCELLED`, oldest
estimate first.

```json
[{"shipment_id":2,"order_id":2,"status":"IN_TRANSIT","shipment_date":"2026-08-25T17:00:00","estimated_delivery":"2026-08-27T16:00:00"}, "…"]
```

### `GET /analytics/warehouse-stock-value`
Per warehouse: Σ `inventory.quantity × product.unit_price`, highest first.

```json
[{"warehouse":"Chennai Distribution Hub","stock_value":2550000.0},{"warehouse":"Vellore Central Warehouse","stock_value":2155400.0}, "…"]
```

---

## 16. Fulfilment and operations

The business sequence is: customer places order → customer pays → **Operations Manager approves** → shipment is
created → driver and vehicle are assigned → tracking proceeds. Routes are optional reference data and never block
any step. The workflow is described in [FULFILMENT_WORKFLOW.md](FULFILMENT_WORKFLOW.md) and
[ARCHITECTURE.md §5](ARCHITECTURE.md#5-business-workflows). Roles below are ADMIN and OPERATIONS_MANAGER unless stated.

### `POST /orders/{order_id}/cancel`
**Auth:** A, O, C (a customer only for their own order: 403 otherwise). Cancels an **unpaid** order and returns its
reserved stock to inventory exactly once (`order_inventory_reservation.released_at`). Paid or dispatched orders are
refused with 409. Repeating the call is harmless. Response: `{"message","order_id","order_status":"CANCELLED","already_cancelled","units_released"}`.

### `GET /orders/{order_id}/tracking`
**Auth:** A, O, D (only orders they deliver), C (only their own; 403 otherwise; 404 unknown order). The order's journey from
stored rows only. Keys: `order`, `items`, `payment`, `invoice_status`, `stage` (`{key,label}`), `fulfilment`, `warehouse`,
`route`, `shipment`, `assignment`, `milestones`, `tracking_events`, `latest_event`, `explanation`, `warnings`,
`live_tracking` (always `supported: false`: there is no GPS) and, for staff only, `fulfilment_events`.

What each audience gets:
- **Staff:** everything, including the plan (`fulfilment`, with `selection_note` and `approved_at`), the full warehouse address,
  the internal "Shipment planned" milestone, `not_recorded` markers for history that was never recorded, warnings about
  order/shipment mismatches, and the precise allocation reason in `explanation`.
- **Customer:** a plain-language `stage` and `explanation`; `fulfilment` is `null`; `warehouse` and `route` appear only once a
  shipment exists (origin city only, no warehouse name or address); `assignment` appears only when a real delivery row
  exists (driver name, vehicle, no ids); no `warnings`, no internal milestones, no `fulfilment_events`.
- **Driver:** no payment, no customer name, no plan, no `explanation`.

Milestones are `ORDER_PLACED`, `PAYMENT_CONFIRMED`, `ORDER_APPROVED`, (`SHIPMENT_PLANNED` for staff), `SHIPMENT_CREATED`,
`DRIVER_ASSIGNED`, `PICKED_UP`, `IN_TRANSIT`, `OUT_FOR_DELIVERY`, `DELIVERED`, with states `done`, `current`, `upcoming`,
`blocked`, `failed`, `cancelled`, `not_reached`, plus `skipped` / `not_recorded` for staff. A shipment that predates approvals
shows `ORDER_APPROVED: not_recorded` to staff and no approval step to customers; no approval is invented.

### `POST /operations/orders/{order_id}/approve`
Approve a **successfully paid, uncancelled** order and dispatch it. Idempotent. Locks the order, then:
- 404 unknown order; 409 `"This order has not been paid, so it cannot be approved."`; 409 `"This order is cancelled and cannot be approved."`.
- 409 `"No stock is reserved for this order ..."` when the order has no active reservation (see `recover-reservation`); nothing is recorded.
- Otherwise records `order_fulfilment.approved_at` / `approved_by_user_id` (first call only), re-plans the origin warehouse from the
  reservations, creates the single shipment (with its items and a `CREATED` tracking event) and allocates the least-loaded
  eligible driver and vehicle. `route_id` is set only if exactly one active route matches the origin and destination; otherwise the
  shipment has no route and no estimated delivery.
- Response (`fulfilment`-style result): `status` is `DRIVER_ASSIGNED`, `PENDING_ASSIGNMENT` (shipment created, nobody eligible, reason in
  `message`), `WAREHOUSE_UNAVAILABLE` (the planned warehouse is not ACTIVE) or `RESERVATION_INCOMPLETE`; with `shipment_id`,
  `shipment_status`, `origin_warehouse_id`, `driver_id`, `vehicle_id`, `route_id`.

### `POST /operations/orders/{order_id}/retry-fulfilment`
Re-checks an order. For a paid, approved order without a shipment it dispatches; for a shipment without a driver it tries to assign one;
otherwise it re-plans and reports. A paid order that has not been approved gets 409 `"... has not been approved yet. Approve it first."`.

### `POST /operations/orders/{order_id}/recover-reservation`
Reserves stock for a **paid** order that predates reservations (no `order_inventory_reservation` rows). Body:
`{"confirm_stock_not_deducted": true}` (required `true`; the database cannot show whether an old order already took its stock, so a person
must vouch for it). Locks the order and the stock rows, takes the stock from active warehouses, writes the reservations and a
`STOCK_RECOVERED` log entry. It **never** approves the order, changes its status, creates a shipment or invents payment/tracking events.
- 200 `{"status":"RESERVED","recovered":true,"reserved":[...],"approved":false,"message"}`, or `{"status":"ALREADY_RESERVED","recovered":false}` on repetition.
- 409 when the order is unpaid / failed-payment, cancelled, already shipped, has no items, had a reservation released earlier, the confirmation is
  missing, or stock is insufficient (`"Insufficient stock for <name>. Only N available."`). Nothing is reserved on any failure.

### `POST /operations/release-abandoned`
Query `older_than_minutes` (optional, ≥1; default `UNPAID_ORDER_TTL_MINUTES`, 1440). Cancels unpaid orders older than that and returns
their stock once. Response: `{"orders_cancelled","units_released","orders":[...]}`. It is run by a person; nothing schedules it.

### `POST /shipments/{shipment_id}/assignment`
Assign or reassign the driver and vehicle. Body `{"driver_id": int, "vehicle_id": int | omitted}`; unknown fields are rejected. The pair must satisfy the
automatic rules (driver available and licensed, vehicle in service and currently assigned to that driver, driver below
`MAX_OPEN_DELIVERIES_PER_DRIVER`, vehicle capacity). Errors: 404, 409 with the reasons (cancelled order, unpaid order, closed shipment,
delivery no longer `PENDING`, ineligible pair or a vehicle that is not the driver's current one); 422 when the driver has several vehicles and none was chosen. Success returns `driver_id`, `driver_name`, `vehicle_id`, `vehicle_registration`.

### `GET /operations/shipments/{shipment_id}/assignment-options`
Every driver/vehicle pair with `eligible`, `reasons` (why a pair cannot be chosen), `open_deliveries` and `remaining_capacity_kg`, plus
`shipment_weight_kg`, `weight_note`, `current` and a `summary` when nobody is eligible.

### `GET /operations/shipments`
Server-side shipment desk. Query: `q` (shipment/order id, customer, warehouse, driver, vehicle), `status`, `warehouse_id`, `assignment`
(`assigned`|`unassigned`), `delayed`, `sort` (`shipment_id`, `shipment_date`, `estimated_delivery`, `status`, `customer`, `warehouse`),
`direction`, `page`, `page_size` (≤100). Returns `{items,total,page,page_size,pages}`. Rows carry the order, customer, warehouse, route (all
`null` if the shipment has none), destination, status, `delayed`, driver, vehicle (`vehicle_recorded` is false for older deliveries),
`assigned_at`, `fulfilment_status` and `pending_reason`.

### `GET /operations/shipments/{shipment_id}`
The staff tracking view (as `GET /orders/{id}/tracking`) of that shipment. 404 if unknown.

### `GET /operations/orders`
Query `stage` (`attention` default, `awaiting_approval`, `awaiting_payment`, `all`), `q`, `page`, `page_size`. `attention` is orders that are blocked, or paid
and not yet shipped. Rows: `order_id`, `order_date`, `order_status`, `customer_name`, `destination_city`, `shipping_address`, `payment_status`,
`fulfilment_status`, `reason_code`, `reason_detail`, `origin_warehouse_name`, `shipment_id`, `has_plan`, `approved`, `approved_at` and `exception`
(`{code, detail}` or `null`, for example `RESERVATION_MISSING` or `WAREHOUSE_INACTIVE`).

### `GET /operations/summary`
`orders` (`total`, `awaiting_payment`, `awaiting_approval`, `awaiting_fulfilment` = approved but not shipped, `blocked`), `shipments` (`total`,
`awaiting_assignment`, `in_transit`, `awaiting_pickup`, `delivered`, `cancelled`, `delayed`), `fleet` (drivers/vehicles totals and availability,
`max_open_deliveries_per_driver`), `warehouses` (`total`, `active`, `low_stock_lines`), `data_consistency` (orders whose status disagrees with
their shipment; reported, never rewritten) and `delay_rule`.

### `GET /operations/warehouses`
Every warehouse: `warehouse_id`, `warehouse_name`, `address`, `city`, `status`, `is_active`, `manager_employee_id`, `manager_name`, `capacity`,
`units_available`, `units_reserved`, `units_on_hand` (= available + reserved), `utilisation_percent` / `utilisation_basis` (capacity has no
recorded unit; utilisation assumes units on hand), `low_stock_lines`, `inventory[]` (`product_id`, `product_name`, `available`, `reserved`, `on_hand`,
`reorder_level`, `low_stock`, `out_of_stock`, `last_updated`), `outgoing_shipments` (`awaiting_pickup`, `in_flight`, `delivered`, `cancelled`),
`incoming_shipments` (`supported: false`: transfers are not modelled), `orders_in_fulfilment` (`count`, `orders[]`), `outgoing_routes` (informational
count of active routes from the city) and `data_gaps[]`. Products have no SKU in the database; `product_id` identifies them.
