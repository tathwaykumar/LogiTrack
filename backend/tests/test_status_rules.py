"""Shipment/delivery status consistency and transition rules (migration 003)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from conftest import REPO_DIR, _load_sql
from database import engine
from main import app
from models import Delivery, Shipment, ShipmentTracking
from test_fulfilment import checkout, count, pay, run_concurrently

FLOW = ["PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"]
EXPECTED_DELIVERY = {"CREATED": "PENDING", "PICKED_UP": "PENDING", "IN_TRANSIT": "PENDING", "OUT_FOR_DELIVERY": "OUT_FOR_DELIVERY", "DELIVERED": "DELIVERED", "CANCELLED": "CANCELLED"}


@pytest.fixture
def flow(client, make):
    """A paid order whose shipment is CREATED with a PENDING delivery for driver A."""
    customer, customer_headers = make.customer()
    warehouse = make.warehouse("Vellore")
    product = make.product()
    make.stock(warehouse, product, 20)
    make.route("Vellore", "Chennai")
    driver, _, driver_headers = make.driver()
    _, ops = make.user("OPERATIONS_MANAGER")
    _, admin = make.user("ADMIN")

    def new_shipment():
        order_id = checkout(client, customer_headers, [(product, 1)]).json()["order"]["order_id"]
        fulfilment = pay(client, customer_headers, order_id).json()["fulfilment"]
        assert fulfilment["status"] == "DRIVER_ASSIGNED", fulfilment
        return fulfilment["shipment_id"]

    shipment_id = new_shipment()
    return {
        "shipment_id": shipment_id, "driver": driver, "driver_headers": driver_headers, "ops": ops, "admin": admin,
        "customer_headers": customer_headers, "new_shipment": new_shipment, "make": make,
    }


def track(client, headers, shipment_id, status, **extra):
    return client.post("/tracking", json={"shipment_id": shipment_id, "status": status, **extra}, headers=headers)


def set_shipment(client, headers, shipment_id, status):
    return client.put(f"/shipments/{shipment_id}/status", json={"status": status}, headers=headers)


def set_delivery(client, headers, delivery_id, status):
    return client.put(f"/deliveries/{delivery_id}/status", json={"delivery_status": status}, headers=headers)


def state(db, shipment_id):
    db.expire_all()
    shipment = db.get(Shipment, shipment_id)
    delivery = db.query(Delivery).filter_by(shipment_id=shipment_id).one()
    events = db.query(ShipmentTracking).filter_by(shipment_id=shipment_id).order_by(ShipmentTracking.tracking_id).all()
    return shipment, delivery, events


# --- Bug 1: one source of truth -----------------------------------------------

def test_tracking_progression_keeps_delivery_in_step(client, db, flow):
    shipment_id = flow["shipment_id"]
    for status in FLOW:
        response = track(client, flow["driver_headers"], shipment_id, status, location="On route")
        assert response.status_code == 200, response.text
        shipment, delivery, _ = state(db, shipment_id)
        assert shipment.shipment_status == status
        assert delivery.delivery_status == EXPECTED_DELIVERY[status]

    shipment, delivery, events = state(db, shipment_id)
    assert shipment.actual_delivery is not None
    assert delivery.delivery_date is not None
    assert [event.status for event in events] == ["CREATED", *FLOW]


def test_driver_pages_agree_for_every_shipment(client, db, flow):
    """What drove the bug: /shipments said DELIVERED while /deliveries said PENDING."""
    first = flow["shipment_id"]
    second = flow["new_shipment"]()
    third = flow["new_shipment"]()
    for status in FLOW:
        assert track(client, flow["driver_headers"], first, status).status_code == 200
    assert track(client, flow["driver_headers"], second, "OUT_FOR_DELIVERY").status_code == 200

    headers = flow["driver_headers"]
    shipments = {s["shipment_id"]: s["shipment_status"] for s in client.get("/shipments", headers=headers).json()}
    deliveries = {d["shipment_id"]: d["delivery_status"] for d in client.get("/deliveries", headers=headers).json()}
    assert set(shipments) == set(deliveries) == {first, second, third}
    for shipment_id, shipment_status in shipments.items():
        assert deliveries[shipment_id] == EXPECTED_DELIVERY[shipment_status], (shipment_id, shipment_status, deliveries[shipment_id])

    # The figures the dashboard and the delivery board derive from these records.
    open_deliveries = [s for s in deliveries.values() if s not in ("DELIVERED", "CANCELLED")]
    delivered_shipments = [s for s in shipments.values() if s == "DELIVERED"]
    assert len(open_deliveries) == 2
    assert len(delivered_shipments) == list(deliveries.values()).count("DELIVERED") == 1

    # Timeline header and latest event agree with the shipment list.
    for shipment_id, shipment_status in shipments.items():
        timeline = client.get(f"/shipments/{shipment_id}/timeline", headers=headers).json()
        assert timeline["shipment_status"] == shipment_status
        assert timeline["tracking_events"][-1]["status"] == shipment_status


def test_delivery_endpoint_moves_the_shipment_too(client, db, flow):
    delivery_id = state(db, flow["shipment_id"])[1].delivery_id
    assert track(client, flow["driver_headers"], flow["shipment_id"], "IN_TRANSIT").status_code == 200

    response = set_delivery(client, flow["driver_headers"], delivery_id, "OUT_FOR_DELIVERY")
    assert response.status_code == 200, response.text
    assert response.json()["tracking_event_created"] is True
    response = set_delivery(client, flow["driver_headers"], delivery_id, "DELIVERED")
    assert response.status_code == 200, response.text
    assert response.json()["shipment_status"] == "DELIVERED"

    shipment, delivery, events = state(db, flow["shipment_id"])
    assert (shipment.shipment_status, delivery.delivery_status) == ("DELIVERED", "DELIVERED")
    assert events[-1].status == "DELIVERED" and "delivery #" in events[-1].remarks


def test_failed_attempt_then_successful_retry(client, db, flow):
    shipment_id = flow["shipment_id"]
    delivery_id = state(db, shipment_id)[1].delivery_id
    assert track(client, flow["driver_headers"], shipment_id, "OUT_FOR_DELIVERY").status_code == 200

    assert set_delivery(client, flow["driver_headers"], delivery_id, "FAILED").status_code == 200
    shipment, delivery, _ = state(db, shipment_id)
    assert (shipment.shipment_status, delivery.delivery_status) == ("OUT_FOR_DELIVERY", "FAILED")

    # A new out-for-delivery event is the retry and re-opens the delivery.
    assert track(client, flow["driver_headers"], shipment_id, "OUT_FOR_DELIVERY", remarks="Second attempt").status_code == 200
    assert state(db, shipment_id)[1].delivery_status == "OUT_FOR_DELIVERY"
    assert track(client, flow["driver_headers"], shipment_id, "DELIVERED").status_code == 200
    assert state(db, shipment_id)[1].delivery_status == "DELIVERED"


def test_failed_is_only_valid_during_a_delivery_attempt(client, db, flow):
    delivery_id = state(db, flow["shipment_id"])[1].delivery_id
    response = set_delivery(client, flow["driver_headers"], delivery_id, "FAILED")
    assert response.status_code == 409
    assert state(db, flow["shipment_id"])[1].delivery_status == "PENDING"


def test_delivery_cannot_be_set_back_to_pending(client, db, flow):
    shipment_id = flow["shipment_id"]
    delivery_id = state(db, shipment_id)[1].delivery_id
    assert track(client, flow["driver_headers"], shipment_id, "OUT_FOR_DELIVERY").status_code == 200
    assert set_delivery(client, flow["ops"], delivery_id, "PENDING").status_code == 409
    assert state(db, shipment_id)[1].delivery_status == "OUT_FOR_DELIVERY"


def test_invalid_and_missing_delivery_requests(client, db, flow):
    delivery_id = state(db, flow["shipment_id"])[1].delivery_id
    assert set_delivery(client, flow["ops"], delivery_id, "TELEPORTED").status_code == 422
    assert set_delivery(client, flow["ops"], 999999, "DELIVERED").status_code == 404


# --- Valid transitions -----------------------------------------------------------

def test_checkpoint_events_and_skipped_stages_are_allowed(client, db, flow):
    shipment_id = flow["shipment_id"]
    assert track(client, flow["driver_headers"], shipment_id, "IN_TRANSIT", location="Ranipet").status_code == 200
    assert track(client, flow["driver_headers"], shipment_id, "IN_TRANSIT", location="Kanchipuram").status_code == 200
    assert track(client, flow["driver_headers"], shipment_id, "DELIVERED").status_code == 200  # skips OUT_FOR_DELIVERY
    assert [event.status for event in state(db, shipment_id)[2]] == ["CREATED", "IN_TRANSIT", "IN_TRANSIT", "DELIVERED"]


@pytest.mark.parametrize("current, attempted", [
    ("PICKED_UP", "CREATED"),
    ("IN_TRANSIT", "PICKED_UP"),
    ("OUT_FOR_DELIVERY", "IN_TRANSIT"),
    ("OUT_FOR_DELIVERY", "CREATED"),
])
def test_backward_moves_are_rejected_on_every_endpoint(client, db, flow, current, attempted):
    shipment_id = flow["shipment_id"]
    assert track(client, flow["driver_headers"], shipment_id, current).status_code == 200
    before = len(state(db, shipment_id)[2])

    assert track(client, flow["driver_headers"], shipment_id, attempted).status_code == 409
    assert track(client, flow["ops"], shipment_id, attempted).status_code == 409
    assert set_shipment(client, flow["ops"], shipment_id, attempted).status_code == 409

    shipment, delivery, events = state(db, shipment_id)
    assert shipment.shipment_status == current
    assert delivery.delivery_status == EXPECTED_DELIVERY[current]
    assert len(events) == before


def test_cancellation_from_an_open_stage(client, db, flow):
    shipment_id = flow["shipment_id"]
    assert track(client, flow["driver_headers"], shipment_id, "IN_TRANSIT").status_code == 200
    assert set_shipment(client, flow["ops"], shipment_id, "CANCELLED").status_code == 200
    shipment, delivery, _ = state(db, shipment_id)
    assert (shipment.shipment_status, delivery.delivery_status) == ("CANCELLED", "CANCELLED")


# --- Bug 2: closed shipments stay closed ----------------------------------------

@pytest.mark.parametrize("terminal", ["DELIVERED", "CANCELLED"])
def test_closed_shipment_cannot_change_through_any_endpoint(client, db, flow, terminal):
    shipment_id = flow["shipment_id"]
    if terminal == "DELIVERED":
        for status in FLOW:
            assert track(client, flow["driver_headers"], shipment_id, status).status_code == 200
    else:
        assert set_shipment(client, flow["ops"], shipment_id, "CANCELLED").status_code == 200
    shipment, delivery, events = state(db, shipment_id)
    snapshot = (shipment.shipment_status, shipment.actual_delivery, delivery.delivery_status, delivery.delivery_date, [(e.tracking_id, e.status) for e in events])

    for status in ["CREATED", "PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"]:
        for headers in (flow["driver_headers"], flow["ops"], flow["admin"]):
            response = track(client, headers, shipment_id, status, remarks="late update")
            assert response.status_code == 409, (status, response.text)
        if status != terminal:
            assert set_shipment(client, flow["ops"], shipment_id, status).status_code == 409
    for status in ["PENDING", "OUT_FOR_DELIVERY", "DELIVERED", "FAILED", "CANCELLED"]:
        if status != delivery.delivery_status:
            assert set_delivery(client, flow["ops"], delivery.delivery_id, status).status_code == 409

    # Re-sending the current status is an idempotent no-op, not a new event.
    same = set_shipment(client, flow["ops"], shipment_id, terminal)
    assert same.status_code == 200 and same.json()["tracking_event_created"] is False
    assert set_delivery(client, flow["ops"], delivery.delivery_id, delivery.delivery_status).status_code == 200

    shipment, delivery, events = state(db, shipment_id)
    assert (shipment.shipment_status, shipment.actual_delivery, delivery.delivery_status, delivery.delivery_date, [(e.tracking_id, e.status) for e in events]) == snapshot


def test_database_blocks_bypasses(db, flow, client):
    """Direct SQL and the stored procedure are held to the same rules."""
    shipment_id = flow["shipment_id"]
    for status in FLOW:
        assert track(client, flow["driver_headers"], shipment_id, status).status_code == 200
    delivery_id = state(db, shipment_id)[1].delivery_id

    attempts = [
        ("UPDATE shipment SET shipment_status = 'IN_TRANSIT' WHERE shipment_id = :s", {"s": shipment_id}),
        ("CALL update_shipment_status(:s, 'OUT_FOR_DELIVERY')", {"s": shipment_id}),
        ("INSERT INTO shipment_tracking (shipment_id, status) VALUES (:s, 'IN_TRANSIT')", {"s": shipment_id}),
        ("INSERT INTO shipment_tracking (shipment_id, status) VALUES (:s, 'DELIVERED')", {"s": shipment_id}),
        ("UPDATE delivery SET delivery_status = 'PENDING' WHERE delivery_id = :d", {"d": delivery_id}),
    ]
    for sql, params in attempts:
        with engine.connect() as conn:
            with pytest.raises(DBAPIError) as error:
                conn.execute(text(sql), params)
            assert error.value.orig.pgcode == "LT409", sql
            conn.rollback()

    shipment, delivery, events = state(db, shipment_id)
    assert (shipment.shipment_status, delivery.delivery_status, len(events)) == ("DELIVERED", "DELIVERED", 5)


def test_database_blocks_incompatible_delivery_rows(db, flow):
    """A delivery cannot claim DELIVERED while its shipment is still moving."""
    shipment_id = flow["shipment_id"]
    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as error:
            conn.execute(text("UPDATE delivery SET delivery_status = 'DELIVERED' WHERE shipment_id = :s"), {"s": shipment_id})
        assert error.value.orig.pgcode == "LT409"
        conn.rollback()


# --- Concurrency -----------------------------------------------------------------

def test_concurrent_delivery_confirmations_record_one_event(db, flow):
    shipment_id = flow["shipment_id"]
    with TestClient(app) as c:
        assert track(c, flow["driver_headers"], shipment_id, "OUT_FOR_DELIVERY").status_code == 200

    def attempt():
        with TestClient(app) as c:
            return track(c, flow["driver_headers"], shipment_id, "DELIVERED")

    responses = run_concurrently(8, attempt)
    codes = sorted(getattr(r, "status_code", r) for r in responses)
    assert codes == [200] + [409] * 7, codes
    shipment, delivery, events = state(db, shipment_id)
    assert [e.status for e in events].count("DELIVERED") == 1
    assert (shipment.shipment_status, delivery.delivery_status) == ("DELIVERED", "DELIVERED")


def test_concurrent_deliver_and_cancel_leave_a_consistent_result(db, flow):
    shipment_id = flow["shipment_id"]
    with TestClient(app) as c:
        assert track(c, flow["driver_headers"], shipment_id, "OUT_FOR_DELIVERY").status_code == 200

    statuses = iter(["DELIVERED", "CANCELLED"] * 4)

    def attempt():
        status = next(statuses)
        with TestClient(app) as c:
            return track(c, flow["ops"], shipment_id, status)

    responses = run_concurrently(8, attempt)
    assert sorted(getattr(r, "status_code", r) for r in responses) == [200] + [409] * 7
    shipment, delivery, events = state(db, shipment_id)
    assert shipment.shipment_status in ("DELIVERED", "CANCELLED")
    assert delivery.delivery_status == shipment.shipment_status
    assert events[-1].status == shipment.shipment_status
    assert sum(e.status in ("DELIVERED", "CANCELLED") for e in events) == 1


# --- Access rules are unchanged --------------------------------------------------

def test_driver_still_limited_to_assigned_shipments(client, db, flow):
    other_driver, _, other_headers = flow["make"].driver()
    shipment_id = flow["shipment_id"]
    delivery_id = state(db, shipment_id)[1].delivery_id
    assert track(client, other_headers, shipment_id, "IN_TRANSIT").status_code == 403
    assert set_delivery(client, other_headers, delivery_id, "OUT_FOR_DELIVERY").status_code == 403
    assert set_shipment(client, flow["driver_headers"], shipment_id, "IN_TRANSIT").status_code == 403
    assert track(client, flow["customer_headers"], shipment_id, "IN_TRANSIT").status_code == 403


# --- Legacy data reconciliation ----------------------------------------------------

def test_migration_reconciles_legacy_contradictions_without_touching_history(db, flow, client):
    """Reproduces the dev-data state (shipment DELIVERED by tracking, delivery PENDING)."""
    shipment_id = flow["shipment_id"]
    for status in FLOW:
        assert track(client, flow["driver_headers"], shipment_id, status).status_code == 200
    db.rollback()  # release this session's read locks before the DDL below
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE delivery DISABLE TRIGGER trg_enforce_delivery_status"))
        conn.execute(text("UPDATE delivery SET delivery_status = 'PENDING', delivery_date = NULL WHERE shipment_id = :s"), {"s": shipment_id})
        conn.execute(text("ALTER TABLE delivery ENABLE TRIGGER trg_enforce_delivery_status"))
    events_before = [(e.tracking_id, e.status, e.tracking_timestamp) for e in state(db, shipment_id)[2]]
    db.rollback()

    migration =_load_sql(Path(REPO_DIR) / "database" / "migrations" / "003_status_transition_rules.sql")
    raw = engine.raw_connection()
    try:
        raw.autocommit = True
        raw.cursor().execute(migration)
    finally:
        raw.close()

    shipment, delivery, events = state(db, shipment_id)
    assert delivery.delivery_status == "DELIVERED"
    assert delivery.delivery_date == shipment.actual_delivery
    assert [(e.tracking_id, e.status, e.tracking_timestamp) for e in events] == events_before
    assert count(db, ShipmentTracking) == len(events_before)
