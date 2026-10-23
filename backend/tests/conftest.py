"""Integration-test fixtures backed by a disposable PostgreSQL database.

The tests never touch the development database. They create (and recreate)
a database named ``logitrack_test`` on the server from backend/.env, or use
TEST_DATABASE_URL when set. The schema is loaded from database/schema.sql
followed by every file in database/migrations, so the tests exercise the real
constraints, functions and triggers.
"""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

_env = dotenv_values(BACKEND_DIR / ".env")
_base_url = os.getenv("TEST_DATABASE_URL") or _env.get("DATABASE_URL")
if not _base_url:
    raise RuntimeError("Set TEST_DATABASE_URL or DATABASE_URL in backend/.env to run tests")

TEST_DB_URL = make_url(_base_url)
if not os.getenv("TEST_DATABASE_URL"):
    TEST_DB_URL = TEST_DB_URL.set(database="logitrack_test")
if not TEST_DB_URL.database.endswith("_test"):
    raise RuntimeError("Refusing to run: the test database name must end with '_test'")

# Must be set before database.py is imported (load_dotenv does not override).
os.environ["DATABASE_URL"] = TEST_DB_URL.render_as_string(hide_password=False)
os.environ.setdefault("JWT_SECRET_KEY", _env.get("JWT_SECRET_KEY") or "test-secret-key-for-integration-tests-only")


def _load_sql(path: Path) -> str:
    # pg_dump emits psql meta-commands (\restrict); they are not SQL.
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.startswith("\\"))


def _create_test_database():
    admin = create_engine(
        TEST_DB_URL.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_URL.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB_URL.database}"'))
    admin.dispose()

    loader = create_engine(TEST_DB_URL, isolation_level="AUTOCOMMIT")
    raw = loader.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute(_load_sql(REPO_DIR / "database" / "schema.sql"))
        cursor.execute("SELECT pg_catalog.set_config('search_path', 'public', false)")
        for migration in sorted((REPO_DIR / "database" / "migrations").glob("*.sql")):
            cursor.execute(_load_sql(migration))
        cursor.close()
    finally:
        raw.close()
    loader.dispose()


_create_test_database()

from database import SessionLocal, engine  # noqa: E402
from jwt_utils import create_access_token  # noqa: E402
from main import app  # noqa: E402
from models import (  # noqa: E402
    Customer, Driver, DriverVehicleAssignment, Employee, Inventory, Invoice,
    Order, OrderItem, Product, Role, Route, User, Vehicle, Warehouse,
)

ROLES = ["ADMIN", "OPERATIONS_MANAGER", "DRIVER", "CUSTOMER", "WAREHOUSE_MANAGER"]


@pytest.fixture(autouse=True)
def clean_database():
    with engine.begin() as conn:
        tables = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )).scalars().all()
        conn.execute(text(
            "TRUNCATE " + ", ".join(f'public."{t}"' for t in tables) + " RESTART IDENTITY CASCADE"
        ))
        for role_name in ROLES:
            conn.execute(text("INSERT INTO role (role_name) VALUES (:n)"), {"n": role_name})
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


class Factory:
    """Small builders for the rows each test needs, committed immediately."""

    def __init__(self):
        self._counter = 0

    def _next(self):
        self._counter += 1
        return self._counter

    def _save(self, *rows):
        with SessionLocal() as session:
            for row in rows:
                session.add(row)
                session.flush()
            session.commit()
            for row in rows:
                session.refresh(row)
                session.expunge(row)
        return rows[0] if len(rows) == 1 else rows

    def user(self, role_name: str):
        n = self._next()
        with SessionLocal() as session:
            role_id = session.query(Role.role_id).filter(Role.role_name == role_name).scalar()
        user = self._save(User(
            role_id=role_id,
            username=f"{role_name.lower()}_{n}",
            email=f"{role_name.lower()}_{n}@example.test",
            password_hash="not-used-in-tests",
        ))
        token = create_access_token({
            "user_id": user.user_id, "username": user.username, "role_id": role_id,
        })
        return user, {"Authorization": f"Bearer {token}"}

    def customer(self):
        user, headers = self.user("CUSTOMER")
        customer = self._save(Customer(user_id=user.user_id, name=f"Customer {user.user_id}"))
        return customer, headers

    def warehouse(self, city: str, status: str | None = None, capacity=None):
        extra = {"status": status} if status else {}
        return self._save(Warehouse(
            warehouse_name=f"{city} Warehouse {self._next()}", address="1 Test Road", city=city,
            capacity=capacity, **extra,
        ))

    def product(self, price=100, weight=None):
        return self._save(Product(product_name=f"Product {self._next()}", unit_price=price, weight=weight))

    def stock(self, warehouse, product, quantity):
        return self._save(Inventory(
            warehouse_id=warehouse.warehouse_id, product_id=product.product_id, quantity=quantity,
        ))

    def route(self, source: str, destination: str, status="ACTIVE"):
        return self._save(Route(
            route_name=f"{source}-{destination}", source=source, destination=destination,
            distance_km=100, estimated_duration=timedelta(hours=4), route_status=status,
        ))

    def vehicle(self, status="ACTIVE", capacity=1000):
        n = self._next()
        return self._save(Vehicle(
            registration_no=f"TN-TEST-{n}", vehicle_type="VAN", capacity=capacity, status=status,
        ))

    def driver(
        self, availability="AVAILABLE", employment="ACTIVE", license_expiry=None,
        vehicle_status="ACTIVE", with_vehicle=True, vehicle=None, vehicle_capacity=1000,
    ):
        user, headers = self.user("DRIVER")
        employee = self._save(Employee(
            user_id=user.user_id, name=f"Driver {user.user_id}", employment_status=employment,
        ))
        driver = self._save(Driver(
            employee_id=employee.employee_id,
            license_no=f"LIC-{employee.employee_id}",
            license_expiry=license_expiry or date.today() + timedelta(days=365),
            availability_status=availability,
        ))
        if with_vehicle:
            vehicle = vehicle or self.vehicle(vehicle_status, vehicle_capacity)
            self._save(DriverVehicleAssignment(
                driver_id=driver.employee_id, vehicle_id=vehicle.vehicle_id,
                assigned_from=date.today() - timedelta(days=30),
            ))
        return driver, vehicle, headers

    def legacy_order(self, customer, product, quantity=1, address="12 Old Street, Chennai"):
        """An order shaped like pre-Phase-3B data: items and invoice, no reservations."""
        order = self._save(Order(
            customer_id=customer.customer_id, order_status="PENDING", shipping_address=address,
        ))
        self._save(OrderItem(
            order_id=order.order_id, product_id=product.product_id,
            quantity=quantity, unit_price=product.unit_price,
        ))
        total = product.unit_price * quantity
        self._save(Invoice(
            order_id=order.order_id, subtotal=total, tax=0, total_amount=total,
            invoice_status="ISSUED",
        ))
        return order


@pytest.fixture
def make():
    return Factory()
