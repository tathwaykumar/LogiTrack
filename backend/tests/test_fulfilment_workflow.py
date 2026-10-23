"""Order creation -> planning -> payment -> dispatch -> delivery, cancellation, and the operations desk."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, text

import fulfilment
from database import engine
from main import app
from models import (
    Delivery, Employee, Inventory, Invoice, Order, OrderFulfilment, OrderFulfilmentEvent,
    OrderInventoryReservation, Payment, Shipment, User,
)
from test_fulfilment import count, pay, run_concurrently


def checkout_to(client, headers, items, city, address="5 Market Road"):
    return client.post(
        "/shop/checkout",
        json={
            "items": [{"product_id": p.product_id, "quantity": q} for p, q in items],
            "shipping_address": address,
            "destination_city": city,
        },
        headers=headers,
    )


def order_id_of(response):
    assert response.status_code == 201, response.text
    return response.json()["order"]["order_id"]


def plan_of(db, order_id):
    db.expire_all()
    return db.get(OrderFulfilment, order_id)


def event_types(db, order_id):
    db.expire_all()
    return [e.event_type for e in db.query(OrderFulfilmentEvent).filter_by(order_id=order_id).order_by(OrderFulfilmentEvent.event_id)]


def stock(db, warehouse, product):
    db.expire_all()
    return db.query(Inventory.quantity).filter_by(warehouse_id=warehouse.warehouse_id, product_id=product.product_id).scalar()


def tracking(client, headers, shipment_id, status):
    return client.post("/tracking", json={"shipment_id": shipment_id, "status": status}, headers=headers)


@pytest.fixture
def world(make):
    """A customer, a Vellore warehouse with stock, a Vellore->Chennai route and one eligible driver."""
    customer, customer_headers = make.customer()
    warehouse = make.warehouse("Vellore", capacity=1000)
    product = make.product(price=250, weight=2)
    make.stock(warehouse, product, 20)
    route = make.route("Vellore", "Chennai")
    driver, vehicle, driver_headers = make.driver()
    _, ops = make.user("OPERATIONS_MANAGER")
    _, admin = make.user("ADMIN")
    return {
        "make": make, "customer": customer, "headers": customer_headers, "warehouse": warehouse, "product": product,
        "route": route, "driver": driver, "vehicle": vehicle, "driver_headers": driver_headers, "ops": ops, "admin": admin,
    }


# --- Order creation plans fulfilment ---------------------------------------------------------

def test_order_creation_plans_fulfilment_but_does_not_dispatch(client, db, world):
    response = checkout_to(client, world["headers"], [(world["product"], 3)], "Chennai", "Plot 9, Anna Nagar")
    order_id = order_id_of(response)
    body = response.json()

    # The customer sees a stage, never internal planning details.
    assert body["fulfilment"]["stage"] == "Awaiting payment"
    assert set(body["fulfilment"]) == {"stage", "dispatch"}
    assert body["order"]["destination_city"] == "Chennai"

    plan = plan_of(db, order_id)
    assert (plan.fulfilment_status, plan.route_basis) == ("PLANNED", "DESTINATION_CITY")
    assert world["warehouse"].warehouse_name in plan.selection_note
    assert event_types(db, order_id) == ["PLANNED"]
    # Unpaid: no shipment, no driver, stock is reserved.
    assert count(db, Shipment) == 0 and count(db, Delivery) == 0
    assert stock(db, world["warehouse"], world["product"]) == 17
    assert db.get(Order, order_id).order_status == "PENDING"


def test_destination_city_is_used_instead_of_searching_the_address(client, db, world):
    world["make"].route("Vellore", "Bangalore")  # lower route id; the street name must not win
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai", "12 Bangalore Road"))
    plan = plan_of(db, order_id)
    assert plan.route_id == world["route"].route_id and plan.route_basis == "DESTINATION_CITY"
    assert plan.origin_warehouse_id == world["warehouse"].warehouse_id

    # Older clients send no city: the address is read as before, and the plan says so.
    legacy = client.post("/shop/checkout", json={"items": [{"product_id": world["product"].product_id, "quantity": 1}],
                                                  "shipping_address": "7 Lake View, Chennai"}, headers=world["headers"])
    assert plan_of(db, order_id_of(legacy)).route_basis == "ADDRESS_TEXT"


def test_checkout_needs_no_route_or_service_area(client, db, world):
    """The customer gives a delivery address; no route has to exist for it, and no city list is offered."""
    assert client.get("/shop/service-areas", headers=world["headers"]).status_code == 404
    response = client.post("/shop/checkout", headers=world["headers"], json={
        "items": [{"product_id": world["product"].product_id, "quantity": 1}],
        "shipping_address": "Flat 4, 12 Lake View Road, Madurai 625001"})
    order_id = order_id_of(response)
    assert plan_of(db, order_id).fulfilment_status == "PLANNED" and plan_of(db, order_id).route_id is None


def test_unserved_destination_does_not_block_a_paid_order(client, db, world):
    """No route to Coimbatore exists. The order is still planned, and ships once it is paid AND approved."""
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 2)], "Coimbatore"))
    plan = plan_of(db, order_id)
    assert plan.fulfilment_status == "PLANNED" and plan.route_id is None and plan.reason_code is None
    assert stock(db, world["warehouse"], world["product"]) == 18

    # Unpaid: cannot be approved, nothing ships.
    assert client.post(f"/operations/orders/{order_id}/approve", headers=world["ops"]).status_code == 409
    assert count(db, Shipment) == 0

    paid = pay(client, world["headers"], order_id).json()
    assert paid["fulfilment"]["status"] == "DRIVER_ASSIGNED"
    shipment = db.query(Shipment).one()
    assert shipment.route_id is None and shipment.estimated_delivery is None
    assert count(db, Delivery) == 1
    # Repeating approval or the retry endpoint creates nothing more.
    assert client.post(f"/operations/orders/{order_id}/approve", headers=world["ops"]).status_code == 200
    assert client.post(f"/operations/orders/{order_id}/retry-fulfilment", headers=world["ops"]).status_code == 200
    assert count(db, Shipment) == 1 and count(db, Delivery) == 1
    assert event_types(db, order_id).count("SHIPMENT_CREATED") == 1


# --- Payment completes fulfilment -------------------------------------------------------------

def test_successful_payment_dispatches_with_a_persisted_vehicle(client, db, world):
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    body = pay(client, world["headers"], order_id).json()
    assert body["fulfilment"]["status"] == "DRIVER_ASSIGNED" and body["order_status"] == "CONFIRMED"
    db.expire_all()
    assert db.get(Order, order_id).order_status == "PROCESSING"
    assert body["fulfilment"]["vehicle_id"] == world["vehicle"].vehicle_id

    delivery = db.query(Delivery).one()
    assert (delivery.driver_id, delivery.vehicle_id) == (world["driver"].employee_id, world["vehicle"].vehicle_id)
    assert delivery.assigned_at is not None
    assert plan_of(db, order_id).fulfilment_status == "ASSIGNED"
    assert event_types(db, order_id) == ["PLANNED", "PAID", "APPROVED", "SHIPMENT_CREATED", "DRIVER_ASSIGNED", "ASSIGNED"]

    again = pay(client, world["headers"], order_id).json()  # repeated request
    assert again["already_processed"] is True and again["fulfilment"]["vehicle_id"] == world["vehicle"].vehicle_id
    assert count(db, Shipment) == 1 and count(db, Delivery) == 1


def test_failed_payment_never_dispatches(client, db, world):
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    failed = pay(client, world["headers"], order_id, "FAILED").json()
    assert failed["fulfilment"] is None and failed["order_status"] == "PENDING"
    assert count(db, Shipment) == 0 and count(db, Delivery) == 0
    assert plan_of(db, order_id).fulfilment_status == "PLANNED"
    # The ops retry on an unpaid order only re-plans.
    retry = client.post(f"/operations/orders/{order_id}/retry-fulfilment", headers=world["ops"]).json()
    assert retry["status"] == "PLANNED" and count(db, Shipment) == 0


# --- Cancellation and stock release ----------------------------------------------------------------

def test_cancel_releases_stock_exactly_once(client, db, world):
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 4)], "Chennai"))
    assert stock(db, world["warehouse"], world["product"]) == 16

    cancelled = client.post(f"/orders/{order_id}/cancel", headers=world["headers"])
    assert cancelled.status_code == 200 and cancelled.json()["units_released"] == 4
    assert stock(db, world["warehouse"], world["product"]) == 20
    db.expire_all()
    assert db.get(Order, order_id).order_status == "CANCELLED"
    assert db.query(Invoice.invoice_status).filter_by(order_id=order_id).scalar() == "CANCELLED"
    assert plan_of(db, order_id).fulfilment_status == "CANCELLED"
    assert all(r.released_at is not None for r in db.query(OrderInventoryReservation).filter_by(order_id=order_id))

    again = client.post(f"/orders/{order_id}/cancel", headers=world["headers"]).json()
    assert again["already_cancelled"] is True and again["units_released"] == 0
    assert stock(db, world["warehouse"], world["product"]) == 20
    assert event_types(db, order_id).count("CANCELLED") == 1

    # A cancelled order cannot be paid.
    assert pay(client, world["headers"], order_id).status_code == 409
    assert count(db, Shipment) == 0


def test_the_release_routine_itself_is_exactly_once(client, db, world):
    """Independent of the order-status guard: the released_at marker stops a second release."""
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 4)], "Chennai"))
    from database import SessionLocal
    session = SessionLocal()
    try:
        first = fulfilment.release_order_stock(session, order_id)
        session.commit()
        second = fulfilment.release_order_stock(session, order_id)
        session.commit()
    finally:
        session.close()
    assert (first, second) == (4, 0)
    assert stock(db, world["warehouse"], world["product"]) == 20


def test_concurrent_cancellations_release_stock_once(db, world):
    with TestClient(app) as c:
        order_id = order_id_of(checkout_to(c, world["headers"], [(world["product"], 4)], "Chennai"))

    def attempt():
        with TestClient(app) as c:
            return c.post(f"/orders/{order_id}/cancel", headers=world["headers"])

    responses = run_concurrently(8, attempt)
    assert all(getattr(r, "status_code", None) == 200 for r in responses), responses
    assert sum(r.json()["units_released"] for r in responses) == 4
    assert stock(db, world["warehouse"], world["product"]) == 20


def test_paid_or_dispatched_orders_cannot_be_cancelled(client, db, world):
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 2)], "Chennai"))
    pay(client, world["headers"], order_id)
    refused = client.post(f"/orders/{order_id}/cancel", headers=world["headers"])
    assert refused.status_code == 409 and "paid" in refused.json()["detail"].lower()
    assert client.post(f"/orders/{order_id}/cancel", headers=world["ops"]).status_code == 409
    assert stock(db, world["warehouse"], world["product"]) == 18  # nothing released
    assert db.get(Order, order_id).order_status == "PROCESSING"


def test_only_the_owner_or_staff_can_cancel(client, db, world):
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    _, intruder = world["make"].customer()
    assert client.post(f"/orders/{order_id}/cancel", headers=intruder).status_code == 403
    assert client.post("/orders/99999/cancel", headers=world["headers"]).status_code == 404
    assert client.post(f"/orders/{order_id}/cancel", headers=world["ops"]).status_code == 200


def test_abandoned_unpaid_orders_are_released_once(client, db, world):
    stale = order_id_of(checkout_to(client, world["headers"], [(world["product"], 3)], "Chennai"))
    paid = order_id_of(checkout_to(client, world["headers"], [(world["product"], 2)], "Chennai"))
    pay(client, world["headers"], paid)
    fresh = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    db.rollback()
    with engine.begin() as conn:
        conn.execute(text("UPDATE orders SET order_date = now() - interval '3 hours' WHERE order_id IN (:a, :b)"), {"a": stale, "b": paid})

    result = client.post("/operations/release-abandoned", params={"older_than_minutes": 60}, headers=world["ops"]).json()
    assert result["orders_cancelled"] == 1 and result["units_released"] == 3
    assert [o["order_id"] for o in result["orders"]] == [stale]
    db.expire_all()
    assert db.get(Order, stale).order_status == "CANCELLED"
    assert db.get(Order, paid).order_status == "PROCESSING"   # paid orders are untouched
    assert db.get(Order, fresh).order_status == "PENDING"     # not old enough
    assert stock(db, world["warehouse"], world["product"]) == 20 - 2 - 1

    repeat = client.post("/operations/release-abandoned", params={"older_than_minutes": 60}, headers=world["ops"]).json()
    assert repeat["orders_cancelled"] == 0
    assert client.post("/operations/release-abandoned", headers=world["headers"]).status_code == 403


# --- Warehouse selection -----------------------------------------------------------------------

def test_warehouse_choice_follows_stock_and_status_not_routes(client, db, make):
    customer, headers = make.customer()
    product = make.product(weight=1)
    first = make.warehouse("Madurai")             # lowest id, holds stock, no route leaves Madurai: still eligible
    second = make.warehouse("Vellore")
    inactive = make.warehouse("Salem", status="INACTIVE")
    for wh in (first, second, inactive):
        make.stock(wh, product, 10)
    make.route("Vellore", "Chennai")              # a route exists from the second warehouse only
    make.driver()

    order_id = order_id_of(checkout_to(client, headers, [(product, 4)], "Chennai"))
    plan = plan_of(db, order_id)
    assert plan.origin_warehouse_id == first.warehouse_id and plan.fulfilment_status == "PLANNED"
    assert "route" not in plan.selection_note.lower() and "other warehouse" in plan.selection_note
    assert stock(db, first, product) == 6 and stock(db, second, product) == 10
    assert stock(db, inactive, product) == 10  # an INACTIVE warehouse is never used

    # Only the inactive warehouse could cover 25 units, so the order is refused, not mis-sourced.
    big = make.product()
    make.stock(inactive, big, 50)
    refused = checkout_to(client, headers, [(big, 25)], "Chennai")
    assert refused.status_code == 409 and "Only 0 available" in refused.json()["detail"]


def test_split_orders_are_planned_with_an_honest_note(client, db, make):
    customer, headers = make.customer()
    a, b = make.product(weight=1), make.product(weight=1)
    first, second = make.warehouse("Vellore"), make.warehouse("Chennai")
    make.stock(first, a, 10)
    make.stock(second, a, 4)
    make.stock(second, b, 20)
    make.route("Chennai", "Bangalore")
    make.driver()

    order_id = order_id_of(checkout_to(client, headers, [(a, 12), (b, 15)], "Bangalore"))
    plan = plan_of(db, order_id)
    assert plan.origin_warehouse_id == second.warehouse_id           # supplies 17 of 27 units
    assert "No single active warehouse" in plan.selection_note and "not modelled" in plan.selection_note
    assert db.query(OrderInventoryReservation).filter_by(order_id=order_id).count() == 3


# --- Driver and vehicle rules -----------------------------------------------------------------------

def test_vehicle_capacity_blocks_assignment_with_a_reason(client, db, make):
    customer, headers = make.customer()
    wh = make.warehouse("Vellore")
    heavy = make.product(weight=10)
    make.stock(wh, heavy, 10)
    make.route("Vellore", "Chennai")
    driver, vehicle, _ = make.driver(vehicle_capacity=5)   # shipment weighs 10 kg
    _, ops = make.user("OPERATIONS_MANAGER")

    order_id = order_id_of(checkout_to(client, headers, [(heavy, 1)], "Chennai"))
    assert "capacity" in plan_of(db, order_id).reason_detail
    body = pay(client, headers, order_id).json()
    assert body["fulfilment"]["status"] == "PENDING_ASSIGNMENT" and body["order_status"] == "CONFIRMED"
    plan = plan_of(db, order_id)
    assert plan.fulfilment_status == "AWAITING_ASSIGNMENT" and "free capacity" in plan.reason_detail
    assert count(db, Delivery) == 0 and count(db, Shipment) == 1

    shipment_id = body["fulfilment"]["shipment_id"]
    options = client.get(f"/operations/shipments/{shipment_id}/assignment-options", headers=ops).json()
    assert options["shipment_weight_kg"] == 10.0
    assert options["options"][0]["eligible"] is False and "capacity" in options["options"][0]["reasons"][0]
    refused = client.post(f"/shipments/{shipment_id}/assignment", json={"driver_id": driver.employee_id}, headers=ops)
    assert refused.status_code == 409 and "capacity" in refused.json()["detail"]

    db.rollback()
    with engine.begin() as conn:
        conn.execute(text("UPDATE vehicle SET capacity = 50 WHERE vehicle_id = :v"), {"v": vehicle.vehicle_id})
    assert client.post(f"/operations/orders/{order_id}/retry-fulfilment", headers=ops).json()["status"] == "DRIVER_ASSIGNED"


def test_unknown_product_weight_skips_the_capacity_check_and_says_so(client, db, make):
    customer, headers = make.customer()
    wh = make.warehouse("Vellore")
    unweighed = make.product(weight=None)
    make.stock(wh, unweighed, 5)
    make.route("Vellore", "Chennai")
    make.driver(vehicle_capacity=1)
    _, ops = make.user("OPERATIONS_MANAGER")

    order_id = order_id_of(checkout_to(client, headers, [(unweighed, 1)], "Chennai"))
    body = pay(client, headers, order_id).json()
    assert body["fulfilment"]["status"] == "DRIVER_ASSIGNED"
    options = client.get(f"/operations/shipments/{body['fulfilment']['shipment_id']}/assignment-options", headers=ops).json()
    assert options["shipment_weight_kg"] is None and "no product weight" in options["weight_note"]


def test_driver_open_delivery_limit_and_manual_assignment(client, db, world, monkeypatch):
    monkeypatch.setattr(fulfilment, "MAX_OPEN_DELIVERIES_PER_DRIVER", 1)
    second_driver, second_vehicle, _ = world["make"].driver()
    ops = world["ops"]

    ids = [order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai")) for _ in range(3)]
    results = [pay(client, world["headers"], oid).json()["fulfilment"] for oid in ids]
    assert [r["status"] for r in results] == ["DRIVER_ASSIGNED", "DRIVER_ASSIGNED", "PENDING_ASSIGNMENT"]
    assert {results[0]["driver_id"], results[1]["driver_id"]} == {world["driver"].employee_id, second_driver.employee_id}
    assert "maximum number of open deliveries" in plan_of(db, ids[2]).reason_detail

    # An operator cannot push a third delivery onto a driver who is at the limit.
    refused = client.post(f"/shipments/{results[2]['shipment_id']}/assignment", json={"driver_id": second_driver.employee_id}, headers=ops)
    assert refused.status_code == 409 and "maximum number of open deliveries" in refused.json()["detail"]

    # Raise the limit: manual assignment works, is recorded, and is idempotent.
    monkeypatch.setattr(fulfilment, "MAX_OPEN_DELIVERIES_PER_DRIVER", 2)
    done = client.post(f"/shipments/{results[2]['shipment_id']}/assignment",
                       json={"driver_id": second_driver.employee_id, "vehicle_id": second_vehicle.vehicle_id}, headers=ops)
    assert done.status_code == 200 and done.json()["changed"] is True
    assert client.post(f"/shipments/{results[2]['shipment_id']}/assignment",
                       json={"driver_id": second_driver.employee_id}, headers=ops).json()["changed"] is False
    db.expire_all()
    assert db.query(Delivery).filter_by(shipment_id=results[2]["shipment_id"]).one().vehicle_id == second_vehicle.vehicle_id
    assert plan_of(db, ids[2]).fulfilment_status == "ASSIGNED"
    assert "DRIVER_ASSIGNED" in event_types(db, ids[2])


def test_manual_assignment_validation_and_reassignment(client, db, world):
    make, ops = world["make"], world["ops"]
    other_driver, other_vehicle, _ = make.driver()
    on_leave, _, _ = make.driver(availability="ON_LEAVE")
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    # Manual shipment creation itself refuses unpaid orders, so build the unpaid shipment directly in the database.
    unpaid_shipment = make._save(Shipment(order_id=order_id, warehouse_id=world["warehouse"].warehouse_id,
                                          route_id=world["route"].route_id, shipment_status="CREATED")).shipment_id
    unpaid = client.post(f"/shipments/{unpaid_shipment}/assignment", json={"driver_id": other_driver.employee_id}, headers=ops)
    assert unpaid.status_code == 409 and "Payment has not succeeded" in unpaid.json()["detail"]

    paid_order = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    shipment_id = pay(client, world["headers"], paid_order).json()["fulfilment"]["shipment_id"]
    url = f"/shipments/{shipment_id}/assignment"

    assert client.post(url, json={"driver_id": on_leave.employee_id}, headers=ops).status_code == 409
    wrong_pair = client.post(url, json={"driver_id": other_driver.employee_id, "vehicle_id": world["vehicle"].vehicle_id}, headers=ops)
    assert wrong_pair.status_code == 409 and "not currently assigned" in wrong_pair.json()["detail"]
    assert client.post(url, json={"driver_id": 99999}, headers=ops).status_code == 404
    assert client.post(url, json={"driver_id": other_driver.employee_id, "surprise": 1}, headers=ops).status_code == 422
    assert client.post(url, json={"driver_id": other_driver.employee_id}, headers=world["headers"]).status_code == 403
    assert client.post(url, json={"driver_id": other_driver.employee_id}, headers=world["driver_headers"]).status_code == 403

    moved = client.post(url, json={"driver_id": other_driver.employee_id}, headers=ops)
    assert moved.status_code == 200 and moved.json()["vehicle_id"] == other_vehicle.vehicle_id
    assert "REASSIGNED" in event_types(db, paid_order)
    assert count(db, Delivery, Delivery.shipment_id == shipment_id) == 1

    # Once the delivery has started it cannot be moved.
    assert client.put(f"/deliveries/{moved.json()['delivery_id']}/status", json={"delivery_status": "OUT_FOR_DELIVERY"}, headers=ops).status_code == 200
    assert client.post(url, json={"driver_id": world["driver"].employee_id}, headers=ops).status_code == 409


# --- Concurrency -------------------------------------------------------------------------------

def test_concurrent_checkouts_cannot_oversell_stock(db, make):
    customer, headers = make.customer()
    wh = make.warehouse("Vellore")
    product = make.product(weight=1)
    make.stock(wh, product, 5)
    make.route("Vellore", "Chennai")
    make.driver()

    def attempt():
        with TestClient(app) as c:
            return checkout_to(c, headers, [(product, 1)], "Chennai")

    responses = run_concurrently(8, attempt)
    codes = sorted(getattr(r, "status_code", r) for r in responses)
    assert codes == [201] * 5 + [409] * 3, codes
    assert stock(db, wh, product) == 0
    assert count(db, OrderInventoryReservation) == 5 and count(db, OrderFulfilment) == 5


def test_concurrent_payments_cannot_double_allocate_a_driver(db, world, monkeypatch):
    monkeypatch.setattr(fulfilment, "MAX_OPEN_DELIVERIES_PER_DRIVER", 1)
    with TestClient(app) as c:
        ids = [order_id_of(checkout_to(c, world["headers"], [(world["product"], 1)], "Chennai")) for _ in range(5)]

    counter = iter(ids)

    def attempt():
        oid = next(counter)
        with TestClient(app) as c:
            return pay(c, world["headers"], oid)

    responses = run_concurrently(5, attempt)
    assert all(getattr(r, "status_code", None) == 200 for r in responses), responses
    statuses = sorted(r.json()["fulfilment"]["status"] for r in responses)
    assert statuses == ["DRIVER_ASSIGNED"] + ["PENDING_ASSIGNMENT"] * 4
    assert count(db, Delivery) == 1 and count(db, Shipment) == 5


def test_concurrent_payments_cannot_overload_a_vehicle(db, make, monkeypatch):
    monkeypatch.setattr(fulfilment, "MAX_OPEN_DELIVERIES_PER_DRIVER", 10)
    customer, headers = make.customer()
    wh = make.warehouse("Vellore")
    product = make.product(weight=4)
    make.stock(wh, product, 20)
    make.route("Vellore", "Chennai")
    make.driver(vehicle_capacity=8)       # room for exactly two 4 kg shipments
    with TestClient(app) as c:
        ids = [order_id_of(checkout_to(c, headers, [(product, 1)], "Chennai")) for _ in range(5)]
    counter = iter(ids)

    def attempt():
        oid = next(counter)
        with TestClient(app) as c:
            return pay(c, headers, oid)

    responses = run_concurrently(5, attempt)
    statuses = sorted(r.json()["fulfilment"]["status"] for r in responses)
    assert statuses == ["DRIVER_ASSIGNED"] * 2 + ["PENDING_ASSIGNMENT"] * 3
    assert count(db, Delivery) == 2


# --- Status consistency and tracking ---------------------------------------------------------------

def test_order_status_follows_the_shipment_and_never_moves_back(client, db, world):
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    shipment_id = pay(client, world["headers"], order_id).json()["fulfilment"]["shipment_id"]
    driver = world["driver_headers"]

    def order_status():
        db.expire_all()
        return db.get(Order, order_id).order_status

    assert order_status() == "PROCESSING"
    assert tracking(client, driver, shipment_id, "PICKED_UP").status_code == 200 and order_status() == "SHIPPED"
    assert tracking(client, driver, shipment_id, "IN_TRANSIT").status_code == 200 and order_status() == "SHIPPED"
    assert tracking(client, driver, shipment_id, "PICKED_UP").status_code == 409 and order_status() == "SHIPPED"  # rejected, unchanged
    assert tracking(client, driver, shipment_id, "DELIVERED").status_code == 200 and order_status() == "DELIVERED"
    assert tracking(client, driver, shipment_id, "IN_TRANSIT").status_code == 409 and order_status() == "DELIVERED"


def test_cancelled_orders_are_not_revived_by_shipment_changes(client, db, world):
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    shipment_id = pay(client, world["headers"], order_id).json()["fulfilment"]["shipment_id"]
    db.rollback()
    with engine.begin() as conn:  # an operator-level cancellation recorded directly
        conn.execute(text("UPDATE orders SET order_status = 'CANCELLED' WHERE order_id = :o"), {"o": order_id})
    assert tracking(client, world["driver_headers"], shipment_id, "PICKED_UP").status_code == 200
    db.expire_all()
    assert db.get(Order, order_id).order_status == "CANCELLED"


def test_tracking_view_shows_persisted_milestones_only(client, db, world):
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    shipment_id = pay(client, world["headers"], order_id).json()["fulfilment"]["shipment_id"]
    tracking(client, world["driver_headers"], shipment_id, "PICKED_UP")
    tracking(client, world["driver_headers"], shipment_id, "OUT_FOR_DELIVERY")   # skips IN_TRANSIT

    view = client.get(f"/orders/{order_id}/tracking", headers=world["ops"]).json()
    states = {m["key"]: m["state"] for m in view["milestones"]}
    assert states["ORDER_PLACED"] == states["PAYMENT_CONFIRMED"] == states["ORDER_APPROVED"] == states["SHIPMENT_PLANNED"] == "done"
    assert states["SHIPMENT_CREATED"] == states["DRIVER_ASSIGNED"] == states["PICKED_UP"] == "done"
    assert states["IN_TRANSIT"] == "skipped" and states["OUT_FOR_DELIVERY"] == "done" and states["DELIVERED"] == "current"
    done = [m for m in view["milestones"] if m["state"] == "done"]
    assert all(m["at"] is not None for m in done)
    assert [e["status"] for e in view["tracking_events"]] == ["CREATED", "PICKED_UP", "OUT_FOR_DELIVERY"]
    assert view["latest_event"]["status"] == "OUT_FOR_DELIVERY" and view["live_tracking"]["supported"] is False
    assert view["route"]["intermediate_stops"] is None and view["shipment"]["shipment_status"] == "OUT_FOR_DELIVERY"
    assert view["assignment"]["vehicle_registration"] == world["vehicle"].registration_no

    # The customer sees the same journey without internal steps or "skipped"/diagnostic wording.
    mine = client.get(f"/orders/{order_id}/tracking", headers=world["headers"]).json()
    mine_states = {m["key"]: m["state"] for m in mine["milestones"]}
    assert "SHIPMENT_PLANNED" not in mine_states and mine_states["IN_TRANSIT"] == "done"
    assert mine["assignment"]["vehicle_registration"] == world["vehicle"].registration_no


def test_tracking_explains_pending_and_blocked_states(client, db, world):
    # A genuine block: the planned warehouse is taken out of service after the order was placed.
    blocked = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    with engine.begin() as conn:
        conn.execute(text("UPDATE warehouse SET status = 'INACTIVE' WHERE warehouse_id = :w"), {"w": world["warehouse"].warehouse_id})
    assert client.post(f"/operations/orders/{blocked}/retry-fulfilment", headers=world["ops"]).status_code == 200
    view = client.get(f"/orders/{blocked}/tracking", headers=world["ops"]).json()
    assert "blocked" in view["explanation"].lower() and "INACTIVE" in view["explanation"]
    assert {m["key"]: m["state"] for m in view["milestones"]}["SHIPMENT_PLANNED"] == "blocked"
    friendly = client.get(f"/orders/{blocked}/tracking", headers=world["headers"]).json()
    assert friendly["explanation"].startswith("Awaiting payment")
    assert "blocked" not in str(friendly).lower() and "inactive" not in str(friendly).lower()
    with engine.begin() as conn:
        conn.execute(text("UPDATE warehouse SET status = 'ACTIVE' WHERE warehouse_id = :w"), {"w": world["warehouse"].warehouse_id})

    waiting = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    assert "Awaiting payment" in client.get(f"/orders/{waiting}/tracking", headers=world["ops"]).json()["explanation"]
    client.post(f"/orders/{waiting}/cancel", headers=world["headers"])
    cancelled = client.get(f"/orders/{waiting}/tracking", headers=world["headers"]).json()
    assert cancelled["explanation"] == "This order was cancelled." and cancelled["milestones"][-1]["key"] == "CANCELLED"


def test_old_orders_are_shown_honestly_without_invented_history(client, db, world):
    legacy = world["make"].legacy_order(world["customer"], world["product"])
    view = client.get(f"/orders/{legacy.order_id}/tracking", headers=world["ops"]).json()
    states = {m["key"]: m["state"] for m in view["milestones"]}
    assert states["SHIPMENT_PLANNED"] == "not_recorded"
    assert view["fulfilment"] is None and view["tracking_events"] == [] and view["shipment"] is None
    assert count(db, OrderFulfilmentEvent) == 0 and count(db, OrderFulfilment) == 0   # nothing was written by viewing


# --- Access control ---------------------------------------------------------------------------------

def test_tracking_access_is_scoped_by_role(client, db, world):
    order_id = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
    pay(client, world["headers"], order_id)
    _, other_customer = world["make"].customer()
    _, _, other_driver = world["make"].driver()

    assert client.get(f"/orders/{order_id}/tracking", headers=other_customer).status_code == 403
    assert client.get(f"/orders/{order_id}/tracking", headers=other_driver).status_code == 403
    assert client.get(f"/orders/{order_id}/tracking", headers=world["driver_headers"]).status_code == 200
    assert client.get("/orders/99999/tracking", headers=world["ops"]).status_code == 404
    assert client.get(f"/orders/{order_id}/tracking").status_code in (401, 403)

    customer_view = client.get(f"/orders/{order_id}/tracking", headers=world["headers"]).json()
    staff_view = client.get(f"/orders/{order_id}/tracking", headers=world["ops"]).json()
    assert customer_view["fulfilment"] is None and "fulfilment_events" not in customer_view
    assert "driver_id" not in customer_view["assignment"] and "address" not in customer_view["warehouse"]
    assert staff_view["fulfilment"]["selection_note"] and staff_view["fulfilment_events"]
    driver_view = client.get(f"/orders/{order_id}/tracking", headers=world["driver_headers"]).json()
    assert driver_view["payment"] is None and driver_view["order"]["customer_name"] is None


def test_operations_endpoints_are_staff_only(client, world):
    for path in ("/operations/summary", "/operations/warehouses", "/operations/shipments", "/operations/orders"):
        assert client.get(path, headers=world["ops"]).status_code == 200, path
        assert client.get(path, headers=world["admin"]).status_code == 200, path
        assert client.get(path, headers=world["headers"]).status_code == 403, path
        assert client.get(path, headers=world["driver_headers"]).status_code == 403, path
    assert client.post("/operations/release-abandoned", headers=world["driver_headers"]).status_code == 403
    assert client.post("/operations/orders/1/retry-fulfilment", headers=world["headers"]).status_code == 403


# --- Operations desk ---------------------------------------------------------------------------------

def test_warehouse_overview_lists_every_warehouse_with_real_numbers(client, db, make):
    customer, headers = make.customer()
    product = make.product(weight=1)
    main = make.warehouse("Vellore", capacity=100)
    empty = make.warehouse("Salem")                       # no stock, no capacity
    closed = make.warehouse("Madurai", status="INACTIVE")
    make.stock(main, product, 10)
    make.stock(closed, product, 3)
    make.route("Vellore", "Chennai")
    make.driver()
    _, ops = make.user("OPERATIONS_MANAGER")

    order_id = order_id_of(checkout_to(client, headers, [(product, 4)], "Chennai"))
    rows = {w["warehouse_id"]: w for w in client.get("/operations/warehouses", headers=ops).json()}
    assert set(rows) == {main.warehouse_id, empty.warehouse_id, closed.warehouse_id}

    w = rows[main.warehouse_id]
    assert (w["units_available"], w["units_reserved"], w["units_on_hand"]) == (6, 4, 10)
    assert w["utilisation_percent"] == 10.0 and w["outgoing_routes"] == 1
    assert w["inventory"][0]["available"] == 6 and w["inventory"][0]["reserved"] == 4
    assert w["orders_in_fulfilment"]["count"] == 1 and w["orders_in_fulfilment"]["orders"][0]["order_id"] == order_id
    assert w["incoming_shipments"]["supported"] is False
    assert rows[empty.warehouse_id]["data_gaps"] and rows[empty.warehouse_id]["utilisation_percent"] is None
    assert rows[closed.warehouse_id]["is_active"] is False and rows[closed.warehouse_id]["units_available"] == 3

    # After payment and pickup the stock has left the building: no longer reserved.
    shipment_id = pay(client, headers, order_id).json()["fulfilment"]["shipment_id"]
    db.rollback()
    assert client.get("/operations/warehouses", headers=ops).json()[0]["units_reserved"] == 4
    client.post("/tracking", json={"shipment_id": shipment_id, "status": "PICKED_UP"}, headers=ops)
    after = {x["warehouse_id"]: x for x in client.get("/operations/warehouses", headers=ops).json()}[main.warehouse_id]
    assert (after["units_available"], after["units_reserved"]) == (6, 0)
    assert after["outgoing_shipments"]["in_flight"] == 1


def test_shipment_desk_search_filter_sort_and_pagination(client, db, world):
    make = world["make"]
    make.driver()
    ids = []
    for _ in range(4):
        oid = order_id_of(checkout_to(client, world["headers"], [(world["product"], 1)], "Chennai"))
        ids.append(pay(client, world["headers"], oid).json()["fulfilment"]["shipment_id"])
    tracking(client, world["driver_headers"], ids[0], "PICKED_UP")
    ops = world["ops"]

    page = client.get("/operations/shipments", params={"page_size": 3, "sort": "shipment_id", "direction": "asc"}, headers=ops).json()
    assert page["total"] == 4 and page["pages"] == 2 and [s["shipment_id"] for s in page["items"]] == ids[:3]
    row = page["items"][0]
    assert row["customer_name"] and row["warehouse_name"] and row["route_name"] and row["driver_name"] and row["vehicle_registration"]
    assert row["shipment_status"] == "PICKED_UP" and row["order_status"] == "SHIPPED"

    assert client.get("/operations/shipments", params={"status": "PICKED_UP"}, headers=ops).json()["total"] == 1
    assert client.get("/operations/shipments", params={"assignment": "assigned"}, headers=ops).json()["total"] == 4
    assert client.get("/operations/shipments", params={"assignment": "unassigned"}, headers=ops).json()["total"] == 0
    assert client.get("/operations/shipments", params={"q": str(ids[2])}, headers=ops).json()["items"][0]["shipment_id"] == ids[2]
    assert client.get("/operations/shipments", params={"q": world["driver"].employee_id and "no-such-person"}, headers=ops).json()["total"] == 0
    assert client.get("/operations/shipments", params={"status": "TELEPORTED"}, headers=ops).status_code == 422
    assert client.get("/operations/shipments", params={"direction": "sideways"}, headers=ops).status_code == 422
    assert client.get("/operations/shipments/99999", headers=ops).status_code == 404


def test_unassigned_and_blocked_work_is_visible_with_reasons(client, db, make):
    customer, headers = make.customer()
    wh = make.warehouse("Vellore")
    other = make.warehouse("Chennai")
    product = make.product(weight=1)
    only_other = make.product(weight=1)
    make.stock(wh, product, 10)
    make.stock(other, only_other, 10)                     # no driver exists at all
    _, ops = make.user("OPERATIONS_MANAGER")

    waiting = order_id_of(checkout_to(client, headers, [(product, 1)], "Chennai"))
    blocked = order_id_of(checkout_to(client, headers, [(only_other, 1)], "Chennai"))
    unpaid = order_id_of(checkout_to(client, headers, [(product, 1)], "Chennai"))
    with engine.begin() as conn:                          # the blocked order's warehouse leaves service
        conn.execute(text("UPDATE warehouse SET status = 'INACTIVE' WHERE warehouse_id = :w"), {"w": other.warehouse_id})
    shipment_id = pay(client, headers, waiting).json()["fulfilment"]["shipment_id"]
    pay(client, headers, blocked)

    shipments = client.get("/operations/shipments", params={"assignment": "unassigned"}, headers=ops).json()
    assert [s["shipment_id"] for s in shipments["items"]] == [shipment_id]
    assert "No drivers are registered" in shipments["items"][0]["pending_reason"] or "eligible" in shipments["items"][0]["pending_reason"]

    attention = client.get("/operations/orders", params={"stage": "attention"}, headers=ops).json()
    by_id = {o["order_id"]: o for o in attention["items"]}
    assert blocked in by_id and by_id[blocked]["reason_code"] == "WAREHOUSE_INACTIVE" and "Chennai" in by_id[blocked]["reason_detail"]
    assert by_id[blocked]["exception"]["code"] == "WAREHOUSE_INACTIVE"
    assert unpaid not in by_id and waiting not in by_id  # unpaid / already shipped need no attention
    assert unpaid in {o["order_id"] for o in client.get("/operations/orders", params={"stage": "awaiting_payment"}, headers=ops).json()["items"]}

    summary = client.get("/operations/summary", headers=ops).json()
    assert summary["orders"]["total"] == 3 and summary["orders"]["awaiting_payment"] == 1
    assert summary["orders"]["awaiting_fulfilment"] == 1 and summary["orders"]["blocked"] == 1
    assert summary["shipments"]["awaiting_assignment"] == 1 and summary["fleet"]["drivers_total"] == 0
    assert summary["warehouses"]["total"] == 2

def test_summary_reports_legacy_status_mismatches_without_rewriting_them(client, db, make):
    customer, _ = make.customer()
    wh = make.warehouse("Vellore")
    product = make.product()
    make.route("Vellore", "Chennai")
    order = make.legacy_order(customer, product)
    _, ops = make.user("OPERATIONS_MANAGER")
    db.rollback()
    with engine.begin() as conn:   # a shipment delivered before orders and shipments were kept in sync
        conn.execute(text("ALTER TABLE shipment DISABLE TRIGGER USER"))
        conn.execute(text("INSERT INTO shipment (order_id, warehouse_id, route_id, shipment_status, shipment_date) "
                          "SELECT :o, :w, route_id, 'DELIVERED', now() - interval '1 day' FROM route LIMIT 1"),
                     {"o": order.order_id, "w": wh.warehouse_id})
        conn.execute(text("ALTER TABLE shipment ENABLE TRIGGER USER"))

    summary = client.get("/operations/summary", headers=ops).json()
    assert summary["data_consistency"]["order_shipment_mismatches"] == 1
    view = client.get(f"/orders/{order.order_id}/tracking", headers=ops).json()
    assert view["warnings"] and "DELIVERED" in view["warnings"][0]
    db.expire_all()
    assert db.get(Order, order.order_id).order_status == "PENDING"   # shown, not rewritten
