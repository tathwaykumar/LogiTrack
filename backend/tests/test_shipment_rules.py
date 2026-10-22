"""Phase 3B follow-up: one active shipment per order, and strict route selection."""
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import main
from main import app
from models import (
    Delivery, Inventory, Invoice, Order, OrderInventoryReservation, Payment,
    Shipment,
)
from test_fulfilment import checkout, count, pay, run_concurrently, shop, stock_of  # noqa: F401


def create_shipment(client, headers, order_id, warehouse, route):
    return client.post(
        "/shipments",
        json={
            "order_id": order_id,
            "warehouse_id": warehouse.warehouse_id,
            "route_id": route.route_id,
        },
        headers=headers,
    )


def set_status(client, headers, shipment_id, status):
    return client.put(f"/shipments/{shipment_id}/status", json={"status": status}, headers=headers)


def active_shipments(db, order_id):
    return count(db, Shipment, Shipment.order_id == order_id, Shipment.shipment_status != "CANCELLED")


@pytest.fixture
def ops(make):
    return make.user("OPERATIONS_MANAGER")[1]


# --- One active shipment per order -----------------------------------------

def test_database_rejects_second_active_shipment(db, make, shop):
    order = make.legacy_order(shop["customer"], shop["product"])
    insert = text(
        "INSERT INTO shipment (order_id, warehouse_id, route_id, shipment_status) "
        "VALUES (:o, :w, :r, :s)"
    )
    params = {"o": order.order_id, "w": shop["warehouse"].warehouse_id, "r": shop["route"].route_id}

    db.execute(insert, {**params, "s": "CANCELLED"})
    db.execute(insert, {**params, "s": "CANCELLED"})  # cancelled rows never conflict
    db.execute(insert, {**params, "s": "CREATED"})
    db.commit()
    with pytest.raises(IntegrityError) as error:
        db.execute(insert, {**params, "s": "IN_TRANSIT"})
        db.commit()
    db.rollback()
    assert main.is_active_shipment_conflict(error.value)


def test_duplicate_shipment_creation_returns_409(client, db, shop, ops):
    order_id = checkout(client, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]
    shipment_id = pay(client, shop["headers"], order_id).json()["fulfilment"]["shipment_id"]
    assert shipment_id is not None

    response = create_shipment(client, ops, order_id, shop["warehouse"], shop["route"])
    assert response.status_code == 409
    assert response.json()["detail"] == main.ACTIVE_SHIPMENT_CONFLICT
    assert count(db, Shipment, Shipment.order_id == order_id) == 1

    # Payment-success idempotency is unchanged.
    repeat = pay(client, shop["headers"], order_id).json()
    assert repeat["already_processed"] is True
    assert repeat["fulfilment"]["shipment_id"] == shipment_id


def test_other_shipment_integrity_errors_are_not_reported_as_duplicates(client, db, make, shop, ops):
    response = create_shipment(client, ops, 999999, shop["warehouse"], shop["route"])
    assert response.status_code == 404

    # An unknown route is a foreign-key error, not an active-shipment conflict,
    # so POST /shipments keeps its previous behaviour for it.
    order = make.legacy_order(shop["customer"], shop["product"])
    shop["route"].route_id = 999999
    raw_client = TestClient(app, raise_server_exceptions=False)
    response = create_shipment(raw_client, ops, order.order_id, shop["warehouse"], shop["route"])
    assert response.status_code == 500
    assert count(db, Shipment) == 0


def test_cancelled_shipment_can_be_replaced(client, db, shop, ops):
    order_id = checkout(client, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]
    original = pay(client, shop["headers"], order_id).json()["fulfilment"]["shipment_id"]

    assert set_status(client, ops, original, "CANCELLED").status_code == 200
    replacement = create_shipment(client, ops, order_id, shop["warehouse"], shop["route"])
    assert replacement.status_code == 200, replacement.text
    replacement_id = replacement.json()["shipment_id"]

    assert count(db, Shipment, Shipment.order_id == order_id) == 2
    assert active_shipments(db, order_id) == 1

    # Reviving the cancelled shipment would create a second active one.
    assert set_status(client, ops, original, "CREATED").status_code == 409
    revived = client.post(
        "/tracking", json={"shipment_id": original, "status": "IN_TRANSIT"}, headers=ops,
    )
    assert revived.status_code == 409
    db.expire_all()
    assert db.get(Shipment, original).shipment_status == "CANCELLED"
    assert db.get(Shipment, replacement_id).shipment_status == "CREATED"

    # Repeated payment reports the active replacement, not the cancelled original.
    repeat = pay(client, shop["headers"], order_id).json()
    assert repeat["fulfilment"]["shipment_id"] == replacement_id


def test_payment_replaces_only_cancelled_shipments(client, db, shop, ops):
    order_id = checkout(client, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]
    manual = create_shipment(client, ops, order_id, shop["warehouse"], shop["route"]).json()["shipment_id"]
    assert set_status(client, ops, manual, "CANCELLED").status_code == 200

    body = pay(client, shop["headers"], order_id).json()
    assert body["fulfilment"]["status"] == "DRIVER_ASSIGNED"
    assert body["fulfilment"]["shipment_id"] != manual
    assert active_shipments(db, order_id) == 1


def test_payment_respects_existing_active_shipment(client, db, shop, ops):
    order_id = checkout(client, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]
    manual = create_shipment(client, ops, order_id, shop["warehouse"], shop["route"]).json()["shipment_id"]

    body = pay(client, shop["headers"], order_id).json()
    assert body["payment_status"] == "SUCCESS"
    assert body["fulfilment"]["shipment_id"] == manual
    assert count(db, Shipment, Shipment.order_id == order_id) == 1


def test_concurrent_shipment_creation_allows_one(db, shop, ops):
    with TestClient(app) as c:
        order_id = checkout(c, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]

    def attempt():
        with TestClient(app) as c:
            return create_shipment(c, ops, order_id, shop["warehouse"], shop["route"])

    responses = run_concurrently(8, attempt)
    codes = sorted(r.status_code for r in responses)
    assert codes == [200] + [409] * 7, codes
    assert count(db, Shipment, Shipment.order_id == order_id) == 1


@pytest.mark.parametrize("attempt_round", range(5))
def test_concurrent_payment_and_manual_creation_leave_one_active(db, shop, ops, attempt_round):
    # Regression: POST /shipments used to deadlock with payment fulfilment.
    with TestClient(app) as c:
        order_id = checkout(c, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]

    def attempt(i):
        with TestClient(app) as c:
            if i % 2:
                return pay(c, shop["headers"], order_id)
            return create_shipment(c, ops, order_id, shop["warehouse"], shop["route"])

    counter = iter(range(10))
    lock = threading.Lock()

    def worker():
        with lock:
            i = next(counter)
        return attempt(i)

    responses = run_concurrently(10, worker)
    assert all(getattr(r, "status_code", None) in (200, 409) for r in responses), responses
    assert active_shipments(db, order_id) == 1
    # Whatever won, a successful payment never leaves partial fulfilment behind.
    db.expire_all()
    payment = db.query(Payment).filter_by(order_id=order_id).first()
    if payment:
        assert payment.payment_status == "SUCCESS"
        assert db.query(Invoice.invoice_status).filter_by(order_id=order_id).scalar() == "PAID"


# --- Route selection --------------------------------------------------------

@pytest.fixture
def routes(make):
    """Vellore routes; Bangalore has the lower route_id so street-name matches would win."""
    return {
        "bangalore": make.route("Vellore", "Bangalore"),
        "chennai": make.route("Vellore", "Chennai"),
        "hosur": make.route("Vellore", "Hosur", status="INACTIVE"),
    }


@pytest.mark.parametrize("address, expected", [
    ("12 Bangalore Road, Chennai", "chennai"),       # street name must not match
    ("Flat 3, CHENNAI", "chennai"),
    ("VIT University Chennai", "chennai"),
    ("Chennai, Tamil Nadu", "chennai"),
    ("Anna Nagar, Chennai - 600040", "chennai"),
    ("Chennai 600040", "chennai"),
    ("7 Lake View,\nBangalore.", "bangalore"),
    ("Chennai Road, Bangalore", "bangalore"),
])
def test_route_valid_matches(db, routes, address, expected):
    route = main.select_route(db, "Vellore", address)
    assert route is not None and route.route_id == routes[expected].route_id


@pytest.mark.parametrize("address", [
    "5 Gandhi St, Coimbatore",            # unmatched destination
    "9 Main Rd, Vellore",                 # same city as origin
    "VIT UNIVERSITY VELLORE",
    "Hosur Industrial Estate, Hosur",     # only an INACTIVE route goes there
    "12 Bangalore Road",                  # street name only
    "Bangaloreans Colony, Madurai",       # partial word
    "Chennai, Bangalore",                 # two destinations: ambiguous
    "Unknown",
])
def test_route_unavailable_without_unambiguous_match(db, routes, address):
    assert main.select_route(db, "Vellore", address) is None


def test_duplicate_active_routes_are_ambiguous(db, make, routes):
    make.route("Vellore", "Chennai")
    assert main.select_route(db, "Vellore", "Flat 3, Chennai") is None


@pytest.mark.parametrize("address", [
    "5 Gandhi St, Coimbatore",
    "9 Main Rd, Vellore",
    "12 Bangalore Road",
    "Hosur Industrial Estate, Hosur",
])
def test_unmatched_route_leaves_paid_order_pending_for_operations(client, db, make, address):
    customer, headers = make.customer()
    warehouse = make.warehouse("Vellore")
    product = make.product()
    make.stock(warehouse, product, 5)
    make.route("Vellore", "Bangalore")
    make.route("Vellore", "Chennai")
    make.route("Vellore", "Hosur", status="INACTIVE")
    make.driver()

    order_id = checkout(client, headers, [(product, 2)], address=address).json()["order"]["order_id"]
    body = pay(client, headers, order_id).json()

    assert body["fulfilment"]["status"] == "ROUTE_UNAVAILABLE"
    assert body["payment_status"] == "SUCCESS"
    assert body["invoice_status"] == "PAID"
    assert body["order_status"] == "CONFIRMED"
    assert count(db, Shipment) == 0
    assert count(db, Delivery) == 0
    # The reservation and stock deduction from checkout are kept, not reversed.
    assert count(db, OrderInventoryReservation, OrderInventoryReservation.order_id == order_id) == 1
    assert stock_of(db, warehouse, product) == 3


def test_operations_resolve_route_unavailable(client, db, make, ops):
    customer, headers = make.customer()
    warehouse = make.warehouse("Vellore")
    product = make.product()
    make.stock(warehouse, product, 5)
    chennai = make.route("Vellore", "Chennai")
    driver, _, _ = make.driver()

    order_id = checkout(client, headers, [(product, 1)], address="5 Gandhi St, Coimbatore").json()["order"]["order_id"]
    assert pay(client, headers, order_id).json()["fulfilment"]["status"] == "ROUTE_UNAVAILABLE"

    created = create_shipment(client, ops, order_id, warehouse, chennai)
    assert created.status_code == 200
    shipment_id = created.json()["shipment_id"]
    assigned = client.post(f"/shipments/{shipment_id}/assign-driver", headers=ops)
    assert assigned.status_code == 200
    assert assigned.json()["driver_id"] == driver.employee_id
    assert assigned.json()["order_status"] == "PROCESSING"

    repeat = pay(client, headers, order_id).json()
    assert repeat["fulfilment"]["shipment_id"] == shipment_id
    assert repeat["fulfilment"]["status"] == "DRIVER_ASSIGNED"
    db.expire_all()
    assert db.query(Order.order_status).filter_by(order_id=order_id).scalar() == "PROCESSING"
    assert db.query(Inventory.quantity).filter_by(product_id=product.product_id).scalar() == 4
