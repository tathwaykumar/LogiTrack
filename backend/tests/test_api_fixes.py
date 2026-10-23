"""Regression tests for the API defects found while documenting the project."""
import pytest
from sqlalchemy import text

from database import engine
from models import Shipment, User
from set_demo_passwords import is_placeholder, set_demo_passwords
from test_fulfilment import checkout, pay, pay_only, shop  # noqa: F401  (shop is a fixture)


@pytest.fixture
def ops(make):
    return make.user("OPERATIONS_MANAGER")[1]


@pytest.fixture
def admin(make):
    return make.user("ADMIN")[1]


# --- Search routes are reachable -------------------------------------------------

def test_order_and_customer_search_are_reachable(client, make, shop, ops):
    order = make.legacy_order(shop["customer"], shop["product"])

    found = client.get("/orders/search", params={"status": "pending"}, headers=ops)
    assert found.status_code == 200
    assert [o["order_id"] for o in found.json()] == [order.order_id]
    assert client.get("/orders/search", params={"status": "DELIVERED"}, headers=ops).json() == []
    assert client.get("/orders/search", params={"customer_id": shop["customer"].customer_id}, headers=ops).status_code == 200

    customers = client.get("/customers/search", params={"name": "customer"}, headers=ops)
    assert customers.status_code == 200
    assert [c["customer_id"] for c in customers.json()] == [shop["customer"].customer_id]

    # Numeric ids still reach the detail routes.
    assert client.get(f"/orders/{order.order_id}", headers=ops).status_code == 200
    assert client.get(f"/customers/{shop['customer'].customer_id}", headers=ops).status_code == 200
    assert client.get("/orders/not-a-number", headers=ops).status_code == 404  # matches no route


# --- Missing records are 404, not 200 -------------------------------------------

MISSING = [
    ("PUT", "/orders/99999/status", {"order_status": "CONFIRMED"}, "ops"),
    ("PUT", "/payments/99999/status", {"payment_status": "SUCCESS"}, "ops"),
    ("PUT", "/inventory/99999/99999", {"quantity": 1}, "ops"),
    ("PUT", "/vehicles/99999/status", {"status": "ACTIVE"}, "ops"),
    ("PUT", "/drivers/99999/status", {"availability_status": "AVAILABLE"}, "ops"),
    ("PUT", "/employees/99999/status", {"employment_status": "ACTIVE"}, "admin"),
    ("PUT", "/warehouses/99999/status", {"status": "ACTIVE"}, "ops"),
    ("PUT", "/products/99999/price", {"unit_price": 10}, "ops"),
    ("PUT", "/invoices/99999/status", {"invoice_status": "PAID"}, "ops"),
    ("PUT", "/routes/99999/status", {"route_status": "ACTIVE"}, "ops"),
    ("GET", "/orders/99999/summary", None, "ops"),
    ("GET", "/orders/99999/financial-summary", None, "ops"),
    ("GET", "/customers/99999", None, "ops"),
    ("GET", "/customers/99999/order-history", None, "ops"),
]


@pytest.mark.parametrize("method, path, body, who", MISSING)
def test_missing_records_return_404(client, ops, admin, method, path, body, who):
    response = client.request(method, path, json=body, headers={"ops": ops, "admin": admin}[who])
    assert response.status_code == 404, response.text
    assert "not found" in response.json()["detail"].lower()


# --- Database errors become 4xx, not 500 -----------------------------------------

def test_constraint_violations_are_client_errors(client, db, make, shop, ops):
    order = make.legacy_order(shop["customer"], shop["product"])

    first = client.post("/payments", json={"order_id": order.order_id, "amount": 100, "payment_method": "UPI"}, headers=ops)
    assert first.status_code == 200
    duplicate = client.post("/payments", json={"order_id": order.order_id, "amount": 100, "payment_method": "UPI"}, headers=ops)
    assert duplicate.status_code == 409 and "already exists" in duplicate.json()["detail"]

    stock = {"warehouse_id": shop["warehouse"].warehouse_id, "product_id": shop["product"].product_id, "quantity": 1}
    assert client.post("/inventory", json=stock, headers=ops).status_code == 409  # pair already stocked
    assert client.post("/inventory", json={**stock, "warehouse_id": 99999}, headers=ops).status_code == 422

    assert client.put(f"/orders/{order.order_id}/status", json={"order_status": "TELEPORTED"}, headers=ops).status_code == 422
    assert client.post("/vehicles", json={"registration_no": "X-1", "vehicle_type": "VAN", "capacity": -5}, headers=ops).status_code == 422
    assert client.post("/routes", json={"route_name": "A-B", "source": "A", "destination": "B", "distance_km": 5, "estimated_duration": "banana"}, headers=ops).status_code == 422

    detail = client.put(f"/orders/{order.order_id}/status", json={"order_status": "TELEPORTED"}, headers=ops).json()["detail"]
    assert "chk_order_status" in detail and "SELECT" not in detail  # names the rule, leaks no SQL


# --- Drivers only see what they deliver -----------------------------------------

def test_driver_access_is_limited_to_assigned_orders_and_shipments(client, db, make, shop):
    order_id = checkout(client, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]
    fulfilment = pay(client, shop["headers"], order_id).json()["fulfilment"]
    shipment_id, assigned = fulfilment["shipment_id"], fulfilment["driver_id"]
    assert assigned == shop["driver"].employee_id

    _, _, other = make.driver()
    # The shop fixture keeps only the driver row, so rebuild that driver's token from their user.
    from jwt_utils import create_access_token
    from models import Employee
    employee = db.query(Employee).filter_by(employee_id=assigned).one()
    user = db.get(User, employee.user_id)
    mine = {"Authorization": "Bearer " + create_access_token({"user_id": user.user_id, "username": user.username, "role_id": user.role_id})}

    assert client.get(f"/orders/{order_id}", headers=mine).status_code == 200
    assert client.get(f"/orders/{order_id}", headers=other).status_code == 403
    assert client.get(f"/shipments/{shipment_id}/tracking-details", headers=mine).status_code == 200
    assert client.get(f"/shipments/{shipment_id}/tracking-details", headers=other).status_code == 403

    assert [s["shipment_id"] for s in client.get("/shipments/search", headers=mine).json()] == [shipment_id]
    assert client.get("/shipments/search", headers=other).json() == []
    assert [s["shipment_id"] for s in client.get("/shipments/search", params={"status": "created"}, headers=mine).json()] == [shipment_id]


# --- Values the database used to leave NULL ---------------------------------------

def test_server_defaults_fill_timestamps_and_route_duration_is_text(client, db, make, shop, ops):
    registered = client.post("/auth/register", json={
        "name": "New Customer", "username": "new.customer", "email": "new@example.test",
        "phone": "9876543210", "address": "1 Test Road, Chennai", "password": "Example-Pass-123",
    })
    assert registered.status_code == 201
    user = db.query(User).filter_by(username="new.customer").one()
    assert user.created_at is not None

    order = make.legacy_order(shop["customer"], shop["product"])
    assert pay_only(client, shop["headers"], order.order_id).status_code == 200
    created = client.post("/shipments", json={"order_id": order.order_id, "warehouse_id": shop["warehouse"].warehouse_id, "route_id": shop["route"].route_id}, headers=ops)
    assert created.status_code == 200
    db.expire_all()
    assert db.get(Shipment, created.json()["shipment_id"]).shipment_date is not None

    route = client.post("/routes", json={"route_name": "A-B", "source": "A", "destination": "B", "distance_km": 5, "estimated_duration": "8 hours"}, headers=ops)
    assert route.json()["estimated_duration"] == "8:00:00"
    listed = {r["route_id"]: r for r in client.get("/routes", headers=ops).json()}
    assert listed[route.json()["route_id"]]["estimated_duration"] == "8:00:00"


# --- Migration 004: a shipment item belongs to its shipment's order -----------------

def test_shipment_item_must_match_the_shipments_order(client, db, make, shop):
    other_product = make.product()
    make.stock(shop["warehouse"], other_product, 5)
    first = checkout(client, shop["headers"], [(shop["product"], 1)]).json()["order"]["order_id"]
    second = checkout(client, shop["headers"], [(other_product, 1)]).json()["order"]["order_id"]
    shipment_id = pay(client, shop["headers"], first).json()["fulfilment"]["shipment_id"]
    db.rollback()

    # (second, other_product) is a real order line, so only the shipment/order pairing is wrong.
    insert = text("INSERT INTO shipment_item (shipment_id, order_id, product_id, quantity) VALUES (:s, :o, :p, 1)")
    with engine.connect() as conn:
        with pytest.raises(Exception) as error:
            conn.execute(insert, {"s": shipment_id, "o": second, "p": other_product.product_id})
        assert "fk_shipment_item_shipment_order" in str(error.value)
        conn.rollback()


# --- set_demo_passwords.py -------------------------------------------------------------

def test_set_demo_passwords_replaces_only_placeholders(client, db, make):
    placeholder_user, _ = make.user("CUSTOMER")  # factory stores a non-hash placeholder
    real_user, _ = make.user("CUSTOMER")
    from auth import hash_password
    real = hash_password("Original-Pass-1")
    db.query(User).filter_by(user_id=real_user.user_id).update({"password_hash": real})
    db.commit()
    assert is_placeholder(placeholder_user.password_hash) and not is_placeholder(real)

    with pytest.raises(ValueError):
        set_demo_passwords("short")
    updated = set_demo_passwords("Example-Pass-123")
    assert updated == [placeholder_user.username]

    db.expire_all()
    assert db.get(User, real_user.user_id).password_hash == real
    login = client.post("/auth/login", json={"username": placeholder_user.username, "password": "Example-Pass-123"})
    assert login.status_code == 200

    assert set_demo_passwords("Another-Pass-9", include_real_hashes=True)  # --all overwrites everyone
    assert client.post("/auth/login", json={"username": real_user.username, "password": "Another-Pass-9"}).status_code == 200
