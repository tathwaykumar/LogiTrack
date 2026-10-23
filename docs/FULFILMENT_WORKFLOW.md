# Order fulfilment workflow

How an order becomes a delivery, what is automatic, what needs a person, and what the system will not invent.
Code: `backend/fulfilment.py` (rules), `backend/operations.py` (read-only operations views), endpoints in
`backend/main.py`, schema in `database/migrations/005_order_fulfilment_planning.sql`.

## Order to delivery

1. **Checkout** (`POST /shop/checkout`). The customer enters a full delivery address. In one transaction the API locks
   products and stock rows, reserves stock from ACTIVE warehouses (one warehouse that holds everything if there is one;
   otherwise several, with a note), creates the order and invoice, and writes a **fulfilment plan** (`order_fulfilment`):
   the origin warehouse and why it was chosen. Only stock and warehouse status decide this. Routes do not.
2. **Payment** (existing simulator, `POST /shop/payments/simulate`). A successful payment confirms the order and
   nothing more: no shipment, driver or vehicle yet. The customer sees "Awaiting approval". A failed or missing
   payment can never lead to a shipment.
3. **Approval** (`POST /operations/orders/{id}/approve`, Admin or Operations Manager). Only a successfully paid,
   uncancelled order can be approved; who approved and when is stored on the plan. Approval refreshes the plan from
   current stock and routes, creates the single shipment, and allocates an eligible driver and vehicle if the rules
   allow. A configured route is attached only when exactly one active route matches; otherwise the shipment has no route
   and no estimated delivery, and everything still proceeds. Repeating the call never creates a second shipment.
4. **Assignment.** Automatic at approval. If nobody is eligible, the shipment stays `CREATED` (pending allocation),
   no assignment row is invented, and the reason is shown to operations. An Operations Manager can assign or
   reassign (`POST /shipments/{id}/assignment`, which lists eligible pairs and the reason each other pair is not)
   or re-check (`POST /operations/orders/{id}/retry-fulfilment`, only after approval).
5. **Delivery.** The driver moves the shipment forward only (picked up → in transit → out for delivery → delivered;
   a failed attempt is possible while out for delivery). The backend validates every transition; the order status
   follows the shipment and never moves backwards or revives a cancelled order.
6. **Cancellation.** An unpaid order can be cancelled by its customer or operations (`POST /orders/{id}/cancel`).
   Paid orders cannot. Reserved stock is returned exactly once (`order_inventory_reservation.released_at`),
   also under concurrent requests. `POST /operations/release-abandoned` cancels unpaid orders older than
   `UNPAID_ORDER_TTL_MINUTES` the same way. It is triggered by a person, not a scheduler.

## Assignment rules

A driver/vehicle pair is eligible when the driver is `AVAILABLE`, employed (ACTIVE), has an active login and an
unexpired licence, has a current vehicle assignment, that vehicle is in service and not shared, the driver has fewer
than `MAX_OPEN_DELIVERIES_PER_DRIVER` open deliveries, and the vehicle's free capacity (capacity minus the weight of
its open deliveries) covers the shipment. If product weights are unknown, capacity is not checked and the response
says so. Allocation runs under an advisory lock plus row locks, so a driver or vehicle cannot be double-booked.
The chosen vehicle and the assignment time are stored on the delivery.

## Tables and columns added by migration 005

| Object | Purpose |
|---|---|
| `order_fulfilment` | One plan per order: status (PLANNED, BLOCKED, AWAITING_ASSIGNMENT, ASSIGNED, CANCELLED), reason code/detail, origin warehouse, route, route basis, selection note, and (migration 006) `approved_at` / `approved_by_user_id`. |
| `demo_seed_record` | (migration 006) Lists every row added by `backend/seed_demo_data.py`, so demo data can be told apart from real data. |
| `order_fulfilment_event` | Append-only audit log of planning and assignment decisions. |
| `delivery.vehicle_id`, `delivery.assigned_at` | The persisted vehicle and assignment time. |
| `orders.destination_city` | Optional free-text city. Used only to find an informational route. |
| `shipment.route_id` (migration 007) | Now nullable: a shipment does not need a route. |
| `order_inventory_reservation.released_at` | Marks a reservation as returned to stock. |
| trigger `trg_sync_order_with_shipment` | Keeps the order status in step with its shipment, forward only. |

The migration only adds. It is re-runnable, changes no existing row, and does not back-fill old records.

## Endpoints added or changed

| Endpoint | Roles | Purpose |
|---|---|---|
| `POST /shop/checkout` | Customer | Now takes `destination_city` and returns a `fulfilment` plan block. |
| `POST /orders/{id}/cancel` | Admin, Operations, Customer (own) | Cancel an unpaid order, release stock once. |
| `GET /orders/{id}/tracking` | All (scoped) | Milestone timeline; customers and drivers see a reduced view. |
| `GET /operations/summary` | Admin, Operations | Counts for the dashboard, plus data-consistency findings. |
| `GET /operations/warehouses` | Admin, Operations | Every warehouse: stock, reserved, capacity, shipments, orders, data gaps. |
| `GET /operations/shipments` | Admin, Operations | Search, filter, sort, pagination. |
| `GET /operations/orders` | Admin, Operations | Orders needing attention or awaiting payment. |
| `GET /operations/shipments/{id}` | Admin, Operations | One shipment with its journey. |
| `GET /operations/shipments/{id}/assignment-options` | Admin, Operations | Every pair, eligible or not, with reasons. |
| `POST /operations/orders/{id}/recover-reservation` | Admin, Operations | Reserve stock for a paid order that predates reservations (explicit confirmation required; never approves). |
| `POST /operations/orders/{id}/approve` | Admin, Operations | Approve a paid order; creates the shipment and allocates a driver and vehicle. Idempotent. |
| `POST /shipments/{id}/assignment` | Admin, Operations | Manual assign/reassign with validation. |
| `POST /operations/orders/{id}/retry-fulfilment` | Admin, Operations | Idempotent re-plan or dispatch. |
| `POST /operations/release-abandoned` | Admin, Operations | Cancel stale unpaid orders. |
| `GET /orders`, `GET /deliveries` | existing | Gained payment/fulfilment fields, and driver, vehicle, assignment time, order and shipment status. |

## What customers see, and what staff see

Customers (and drivers) get a plain-language stage derived only from stored rows: *Awaiting payment*, *Payment
failed*, *Awaiting approval*, *Preparing shipment*, *Driver assigned*, *Picked up*, *In transit*, *Out for delivery*,
*Delivered* or *Cancelled*. A driver and vehicle appear only when a real `delivery` row exists. Customers are never
shown allocation diagnostics, blocked-plan reasons, warehouse names or addresses, or the internal planning step.
Operations staff see the full detail: the precise reason a shipment has no driver, every candidate pair with the
reason it cannot be used, blocked plans, the fulfilment log, and data inconsistencies. API error text is also
normalised in the frontend (`friendlyError`): validation arrays, database text and bare status codes are replaced by
a sentence a person can act on.

## Configuration

`MAX_OPEN_DELIVERIES_PER_DRIVER` (default 3) and `UNPAID_ORDER_TTL_MINUTES` (default 1440). Both optional.

## Limitations

- Warehouse `capacity` has no recorded unit; utilisation assumes units on hand and says so.
- There are no stock transfers, so “incoming shipments” is reported as not tracked.
- No GPS, intermediate stops or live ETAs exist. Estimated delivery exists only when a configured route supplies a duration.
- Routes never block fulfilment. A shipment without a matching route simply has none.
- A split order ships from one warehouse; the selection note records that stock came from several.
- Vehicle type is shown but not used in matching.
- Drivers cannot “accept” a job; assignment is by the system or operations.
- Records from before migration 005 have no plan, vehicle or assignment time, and are shown as such. A few older
  orders disagree with their shipments; they are reported on the dashboard, not rewritten.
