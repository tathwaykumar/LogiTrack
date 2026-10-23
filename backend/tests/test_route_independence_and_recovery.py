"""Routes are optional reference data, never a prerequisite; paid orders that predate reservations can be recovered."""
import pytest
from fastapi.testclient import TestClient
import threading

from sqlalchemy import func, text

from database import engine
from main import app
from models import (
    Delivery, Inventory, Order, OrderFulfilment, OrderFulfilmentEvent, OrderInventoryReservation, OrderItem, Payment, Shipment,
)
from test_fulfilment import approve, count, ops_headers, pay_only, run_concurrently
from test_fulfilment_workflow import checkout_to, event_types, order_id_of, plan_of, stock, tracking, world  # noqa: F401


# --- Route-independent fulfilment ------------------------------------------------------------------

def test_paid_order_goes_all_the_way_to_delivery_with_no_route_configured(client, db, world):  # noqa: F811
    destination = "Tiny Village, Idukki 685601"      # nothing like it is configured anywhere
    order_id = order_id_of(client.post("/shop/checkout", headers=world["headers"], json={
        "items": [{"product_id": world["product"].product_id, "quantity": 2}], "shipping_address": destination}))
    assert pay_only(client, world["headers"], order_id).json()["fulfilment"]["status"] == "AWAITING_APPROVAL"
    assert count(db, Shipment) == 0

    body = approve(client, order_id, world["ops"]).json()
    assert body["status"] == "DRIVER_ASSIGNED" and body["route_id"] is None
    db.expire_all()
    shipment = db.query(Shipment).one()
    assert shipment.route_id is None and shipment.estimated_delivery is None     # no route, no invented ETA
    assert db.query(Delivery).one().vehicle_id == world["vehicle"].vehicle_id

    for status in ("PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"):
        assert tracking(client, world["driver_headers"], shipment.shipment_id, status).status_code == 200, status
    db.expire_all()
    assert db.get(Order, order_id).order_status == "DELIVERED"

    # Every view copes with a shipment that has no route.
    desk = client.get("/operations/shipments", headers=world["ops"]).json()
    assert [r["shipment_id"] for r in desk["items"]] == [shipment.shipment_id] and desk["items"][0]["route_name"] is None
    assert client.get("/operations/shipments?q=Tiny", headers=world["ops"]).status_code == 200
    details = client.get("/shipment-details", headers=world["ops"]).json()
    assert [d["shipment_id"] for d in details] == [shipment.shipment_id] and details[0]["route_name"] is None
    assert client.get(f"/shipments/{shipment.shipment_id}/tracking-details", headers=world["ops"]).status_code == 200
    mine = client.get(f"/orders/{order_id}/tracking", headers=world["headers"]).json()
    assert mine["stage"]["label"] == "Delivered" and mine["route"] is None
    assert "route" not in mine["explanation"].lower() if mine["explanation"] else True
    wh = {w["warehouse_id"]: w for w in client.get("/operations/warehouses", headers=world["ops"]).json()}[world["warehouse"].warehouse_id]
    assert wh["data_gaps"] == [] or all("route" not in gap.lower() for gap in wh["data_gaps"])
    assert wh["outgoing_shipments"]["delivered"] == 1


def test_a_route_is_recorded_only_when_exactly_one_real_route_matches(client, db, world):  # noqa: F811
    matched = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    pay_only(client, world["headers"], matched)
    approve(client, matched, world["ops"])
    db.expire_all()
    first = db.query(Shipment).one()
    assert first.route_id == world["route"].route_id and first.estimated_delivery is not None

    world["make"].route("Vellore", "Chennai")        # a second active route makes the match ambiguous
    ambiguous = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    pay_only(client, world["headers"], ambiguous)
    assert approve(client, ambiguous, world["ops"]).status_code == 200
    db.expire_all()
    second = db.query(Shipment).filter(Shipment.order_id == ambiguous).one()
    assert second.route_id is None and second.estimated_delivery is None


def test_retry_after_a_driver_appears_needs_no_route(client, db, make):
    customer, headers = make.customer()
    wh = make.warehouse("Madurai")
    product = make.product(weight=1)
    make.stock(wh, product, 5)
    ops = ops_headers()
    order_id = order_id_of(checkout_to(client, headers, [(product, 1)], "Anywhere"))
    pay_only(client, headers, order_id)
    waiting = approve(client, order_id, ops).json()
    assert waiting["status"] == "PENDING_ASSIGNMENT" and count(db, Delivery) == 0

    driver, vehicle, _ = make.driver()
    retried = client.post(f"/operations/orders/{order_id}/retry-fulfilment", headers=ops)
    assert retried.status_code == 200 and retried.json()["status"] == "DRIVER_ASSIGNED"
    assert count(db, Shipment) == 1 and count(db, Delivery) == 1
    db.expire_all()
    assert db.query(Shipment).one().route_id is None


def test_unpaid_and_failed_payment_orders_cannot_be_approved_or_shipped(client, db, world):  # noqa: F811
    unpaid = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    failed = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    assert pay_only(client, world["headers"], failed, "FAILED").status_code == 200
    for order_id in (unpaid, failed):
        refused = approve(client, order_id, world["ops"])
        assert refused.status_code == 409 and "not been paid" in refused.json()["detail"]
        assert client.post(f"/operations/orders/{order_id}/retry-fulfilment", headers=world["ops"]).status_code in (200, 409)
    assert count(db, Shipment) == 0 and count(db, Delivery) == 0
    db.expire_all()
    assert all(plan_of(db, o).approved_at is None for o in (unpaid, failed))


def test_customer_never_sees_allocation_or_route_exceptions(client, db, make):
    customer, headers = make.customer()
    wh = make.warehouse("Madurai")
    product = make.product(weight=1)
    make.stock(wh, product, 5)                                    # no route, no driver, no vehicle anywhere
    order_id = order_id_of(checkout_to(client, headers, [(product, 1)], "Anywhere"))
    pay_only(client, headers, order_id)
    approve(client, order_id, ops_headers())
    text = str(client.get(f"/orders/{order_id}/tracking", headers=headers).json()).lower()
    text += str(client.get("/orders", headers=headers).json()).lower()
    for phrase in ("no driver", "no vehicle", "eligible", "no route", "blocked", "not configured", "reservation"):
        assert phrase not in text, phrase


# --- Recovering stock for a paid order that predates reservations ----------------------------------

@pytest.fixture
def legacy(client, db, make):
    """A paid order shaped like order 13: items and a successful payment, but no reservation."""
    customer, headers = make.customer()
    wh = make.warehouse("Vellore")
    a, b = make.product(price=3000, weight=1), make.product(price=2800, weight=1)
    make.stock(wh, a, 5)
    make.stock(wh, b, 1)
    order = make.legacy_order(customer, a, quantity=2)
    make._save(OrderItem(order_id=order.order_id, product_id=b.product_id, quantity=1, unit_price=b.unit_price))
    assert pay_only(client, headers, order.order_id).status_code == 200
    return {"order": order, "wh": wh, "a": a, "b": b, "customer": customer, "headers": headers,
            "ops": ops_headers(), "make": make}


def recover(client, headers, order_id, confirm=True):
    return client.post(f"/operations/orders/{order_id}/recover-reservation", headers=headers,
                       json={"confirm_stock_not_deducted": confirm})


def test_recovery_reserves_exactly_the_order_items_and_does_not_approve(client, db, legacy):
    order_id = legacy["order"].order_id
    flagged = client.get("/operations/orders?stage=attention", headers=legacy["ops"]).json()["items"][0]
    assert flagged["order_id"] == order_id and flagged["exception"]["code"] == "RESERVATION_MISSING"

    outcome = recover(client, legacy["ops"], order_id)
    assert outcome.status_code == 200 and outcome.json()["status"] == "RESERVED" and outcome.json()["approved"] is False
    db.expire_all()
    rows = db.query(OrderInventoryReservation).filter_by(order_id=order_id).all()
    assert sorted((r.product_id, r.reserved_quantity, r.warehouse_id) for r in rows) == sorted([
        (legacy["a"].product_id, 2, legacy["wh"].warehouse_id), (legacy["b"].product_id, 1, legacy["wh"].warehouse_id)])
    assert stock(db, legacy["wh"], legacy["a"]) == 3 and stock(db, legacy["wh"], legacy["b"]) == 0

    # Nothing else was claimed: status, payment, approval, shipment and tracking are untouched.
    assert db.get(Order, order_id).order_status == "CONFIRMED"
    assert db.get(OrderFulfilment, order_id).approved_at is None
    assert count(db, Shipment) == 0 and count(db, Delivery) == 0
    assert db.query(Payment).filter_by(order_id=order_id).one().payment_status == "SUCCESS"
    assert "STOCK_RECOVERED" in event_types(db, order_id) and "APPROVED" not in event_types(db, order_id)
    assert client.get("/operations/orders?stage=awaiting_approval", headers=legacy["ops"]).json()["items"][0]["approved"] is False

    # Only an explicit approval ships it.
    assert approve(client, order_id, legacy["ops"]).status_code == 200
    assert count(db, Shipment) == 1


def test_recovery_is_refused_until_staff_confirm_and_changes_nothing(client, db, legacy):
    order_id = legacy["order"].order_id
    refused = recover(client, legacy["ops"], order_id, confirm=False)
    assert refused.status_code == 409 and "Confirm" in refused.json()["detail"]
    db.expire_all()
    assert count(db, OrderInventoryReservation) == 0 and stock(db, legacy["wh"], legacy["a"]) == 5


def test_recovery_with_insufficient_stock_reserves_nothing_and_stays_visible(client, db, legacy):
    order_id = legacy["order"].order_id
    with engine.begin() as conn:
        conn.execute(text("UPDATE inventory SET quantity = 0 WHERE product_id = :p"), {"p": legacy["b"].product_id})
    refused = recover(client, legacy["ops"], order_id)
    assert refused.status_code == 409 and "Insufficient stock" in refused.json()["detail"]
    db.expire_all()
    assert count(db, OrderInventoryReservation) == 0
    assert stock(db, legacy["wh"], legacy["a"]) == 5          # the first item's stock was not half-taken
    assert db.get(Order, order_id).order_status == "CONFIRMED" and count(db, Shipment) == 0
    # The exception stays on the staff desk, and approval is still refused.
    item = client.get("/operations/orders?stage=attention", headers=legacy["ops"]).json()["items"][0]
    assert item["order_id"] == order_id and item["exception"]["code"] == "RESERVATION_MISSING"
    assert approve(client, order_id, legacy["ops"]).status_code == 409


def test_recovery_requires_a_genuine_successful_payment(client, db, make):
    customer, headers = make.customer()
    wh = make.warehouse("Vellore")
    product = make.product(weight=1)
    make.stock(wh, product, 5)
    ops = ops_headers()
    unpaid = make.legacy_order(customer, product)
    failed = make.legacy_order(customer, product)
    assert pay_only(client, headers, failed.order_id, "FAILED").status_code == 200
    for order_id in (unpaid.order_id, failed.order_id):
        refused = recover(client, ops, order_id)
        assert refused.status_code == 409 and "no successful payment" in refused.json()["detail"]
    assert recover(client, ops, 99999).status_code == 404
    assert recover(client, headers, unpaid.order_id).status_code == 403
    assert count(db, OrderInventoryReservation) == 0 and stock(db, wh, product) == 5


def test_recovery_is_idempotent_and_never_reserves_twice(client, db, legacy):
    order_id = legacy["order"].order_id
    assert recover(client, legacy["ops"], order_id).json()["status"] == "RESERVED"
    again = recover(client, legacy["ops"], order_id)
    assert again.status_code == 200 and again.json()["status"] == "ALREADY_RESERVED" and again.json()["recovered"] is False
    db.expire_all()
    assert count(db, OrderInventoryReservation, OrderInventoryReservation.order_id == order_id) == 2
    assert stock(db, legacy["wh"], legacy["a"]) == 3
    assert event_types(db, order_id).count("STOCK_RECOVERED") == 1


def test_concurrent_recovery_of_one_order_reserves_once(db, legacy):
    order_id, ops = legacy["order"].order_id, legacy["ops"]

    def attempt():
        with TestClient(app) as c:
            return recover(c, ops, order_id)

    results = run_concurrently(4, attempt)
    assert all(not isinstance(r, Exception) and r.status_code == 200 for r in results), results
    assert sorted(r.json()["status"] for r in results) == ["ALREADY_RESERVED"] * 3 + ["RESERVED"]
    db.expire_all()
    assert count(db, OrderInventoryReservation, OrderInventoryReservation.order_id == order_id) == 2
    assert stock(db, legacy["wh"], legacy["a"]) == 3 and stock(db, legacy["wh"], legacy["b"]) == 0


def test_two_orders_cannot_both_recover_the_last_unit(db, client, make):
    customer, headers = make.customer()
    wh = make.warehouse("Vellore")
    product = make.product(weight=1)
    make.stock(wh, product, 1)
    ops = ops_headers()
    orders = [make.legacy_order(customer, product) for _ in range(2)]
    for order in orders:
        assert pay_only(client, headers, order.order_id).status_code == 200

    def attempt(order_id):
        def run():
            with TestClient(app) as c:
                return recover(c, ops, order_id)
        return run

    out = [None, None]
    barrier = threading.Barrier(2)

    def worker(i):
        barrier.wait()
        out[i] = attempt(orders[i].order_id)()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sorted(r.status_code for r in out) == [200, 409], [r.text for r in out]
    db.expire_all()
    assert stock(db, wh, product) == 0 and count(db, OrderInventoryReservation) == 1
    assert db.query(func.coalesce(func.sum(Inventory.quantity), 0)).scalar() == 0     # never negative (CHECK also enforces it)


def test_shipments_that_predate_approvals_make_no_approval_claim(client, db, make):
    """An older shipment has no recorded approval: staff see 'not recorded', customers see no approval step."""
    from datetime import datetime
    customer, headers = make.customer()
    wh = make.warehouse("Vellore")
    product = make.product()
    order = make.legacy_order(customer, product)
    make._save(Payment(order_id=order.order_id, amount=100, payment_method="SIMULATED_TEST_MODE",
                       payment_status="SUCCESS", payment_date=datetime.now()))
    shipment = make._save(Shipment(order_id=order.order_id, warehouse_id=wh.warehouse_id, shipment_status="CREATED"))
    ops = ops_headers()

    staff = {m["key"]: m for m in client.get(f"/orders/{order.order_id}/tracking", headers=ops).json()["milestones"]}
    assert staff["ORDER_APPROVED"]["state"] == "not_recorded" and staff["ORDER_APPROVED"]["at"] is None
    mine = client.get(f"/orders/{order.order_id}/tracking", headers=headers).json()
    assert "ORDER_APPROVED" not in {m["key"] for m in mine["milestones"]}
    db.expire_all()
    assert db.query(OrderFulfilment).count() == 0 and shipment.shipment_id         # viewing wrote nothing


def test_manual_shipment_creation_cannot_bypass_payment(client, db, world):  # noqa: F811
    """POST /shipments follows the same rule as approval: paid and uncancelled orders only."""
    body = lambda order_id: {"order_id": order_id, "warehouse_id": world["warehouse"].warehouse_id, "route_id": world["route"].route_id}
    unpaid = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    refused = client.post("/shipments", json=body(unpaid), headers=world["ops"])
    assert refused.status_code == 409 and "Payment has not succeeded" in refused.json()["detail"]

    pay_only(client, world["headers"], unpaid)
    created = client.post("/shipments", json=body(unpaid), headers=world["ops"])
    assert created.status_code == 200
    db.expire_all()
    plan = plan_of(db, unpaid)
    assert plan.approved_at is not None and plan.approved_by_user_id is not None     # a real act, recorded
    assert event_types(db, unpaid).count("APPROVED") == 1

    cancelled = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    pay_only(client, world["headers"], cancelled)
    with engine.begin() as conn:
        conn.execute(text("UPDATE orders SET order_status = 'CANCELLED' WHERE order_id = :o"), {"o": cancelled})
    assert client.post("/shipments", json=body(cancelled), headers=world["ops"]).status_code == 409
    assert count(db, Shipment) == 1


def _manual(client, world, order_id, **extra):
    payload = {"order_id": order_id, "warehouse_id": world["warehouse"].warehouse_id, **extra}
    return client.post("/shipments", json=payload, headers=world["ops"])


def test_manual_shipment_needs_no_route(client, db, world):  # noqa: F811
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    pay_only(client, world["headers"], order_id)
    created = _manual(client, world, order_id)                      # route_id omitted
    assert created.status_code == 200, created.text
    assert created.json()["route_id"] is None
    db.expire_all()
    shipment = db.query(Shipment).one()
    assert shipment.route_id is None and shipment.estimated_delivery is None and shipment.shipment_status == "CREATED"
    # An explicit route is still accepted, and a nonexistent one is still rejected.
    other = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    pay_only(client, world["headers"], other)
    assert _manual(client, world, other, route_id=world["route"].route_id).json()["route_id"] == world["route"].route_id
    third = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    pay_only(client, world["headers"], third)
    assert _manual(client, world, third, route_id=999999).status_code == 422


def test_manual_shipment_rejects_unpaid_failed_and_cancelled_orders(client, db, world):  # noqa: F811
    unpaid = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    failed = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    pay_only(client, world["headers"], failed, "FAILED")
    cancelled = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    pay_only(client, world["headers"], cancelled)
    with engine.begin() as conn:
        conn.execute(text("UPDATE orders SET order_status = 'CANCELLED' WHERE order_id = :o"), {"o": cancelled})

    for order_id, reason in ((unpaid, "Payment has not succeeded"), (failed, "Payment has not succeeded"), (cancelled, "cancelled")):
        refused = _manual(client, world, order_id)
        assert refused.status_code == 409 and reason in refused.json()["detail"], (order_id, refused.text)
    db.expire_all()
    assert count(db, Shipment) == 0
    assert all(plan_of(db, o).approved_at is None for o in (unpaid, failed, cancelled))      # no approval recorded
    assert count(db, OrderFulfilmentEvent, OrderFulfilmentEvent.event_type == "APPROVED") == 0


def test_manual_creation_records_one_approval_and_never_a_duplicate(client, db, world):  # noqa: F811
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    pay_only(client, world["headers"], order_id)

    # An invalid request (unknown warehouse) records no approval at all.
    bad = client.post("/shipments", json={"order_id": order_id, "warehouse_id": 999999}, headers=world["ops"])
    assert bad.status_code == 422
    db.expire_all()
    assert plan_of(db, order_id).approved_at is None and "APPROVED" not in event_types(db, order_id)

    first = _manual(client, world, order_id)
    assert first.status_code == 200
    db.expire_all()
    approved_at = plan_of(db, order_id).approved_at
    assert approved_at is not None and event_types(db, order_id).count("APPROVED") == 1

    # A second shipment is refused, the approval is untouched, and approving the order again is harmless.
    assert _manual(client, world, order_id).status_code == 409
    assert approve(client, order_id, world["ops"]).status_code == 200
    # Replacing a cancelled shipment does not record a second approval either.
    with engine.begin() as conn:
        conn.execute(text("UPDATE shipment SET shipment_status = 'CANCELLED' WHERE shipment_id = :s"), {"s": first.json()["shipment_id"]})
    assert _manual(client, world, order_id).status_code == 200
    db.expire_all()
    assert plan_of(db, order_id).approved_at == approved_at
    assert event_types(db, order_id).count("APPROVED") == 1
    assert count(db, OrderFulfilmentEvent, OrderFulfilmentEvent.event_type == "APPROVED") == 1


def test_manual_creation_after_the_manager_approved_keeps_the_original_approval(client, db, world):  # noqa: F811
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    pay_only(client, world["headers"], order_id)
    approve(client, order_id, world["ops"])
    db.expire_all()
    original = (plan_of(db, order_id).approved_at, plan_of(db, order_id).approved_by_user_id)
    with engine.begin() as conn:
        conn.execute(text("UPDATE shipment SET shipment_status = 'CANCELLED'"))
    assert _manual(client, world, order_id).status_code == 200
    db.expire_all()
    assert (plan_of(db, order_id).approved_at, plan_of(db, order_id).approved_by_user_id) == original
    assert event_types(db, order_id).count("APPROVED") == 1
