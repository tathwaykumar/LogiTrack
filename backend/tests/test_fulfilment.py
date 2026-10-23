"""Phase 3B: inventory reservations, payment fulfilment and driver assignment."""
import itertools
import threading
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

import main
from conftest import Factory
from main import app
from models import (
    Delivery, Inventory, Invoice, Order, OrderFulfilment, OrderInventoryReservation, Payment,
    Shipment, ShipmentItem, ShipmentTracking,
)


def checkout(client, headers, items, address="42 Market Road, Chennai"):
    return client.post(
        "/shop/checkout",
        json={
            "items": [{"product_id": p.product_id, "quantity": q} for p, q in items],
            "shipping_address": address,
        },
        headers=headers,
    )


_ops_numbers = itertools.count(1000)


def ops_headers():
    """A fresh Operations Manager login (usernames are unique across calls and threads)."""
    factory = Factory()
    factory._counter = next(_ops_numbers)
    return factory.user("OPERATIONS_MANAGER")[1]


def pay_only(client, headers, order_id, outcome="SUCCESS"):
    """The customer's payment on its own. A successful payment does not dispatch anything."""
    return client.post(
        "/shop/payments/simulate",
        json={"order_id": order_id, "outcome": outcome},
        headers=headers,
    )


def approve(client, order_id, headers=None):
    return client.post(f"/operations/orders/{order_id}/approve", headers=headers or ops_headers())


class _Dispatched:
    """Response-like: the payment response with `fulfilment` replaced by the approval's dispatch result."""

    def __init__(self, payment, dispatch):
        self.status_code = payment.status_code
        self._body = {**payment.json(), "fulfilment": dispatch.json()}
        self.text = payment.text

    def json(self):
        return self._body


def pay(client, headers, order_id, outcome="SUCCESS"):
    """Pay, then (for a successful payment) approve as an Operations Manager, which is what dispatches.

    Most tests care about what happens after dispatch, so this keeps the pay-then-approve sequence in one
    call. Tests of the sequence itself use pay_only and approve directly.
    """
    payment = pay_only(client, headers, order_id, outcome)
    if outcome != "SUCCESS" or payment.status_code != 200:
        return payment
    dispatch = approve(client, order_id)
    return _Dispatched(payment, dispatch) if dispatch.status_code == 200 else dispatch


def count(db, model, *criteria):
    db.expire_all()
    return db.query(func.count()).select_from(model).filter(*criteria).scalar()


def stock_of(db, warehouse, product):
    db.expire_all()
    return db.query(Inventory.quantity).filter(
        Inventory.warehouse_id == warehouse.warehouse_id,
        Inventory.product_id == product.product_id,
    ).scalar()


@pytest.fixture
def shop(make):
    """One customer, a Vellore warehouse with stock, a route to Chennai and an eligible driver."""
    customer, headers = make.customer()
    warehouse = make.warehouse("Vellore")
    product = make.product(price=250)
    make.stock(warehouse, product, 10)
    route = make.route("Vellore", "Chennai")
    make.route("Vellore", "Bangalore")
    driver, vehicle, _ = make.driver()
    return {
        "customer": customer, "headers": headers, "warehouse": warehouse,
        "product": product, "route": route, "driver": driver, "vehicle": vehicle,
    }


# --- Checkout reservations -------------------------------------------------

def test_checkout_records_reservation_and_deducts_stock(client, db, shop):
    response = checkout(client, shop["headers"], [(shop["product"], 3)])
    assert response.status_code == 201, response.text
    order_id = response.json()["order"]["order_id"]

    reservations = db.query(OrderInventoryReservation).filter_by(order_id=order_id).all()
    assert [(r.warehouse_id, r.product_id, r.reserved_quantity) for r in reservations] == [
        (shop["warehouse"].warehouse_id, shop["product"].product_id, 3)
    ]
    assert reservations[0].created_at is not None
    assert stock_of(db, shop["warehouse"], shop["product"]) == 7


def test_checkout_failure_rolls_back_stock_and_reservations(client, db, make, shop, monkeypatch):
    other = make.product()
    make.stock(shop["warehouse"], other, 1)

    # Insufficient stock on the second product: nothing from the first may persist.
    response = checkout(client, shop["headers"], [(shop["product"], 2), (other, 5)])
    assert response.status_code == 409
    assert stock_of(db, shop["warehouse"], shop["product"]) == 10
    assert count(db, OrderInventoryReservation) == 0
    assert count(db, Order) == 0

    # Failure after stock and reservations were flushed (invoice step) also rolls back.
    def broken_invoice(**kwargs):
        raise RuntimeError("simulated failure after reservation")

    monkeypatch.setattr(main, "Invoice", broken_invoice)
    failing_client = TestClient(app, raise_server_exceptions=False)
    response = checkout(failing_client, shop["headers"], [(shop["product"], 2)])
    assert response.status_code == 500
    assert stock_of(db, shop["warehouse"], shop["product"]) == 10
    assert count(db, OrderInventoryReservation) == 0
    assert count(db, Order) == 0


def test_multiple_warehouses_supply_one_order(client, db, make, shop):
    second = make.warehouse("Chennai")
    make.route("Chennai", "Bangalore")
    widget = make.product(price=40)
    # Product A: 10 in Vellore (warehouse id lower, consumed first) + 4 in Chennai.
    make.stock(second, shop["product"], 4)
    # Product B only in Chennai, so Chennai supplies the most units overall.
    make.stock(second, widget, 20)

    response = checkout(
        client, shop["headers"], [(shop["product"], 12), (widget, 15)],
        address="7 Lake View, Bangalore",
    )
    assert response.status_code == 201, response.text
    order_id = response.json()["order"]["order_id"]

    rows = (
        db.query(OrderInventoryReservation)
        .filter_by(order_id=order_id)
        .order_by(OrderInventoryReservation.warehouse_id, OrderInventoryReservation.product_id)
        .all()
    )
    assert [(r.warehouse_id, r.product_id, r.reserved_quantity) for r in rows] == [
        (shop["warehouse"].warehouse_id, shop["product"].product_id, 10),
        (second.warehouse_id, shop["product"].product_id, 2),
        (second.warehouse_id, widget.product_id, 15),
    ]
    assert stock_of(db, shop["warehouse"], shop["product"]) == 0
    assert stock_of(db, second, shop["product"]) == 2
    assert stock_of(db, second, widget) == 5

    paid = pay(client, shop["headers"], order_id)
    assert paid.status_code == 200, paid.text
    fulfilment = paid.json()["fulfilment"]
    assert fulfilment["origin_warehouse_id"] == second.warehouse_id  # 17 units vs 10
    assert fulfilment["source_warehouse_ids"] == [shop["warehouse"].warehouse_id, second.warehouse_id]

    shipments = db.query(Shipment).filter_by(order_id=order_id).all()
    assert len(shipments) == 1
    items = db.query(ShipmentItem).filter_by(shipment_id=shipments[0].shipment_id).all()
    assert sorted((i.product_id, i.quantity) for i in items) == [
        (shop["product"].product_id, 12), (widget.product_id, 15),
    ]
    tracking = db.query(ShipmentTracking).filter_by(shipment_id=shipments[0].shipment_id).one()
    assert "Consolidated from warehouses" in tracking.remarks


# --- Payment fulfilment ----------------------------------------------------

def test_successful_payment_creates_one_shipment(client, db, shop):
    order_id = checkout(client, shop["headers"], [(shop["product"], 2)]).json()["order"]["order_id"]

    response = pay(client, shop["headers"], order_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "DEVELOPMENT_ONLY_SIMULATION"
    assert body["payment_status"] == "SUCCESS"
    assert body["invoice_status"] == "PAID"
    assert body["order_status"] == "CONFIRMED"          # payment alone does not dispatch
    assert body["fulfilment"]["status"] == "DRIVER_ASSIGNED"   # ... approval does (pay() approves)
    db.expire_all()
    assert db.get(Order, order_id).order_status == "PROCESSING"
    assert body["fulfilment"]["driver_id"] == shop["driver"].employee_id
    assert body["fulfilment"]["vehicle_id"] == shop["vehicle"].vehicle_id

    shipment = db.query(Shipment).filter_by(order_id=order_id).one()
    assert shipment.warehouse_id == shop["warehouse"].warehouse_id
    assert shipment.route_id == shop["route"].route_id  # destination matches the address
    assert shipment.shipment_status == "CREATED"
    assert shipment.estimated_delivery is not None

    tracking = db.query(ShipmentTracking).filter_by(shipment_id=shipment.shipment_id).all()
    assert [t.status for t in tracking] == ["CREATED"]
    assert tracking[0].status in main.TRACKING_STATUSES

    delivery = db.query(Delivery).filter_by(shipment_id=shipment.shipment_id).one()
    assert delivery.driver_id == shop["driver"].employee_id
    assert delivery.delivery_status == "PENDING"
    assert delivery.delivery_address == "42 Market Road, Chennai"

    assert db.query(Payment).filter_by(order_id=order_id).one().payment_method == "SIMULATED_TEST_MODE"


def test_repeated_successful_payment_is_idempotent(client, db, shop):
    order_id = checkout(client, shop["headers"], [(shop["product"], 2)]).json()["order"]["order_id"]
    first = pay(client, shop["headers"], order_id)
    assert first.status_code == 200

    second = pay(client, shop["headers"], order_id)
    assert second.status_code == 200
    body = second.json()
    assert body["already_processed"] is True
    assert body["fulfilment"]["shipment_id"] == first.json()["fulfilment"]["shipment_id"]

    assert count(db, Shipment, Shipment.order_id == order_id) == 1
    assert count(db, OrderInventoryReservation, OrderInventoryReservation.order_id == order_id) == 1
    assert count(db, Delivery) == 1
    assert count(db, ShipmentTracking) == 1
    assert count(db, Payment) == 1
    assert stock_of(db, shop["warehouse"], shop["product"]) == 8

    # A late FAILED result cannot undo a successful payment.
    assert pay(client, shop["headers"], order_id, "FAILED").status_code == 409


def test_failed_payment_creates_no_shipment(client, db, shop):
    order_id = checkout(client, shop["headers"], [(shop["product"], 2)]).json()["order"]["order_id"]

    response = pay(client, shop["headers"], order_id, "FAILED")
    assert response.status_code == 200
    body = response.json()
    assert body["payment_status"] == "FAILED"
    assert body["order_status"] == "PENDING"
    assert body["invoice_status"] == "ISSUED"
    assert body["fulfilment"] is None
    assert count(db, Shipment) == 0
    assert count(db, Delivery) == 0
    assert count(db, ShipmentTracking) == 0
    # Reservation stays with the still-pending order.
    assert count(db, OrderInventoryReservation, OrderInventoryReservation.order_id == order_id) == 1

    # A retry that succeeds then fulfils exactly once.
    retry = pay(client, shop["headers"], order_id)
    assert retry.status_code == 200
    assert retry.json()["fulfilment"]["status"] == "DRIVER_ASSIGNED"
    assert count(db, Shipment) == 1


def test_missing_reservations_are_handled_safely(client, db, make, shop):
    order = make.legacy_order(shop["customer"], shop["product"], quantity=2)

    response = pay_only(client, shop["headers"], order.order_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["payment_status"] == "SUCCESS"
    assert body["invoice_status"] == "PAID"
    assert body["order_status"] == "CONFIRMED"
    assert body["fulfilment"]["status"] == "AWAITING_APPROVAL"

    # Approval is refused (not recorded) while no stock is reserved: staff must recover the reservation first.
    approval = approve(client, order.order_id)
    assert approval.status_code == 409 and "No stock is reserved" in approval.json()["detail"]
    db.expire_all()
    assert db.get(OrderFulfilment, order.order_id) is None      # no approval was recorded

    assert count(db, Shipment) == 0
    assert count(db, Delivery) == 0
    assert count(db, OrderInventoryReservation) == 0  # nothing invented
    assert stock_of(db, shop["warehouse"], shop["product"]) == 10

    repeat = pay_only(client, shop["headers"], order.order_id)
    assert repeat.json()["already_processed"] is True
    assert count(db, Shipment) == 0


def test_incomplete_reservations_are_not_fulfilled(client, db, make, shop):
    order = make.legacy_order(shop["customer"], shop["product"], quantity=3)
    make._save(OrderInventoryReservation(
        order_id=order.order_id, warehouse_id=shop["warehouse"].warehouse_id,
        product_id=shop["product"].product_id, reserved_quantity=1,
    ))

    body = pay(client, shop["headers"], order.order_id).json()
    assert body["fulfilment"]["status"] == "RESERVATION_INCOMPLETE"
    assert body["order_status"] == "CONFIRMED"
    assert count(db, Shipment) == 0


def test_no_route_from_origin_does_not_block_fulfilment(client, db, make):
    customer, headers = make.customer()
    warehouse = make.warehouse("Madurai")  # no route leaves Madurai
    product = make.product()
    make.stock(warehouse, product, 5)
    make.driver()

    order_id = checkout(client, headers, [(product, 1)]).json()["order"]["order_id"]
    body = pay(client, headers, order_id).json()
    assert body["fulfilment"]["status"] == "DRIVER_ASSIGNED"
    assert body["invoice_status"] == "PAID"
    shipment = db.query(Shipment).one()
    assert shipment.route_id is None and shipment.estimated_delivery is None   # nothing made up


# --- Driver and vehicle assignment -----------------------------------------

INELIGIBLE_DRIVERS = {
    "no_driver": None,
    "driver_on_leave": dict(availability="ON_LEAVE"),
    "employee_inactive": dict(employment="INACTIVE"),
    "licence_expired": dict(license_expiry=date.today() - timedelta(days=1)),
    "vehicle_in_maintenance": dict(vehicle_status="MAINTENANCE"),
    "no_vehicle_assigned": dict(with_vehicle=False),
}


@pytest.mark.parametrize("case", INELIGIBLE_DRIVERS)
def test_no_eligible_driver_leaves_shipment_pending(client, db, make, case):
    customer, headers = make.customer()
    warehouse = make.warehouse("Vellore")
    product = make.product()
    make.stock(warehouse, product, 5)
    make.route("Vellore", "Chennai")
    if INELIGIBLE_DRIVERS[case] is not None:
        make.driver(**INELIGIBLE_DRIVERS[case])

    order_id = checkout(client, headers, [(product, 1)]).json()["order"]["order_id"]
    body = pay(client, headers, order_id).json()

    assert body["payment_status"] == "SUCCESS"
    assert body["invoice_status"] == "PAID"
    assert body["order_status"] == "CONFIRMED"
    assert body["fulfilment"]["status"] == "PENDING_ASSIGNMENT"
    assert body["fulfilment"]["driver_id"] is None

    shipment = db.query(Shipment).filter_by(order_id=order_id).one()
    assert shipment.shipment_status == "CREATED"
    assert count(db, Delivery) == 0
    tracking = db.query(ShipmentTracking).filter_by(shipment_id=shipment.shipment_id).one()
    assert tracking.status == "CREATED"
    assert "Awaiting driver assignment" in tracking.remarks


def test_vehicle_shared_with_another_driver_is_not_used(client, db, make, shop):
    # Remove the fixture driver's eligibility by sharing their vehicle with a second driver.
    make.driver(vehicle=shop["vehicle"])

    order_id = checkout(client, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]
    assert pay(client, shop["headers"], order_id).json()["fulfilment"]["status"] == "PENDING_ASSIGNMENT"
    assert count(db, Delivery) == 0


def test_least_loaded_eligible_driver_is_chosen(client, db, make, shop):
    second_driver, second_vehicle, _ = make.driver()
    first = checkout(client, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]
    second = checkout(client, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]

    assert pay(client, shop["headers"], first).json()["fulfilment"]["driver_id"] == shop["driver"].employee_id
    body = pay(client, shop["headers"], second).json()
    assert body["fulfilment"]["driver_id"] == second_driver.employee_id
    assert body["fulfilment"]["vehicle_id"] == second_vehicle.vehicle_id


def test_operations_can_assign_pending_shipment_later(client, db, make):
    customer, headers = make.customer()
    warehouse = make.warehouse("Vellore")
    product = make.product()
    make.stock(warehouse, product, 5)
    make.route("Vellore", "Chennai")
    _, ops_headers = make.user("OPERATIONS_MANAGER")

    order_id = checkout(client, headers, [(product, 1)]).json()["order"]["order_id"]
    shipment_id = pay(client, headers, order_id).json()["fulfilment"]["shipment_id"]

    still_none = client.post(f"/shipments/{shipment_id}/assign-driver", headers=ops_headers)
    assert still_none.status_code == 409
    assert count(db, Delivery) == 0

    driver, vehicle, _ = make.driver()
    assigned = client.post(f"/shipments/{shipment_id}/assign-driver", headers=ops_headers)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["driver_id"] == driver.employee_id
    assert assigned.json()["vehicle_id"] == vehicle.vehicle_id
    assert assigned.json()["order_status"] == "PROCESSING"

    again = client.post(f"/shipments/{shipment_id}/assign-driver", headers=ops_headers)
    assert again.status_code == 200
    assert again.json()["already_assigned"] is True
    assert count(db, Delivery) == 1


# --- Authorization ---------------------------------------------------------

def test_unauthenticated_and_wrong_role_requests_are_rejected(client, db, make, shop):
    order_id = checkout(client, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]
    _, driver_headers = make.user("DRIVER")
    _, admin_headers = make.user("ADMIN")

    assert client.post(
        "/shop/payments/simulate", json={"order_id": order_id, "outcome": "SUCCESS"}
    ).status_code in (401, 403)
    assert client.post(
        "/shop/payments/simulate", json={"order_id": order_id, "outcome": "SUCCESS"},
        headers={"Authorization": "Bearer not-a-token"},
    ).status_code == 401
    # Payment simulation is customer-only, even for admins and drivers.
    assert pay(client, driver_headers, order_id).status_code == 403
    assert pay(client, admin_headers, order_id).status_code == 403
    assert count(db, Payment) == 0
    assert count(db, Shipment) == 0

    shipment_id = pay(client, shop["headers"], order_id).json()["fulfilment"]["shipment_id"]
    # Driver assignment is limited to ADMIN / OPERATIONS_MANAGER.
    for headers in (shop["headers"], driver_headers):
        assert client.post(f"/shipments/{shipment_id}/assign-driver", headers=headers).status_code == 403
    assert client.post(f"/shipments/{shipment_id}/assign-driver").status_code in (401, 403)


def test_customer_cannot_pay_or_fulfil_another_customers_order(client, db, make, shop):
    order_id = checkout(client, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]
    _, intruder_headers = make.customer()

    for outcome in ("SUCCESS", "FAILED"):
        response = pay(client, intruder_headers, order_id, outcome)
        assert response.status_code == 404

    assert count(db, Payment) == 0
    assert count(db, Shipment) == 0
    db.expire_all()
    assert db.query(Order.order_status).filter_by(order_id=order_id).scalar() == "PENDING"
    assert db.query(Invoice.invoice_status).filter_by(order_id=order_id).scalar() == "ISSUED"


# --- Concurrency -----------------------------------------------------------

def run_concurrently(n, func):
    barrier = threading.Barrier(n)
    results = [None] * n

    def worker(i):
        barrier.wait()
        try:
            results[i] = func()
        except Exception as error:  # surface it in the assertion, not a lost thread
            results[i] = error

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def test_concurrent_successful_payments_fulfil_once(db, shop):
    with TestClient(app) as setup_client:
        order_id = checkout(setup_client, shop["headers"], [(shop["product"], 2)]).json()["order"]["order_id"]

    def attempt():
        with TestClient(app) as c:
            return pay(c, shop["headers"], order_id)

    responses = run_concurrently(6, attempt)
    assert all(r is not None and r.status_code == 200 for r in responses), [
        r and r.text for r in responses
    ]
    assert sum(not r.json()["already_processed"] for r in responses) == 1
    assert len({r.json()["fulfilment"]["shipment_id"] for r in responses}) == 1

    assert count(db, Shipment) == 1
    assert count(db, Delivery) == 1
    assert count(db, ShipmentTracking) == 1
    assert count(db, Payment) == 1
    assert count(db, OrderInventoryReservation) == 1
    assert stock_of(db, shop["warehouse"], shop["product"]) == 8


def test_concurrent_driver_assignment_creates_one_delivery(db, make):
    customer, headers = make.customer()
    warehouse = make.warehouse("Vellore")
    product = make.product()
    make.stock(warehouse, product, 5)
    make.route("Vellore", "Chennai")
    _, ops_headers = make.user("OPERATIONS_MANAGER")

    with TestClient(app) as c:
        order_id = checkout(c, headers, [(product, 1)]).json()["order"]["order_id"]
        shipment_id = pay(c, headers, order_id).json()["fulfilment"]["shipment_id"]
    make.driver()
    make.driver()

    def attempt():
        with TestClient(app) as c:
            return c.post(f"/shipments/{shipment_id}/assign-driver", headers=ops_headers)

    responses = run_concurrently(5, attempt)
    assert all(r is not None and r.status_code == 200 for r in responses), [
        r and r.text for r in responses
    ]
    assert sum(not r.json()["already_assigned"] for r in responses) == 1
    assert count(db, Delivery) == 1
