"""Demo seed (fleet + warehouse stock), the pay -> approve -> ship sequence, and customer vs staff wording."""
import pytest
from sqlalchemy import func

import seed_demo_data
from auth import verify_password
from database import SessionLocal
from models import (
    Delivery, DemoSeedRecord, Driver, DriverVehicleAssignment, Employee, Inventory, Order, OrderFulfilment,
    Role, Shipment, User, Vehicle, Warehouse,
)
from test_fulfilment import approve, count, ops_headers, pay_only
from test_fulfilment_workflow import checkout_to, order_id_of

PASSWORD = "demo-password-for-tests"


@pytest.fixture
def network(make):
    """Four warehouses with uneven stock (one empty), six catalogue products, routes out of Vellore."""
    warehouses = [make.warehouse(city) for city in ("Vellore", "Chennai", "Bangalore", "Coimbatore")]
    products = [make.product(price=100 + n, weight=1) for n in range(6)]
    make.stock(warehouses[0], products[0], 17)
    make.stock(warehouses[0], products[1], 33)
    make.stock(warehouses[1], products[2], 5)
    make.route("Vellore", "Chennai")
    return {"warehouses": warehouses, "products": products}


def run_seed(**kwargs):
    with SessionLocal() as session:
        return seed_demo_data.seed(session, PASSWORD, **kwargs)


def inventory_snapshot():
    with SessionLocal() as session:
        return {(r.warehouse_id, r.product_id): (r.quantity, r.reorder_level)
                for r in session.query(Inventory)}


# --- The seed ------------------------------------------------------------------------------------

def test_seed_is_idempotent(network):
    first = run_seed()
    assert first["fleet"]["drivers_created"] == 10 and first["fleet"]["vehicles_created"] == 10
    after_first = {key: value for key, value in first["totals_after"].items()}

    second = run_seed()
    assert second["fleet"]["drivers_created"] == second["fleet"]["vehicles_created"] == second["fleet"]["assignments_created"] == 0
    assert second["inventory"]["inventory_rows_created"] == 0
    assert second["totals_after"] == after_first
    with SessionLocal() as session:
        assert session.query(func.count(User.user_id)).filter(User.username.like("demo_driver%")).scalar() == 10
        assert session.query(func.count(DemoSeedRecord.entity)).scalar() == 10 * 5 + first["inventory"]["inventory_rows_created"]


def test_dry_run_changes_nothing(network):
    before = inventory_snapshot()
    outcome = run_seed(dry_run=True)
    assert outcome["fleet"]["drivers_created"] == 10 and outcome["dry_run"] is True
    with SessionLocal() as session:
        assert session.query(func.count(Driver.employee_id)).scalar() == 0
        assert session.query(func.count(Vehicle.vehicle_id)).scalar() == 0
        assert session.query(func.count(DemoSeedRecord.entity)).scalar() == 0
    assert inventory_snapshot() == before


def test_every_warehouse_gets_inventory_and_existing_stock_is_preserved(network):
    before = inventory_snapshot()
    outcome = run_seed()
    after = inventory_snapshot()

    # Rows that already existed are byte-for-byte the same.
    assert all(after[key] == value for key, value in before.items())
    per_warehouse = {}
    for (warehouse_id, _product_id), (quantity, reorder) in after.items():
        per_warehouse[warehouse_id] = per_warehouse.get(warehouse_id, 0) + 1
        assert quantity > 0 and reorder >= 0
    assert set(per_warehouse) == {w.warehouse_id for w in network["warehouses"]}
    assert all(n >= min(seed_demo_data.MIN_PRODUCTS_PER_WAREHOUSE, 6) for n in per_warehouse.values())
    # Only the missing rows were added, and each one is recorded as demo data.
    added = set(after) - set(before)
    assert len(added) == outcome["inventory"]["inventory_rows_created"]
    with SessionLocal() as session:
        recorded = {tuple(int(x) for x in r.entity_key.split(":")) for r in session.query(DemoSeedRecord).filter_by(entity="inventory")}
    assert recorded == added


def test_demo_drivers_and_vehicles_satisfy_the_schema_and_rules(network):
    run_seed()
    with SessionLocal() as session:
        drivers = session.query(Driver, Employee, User).join(Employee, Employee.employee_id == Driver.employee_id) \
            .join(User, User.user_id == Employee.user_id).all()
        assert len(drivers) == 10
        driver_role = session.query(Role.role_id).filter_by(role_name="DRIVER").scalar()
        licences = set()
        for driver, employee, user in drivers:
            assert driver.availability_status == "AVAILABLE" and employee.employment_status == "ACTIVE" and user.is_active
            assert user.role_id == driver_role and user.username.startswith("demo_driver")
            assert user.email.endswith("@" + seed_demo_data.DEMO_EMAIL_DOMAIN) and "(Demo)" in employee.name
            assert driver.license_expiry > __import__("datetime").date.today()
            licences.add(driver.license_no)
            # The password is hashed with the application's helper, never stored as given.
            assert user.password_hash.startswith("$argon2") and PASSWORD not in user.password_hash
            assert verify_password(PASSWORD, user.password_hash)
        assert len(licences) == 10
        vehicles = session.query(Vehicle).all()
        assert len(vehicles) == 10 and len({v.registration_no for v in vehicles}) == 10
        assert all(v.status == "ACTIVE" and v.capacity > 0 and v.vehicle_type for v in vehicles)
        # Each driver has exactly one current vehicle and no vehicle is shared.
        current = session.query(DriverVehicleAssignment).filter(DriverVehicleAssignment.assigned_to.is_(None)).all()
        assert len(current) == 10 and len({a.driver_id for a in current}) == 10 and len({a.vehicle_id for a in current}) == 10
        # Nothing was dispatched just to fill a dashboard.
        assert session.query(func.count(Delivery.delivery_id)).scalar() == 0


def test_seed_never_touches_existing_drivers_vehicles_or_passwords(network, make):
    driver, vehicle, _ = make.driver()
    with SessionLocal() as session:
        before = (session.query(User.password_hash).filter(User.user_id == session.get(Employee, driver.employee_id).user_id).scalar(),
                  session.get(Vehicle, vehicle.vehicle_id).capacity)
    run_seed()
    with SessionLocal() as session:
        after = (session.query(User.password_hash).filter(User.user_id == session.get(Employee, driver.employee_id).user_id).scalar(),
                 session.get(Vehicle, vehicle.vehicle_id).capacity)
        assert before == after
        assert session.query(func.count(Driver.employee_id)).scalar() == 11


def test_seed_refuses_production_and_short_passwords(network, monkeypatch):
    monkeypatch.setenv("LOGITRACK_ENV", "production")
    with pytest.raises(SystemExit):
        seed_demo_data.refuse_in_production()
    with SessionLocal() as session, pytest.raises(ValueError):
        seed_demo_data.seed(session, "short")


# --- Inventory numbers ---------------------------------------------------------------------------

def test_available_reserved_and_on_hand_agree_with_persisted_data(client, db, make, network):
    run_seed()
    customer, headers = make.customer()
    _, ops = make.user("OPERATIONS_MANAGER")
    warehouse, product = network["warehouses"][0], network["products"][0]
    before = db.query(Inventory.quantity).filter_by(warehouse_id=warehouse.warehouse_id, product_id=product.product_id).scalar()

    order_id = order_id_of(checkout_to(client, headers, [(product, 4)], "Chennai"))
    lines = {(w["warehouse_id"], l["product_id"]): l for w in client.get("/operations/warehouses", headers=ops).json() for l in w["inventory"]}
    line = lines[(warehouse.warehouse_id, product.product_id)]
    assert line["available"] == before - 4 and line["reserved"] == 4 and line["on_hand"] == before
    assert all(l["reserved"] <= l["on_hand"] and l["available"] >= 0 for l in lines.values())

    # More than the stock that exists cannot be reserved.
    network_total = db.query(func.sum(Inventory.quantity)).filter_by(product_id=product.product_id).scalar()
    too_many = checkout_to(client, headers, [(product, network_total + 1)], "Chennai")
    assert too_many.status_code == 409

    # Cancelling returns the reservation: on hand and available converge again.
    assert client.post(f"/orders/{order_id}/cancel", headers=headers).status_code == 200
    lines = {(w["warehouse_id"], l["product_id"]): l for w in client.get("/operations/warehouses", headers=ops).json() for l in w["inventory"]}
    assert lines[(warehouse.warehouse_id, product.product_id)]["available"] == before


def test_catalogue_counts_only_stock_that_can_be_sold(client, make):
    customer, headers = make.customer()
    active = make.warehouse("Vellore")
    paused = make.warehouse("Chennai", status="INACTIVE")
    product = make.product()
    make.stock(active, product, 7)
    make.stock(paused, product, 100)
    rows = client.get("/shop/products", headers=headers).json()
    assert [r["available_stock"] for r in rows if r["product_id"] == product.product_id] == [7]


# --- Pay, then approve, then ship ----------------------------------------------------------------

@pytest.fixture
def shop(client, make, network):
    run_seed()
    customer, headers = make.customer()
    return {"customer": customer, "headers": headers, "product": network["products"][0], "ops": ops_headers()}


def test_payment_alone_never_creates_a_shipment(client, db, shop):
    order_id = order_id_of(checkout_to(client, shop["headers"], [(shop["product"], 1)], "Chennai"))
    paid = pay_only(client, shop["headers"], order_id)
    assert paid.status_code == 200 and paid.json()["fulfilment"]["status"] == "AWAITING_APPROVAL"
    assert count(db, Shipment) == 0 and count(db, Delivery) == 0

    orders = client.get("/orders", headers=shop["headers"]).json()
    assert orders[0]["stage"]["label"] == "Awaiting approval"
    desk = client.get("/operations/orders?stage=awaiting_approval", headers=shop["ops"]).json()
    assert [o["order_id"] for o in desk["items"]] == [order_id] and desk["items"][0]["approved"] is False
    assert client.get("/operations/summary", headers=shop["ops"]).json()["orders"]["awaiting_approval"] == 1


def test_approval_rules(client, db, shop):
    order_id = order_id_of(checkout_to(client, shop["headers"], [(shop["product"], 1)], "Chennai"))
    # Unpaid orders cannot be approved; customers cannot approve anything.
    assert approve(client, order_id, shop["ops"]).status_code == 409
    pay_only(client, shop["headers"], order_id)
    assert approve(client, order_id, shop["headers"]).status_code == 403
    assert approve(client, 99999, shop["ops"]).status_code == 404
    # Dispatch cannot be forced before approval through the re-check endpoint either.
    assert client.post(f"/operations/orders/{order_id}/retry-fulfilment", headers=shop["ops"]).status_code == 409
    assert count(db, Shipment) == 0

    first = approve(client, order_id, shop["ops"])
    again = approve(client, order_id, shop["ops"])
    assert first.status_code == again.status_code == 200
    assert first.json()["shipment_id"] == again.json()["shipment_id"]
    assert count(db, Shipment) == 1 and count(db, Delivery) == 1
    db.expire_all()
    plan = db.get(OrderFulfilment, order_id)
    assert plan.approved_at is not None and plan.approved_by_user_id is not None

    cancelled = order_id_of(checkout_to(client, shop["headers"], [(shop["product"], 1)], "Chennai"))
    client.post(f"/orders/{cancelled}/cancel", headers=shop["headers"])
    assert approve(client, cancelled, shop["ops"]).status_code == 409


def test_approval_assigns_a_real_fleet_pair(client, db, shop):
    order_id = order_id_of(checkout_to(client, shop["headers"], [(shop["product"], 1)], "Chennai"))
    pay_only(client, shop["headers"], order_id)
    body = approve(client, order_id, shop["ops"]).json()
    assert body["status"] == "DRIVER_ASSIGNED"

    db.expire_all()
    delivery = db.query(Delivery).one()
    pair = db.query(DriverVehicleAssignment).filter_by(
        driver_id=delivery.driver_id, vehicle_id=delivery.vehicle_id).filter(DriverVehicleAssignment.assigned_to.is_(None)).first()
    assert pair is not None and delivery.assigned_at is not None
    assert db.get(Driver, delivery.driver_id).employee_id == body["driver_id"]
    assert db.get(Order, order_id).order_status == "PROCESSING"

    # The customer sees the real assignment; staff and the driver's own list show it too.
    view = client.get(f"/orders/{order_id}/tracking", headers=shop["headers"]).json()
    assert view["stage"]["label"] == "Driver assigned" and view["assignment"]["vehicle_registration"].startswith("DEMO-FLT-")
    assert any(row["driver_id"] == body["driver_id"] for row in client.get("/operations/shipments", headers=shop["ops"]).json()["items"])


def test_conflicting_assignments_are_rejected(client, db, make, network):
    # One driver with a 1000 kg vehicle and two 900 kg orders: the second cannot share the vehicle.
    heavy = make.product(price=50, weight=900)
    make.stock(network["warehouses"][0], heavy, 5)
    driver, vehicle, _ = make.driver(vehicle_capacity=1000)
    customer, headers = make.customer()
    ops = ops_headers()
    first, second = (order_id_of(checkout_to(client, headers, [(heavy, 1)], "Chennai")) for _ in range(2))
    for order_id in (first, second):
        pay_only(client, headers, order_id)
    assert approve(client, first, ops).json()["status"] == "DRIVER_ASSIGNED"
    waiting = approve(client, second, ops).json()
    assert waiting["status"] == "PENDING_ASSIGNMENT" and waiting["driver_id"] is None   # no fake assignment

    attempt = client.post(f"/shipments/{waiting['shipment_id']}/assignment", headers=ops,
                          json={"driver_id": driver.employee_id, "vehicle_id": vehicle.vehicle_id})
    assert attempt.status_code == 409 and "capacity" in attempt.json()["detail"]
    assert count(db, Delivery) == 1
    # A pair that is not a current driver/vehicle assignment is rejected as well.
    other_vehicle = make.vehicle()
    mismatch = client.post(f"/shipments/{waiting['shipment_id']}/assignment", headers=ops,
                           json={"driver_id": driver.employee_id, "vehicle_id": other_vehicle.vehicle_id})
    assert mismatch.status_code == 409
    assert count(db, Delivery) == 1


# --- Customer wording vs staff diagnostics --------------------------------------------------------

FORBIDDEN_FOR_CUSTOMERS = ("no driver", "no vehicle", "eligible", "blocked", "reservation", "planning", "warehouse_name")


def test_unallocated_shipment_is_calm_for_customers_and_explicit_for_staff(client, db, make, network):
    # No drivers or vehicles exist: allocation genuinely cannot succeed.
    customer, headers = make.customer()
    ops = ops_headers()
    order_id = order_id_of(checkout_to(client, headers, [(network["products"][0], 1)], "Chennai"))
    pay_only(client, headers, order_id)
    body = approve(client, order_id, ops).json()
    assert body["status"] == "PENDING_ASSIGNMENT" and body["driver_id"] is None
    db.expire_all()
    shipment = db.query(Shipment).one()
    assert count(db, Delivery) == 0           # nothing invented

    view = client.get(f"/orders/{order_id}/tracking", headers=headers).json()
    text = str(view).lower()
    assert view["stage"]["label"] == "Preparing shipment" and view["assignment"] is None and view["fulfilment"] is None
    assert not any(word in text for word in FORBIDDEN_FOR_CUSTOMERS), text
    mine = client.get("/orders", headers=headers).json()[0]
    assert mine["stage"]["label"] == "Preparing shipment" and mine["fulfilment_reason"] is None and mine["fulfilment_status"] is None
    assert "warehouse" not in str(mine).lower()

    # Staff still see exactly what is wrong, and can resolve it.
    staff = client.get(f"/orders/{order_id}/tracking", headers=ops).json()
    assert staff["explanation"].startswith("Awaiting driver assignment.") and "No drivers are registered" in staff["explanation"]
    row = client.get("/operations/shipments?assignment=unassigned", headers=ops).json()["items"][0]
    assert row["shipment_id"] == shipment.shipment_id and row["pending_reason"]
    options = client.get(f"/operations/shipments/{shipment.shipment_id}/assignment-options", headers=ops).json()
    assert options["options"] == [] and options["summary"]

    driver, vehicle, _ = make.driver()
    fixed = client.post(f"/shipments/{shipment.shipment_id}/assignment", headers=ops,
                        json={"driver_id": driver.employee_id, "vehicle_id": vehicle.vehicle_id})
    assert fixed.status_code == 200, fixed.text
    assert client.get(f"/orders/{order_id}/tracking", headers=headers).json()["stage"]["label"] == "Driver assigned"


def test_awaiting_approval_wording_before_dispatch(client, db, make, network):
    customer, headers = make.customer()
    order_id = order_id_of(checkout_to(client, headers, [(network["products"][0], 1)], "Chennai"))
    unpaid = client.get(f"/orders/{order_id}/tracking", headers=headers).json()
    assert unpaid["stage"]["label"] == "Awaiting payment"
    pay_only(client, headers, order_id)
    paid = client.get(f"/orders/{order_id}/tracking", headers=headers).json()
    assert paid["stage"]["label"] == "Awaiting approval" and paid["explanation"] == "Payment received. Your order is awaiting approval."
    assert paid["assignment"] is None and paid["warehouse"] is None and paid["route"] is None
    assert [m["key"] for m in paid["milestones"]][:3] == ["ORDER_PLACED", "PAYMENT_CONFIRMED", "ORDER_APPROVED"]
