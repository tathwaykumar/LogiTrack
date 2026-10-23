"""Development demo data: a small fleet of drivers and vehicles, and stock in every warehouse.

    python seed_demo_data.py --dry-run     # show what would be added, change nothing
    python seed_demo_data.py               # add what is missing (prompts for the demo drivers' password)

For non-interactive use set LOGITRACK_DEMO_PASSWORD instead of typing the password.

Safe to run repeatedly. It only ever INSERTS rows that are missing, keyed by deterministic identifiers
(usernames demo_driver01..., registrations DEMO-FLT-001..., one inventory row per warehouse/product pair).
It never updates or deletes an existing row, so existing stock quantities, drivers, vehicles, shipments and
passwords are left exactly as they are. Every row it adds is listed in demo_seed_record (migration 006).

Refuses to run when LOGITRACK_ENV or APP_ENV is 'production'. Passwords are hashed with the application's own
helper; nothing secret is stored in this file.

Not modelled by the schema, so not invented here: driver/vehicle-to-warehouse links, SKUs, stock movements,
GPS positions, certifications.
"""
import argparse
import getpass
import os
import sys
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import hash_password
from database import SessionLocal
from models import (
    DemoSeedRecord, Driver, DriverVehicleAssignment, Employee, Inventory, Product, Role, User, Vehicle, Warehouse,
)

MIN_PASSWORD_LENGTH = 8
MIN_PRODUCTS_PER_WAREHOUSE = 6
DEMO_REORDER_LEVEL = 10
DEMO_EMAIL_DOMAIN = "demo.logitrack.example"   # reserved example domain: never a real mailbox

# (display name, vehicle type, capacity kg, fuel). Fictional people and plates; capacities are plausible
# payloads for the vehicle type, not measurements of anything real.
DEMO_FLEET = [
    ("Arjun Menon", "Mini Truck", 1500, "Diesel"),
    ("Divya Nair", "Delivery Van", 1000, "Diesel"),
    ("Rahul Verma", "Heavy Truck", 5000, "Diesel"),
    ("Sneha Iyer", "Electric Van", 800, "Electric"),
    ("Karan Malhotra", "Delivery Van", 1200, "Petrol"),
    ("Meera Pillai", "Mini Truck", 1500, "Diesel"),
    ("Imran Sheikh", "Pickup Truck", 1100, "Diesel"),
    ("Lakshmi Narayan", "Electric Van", 900, "Electric"),
    ("Vivek Reddy", "Delivery Van", 1000, "Petrol"),
    ("Anita Joseph", "Mini Truck", 1400, "Diesel"),
]
LICENCE_EXPIRY = date(2030, 12, 31)
HIRE_DATE = date(2025, 1, 15)
PURCHASE_DATE = date(2025, 1, 10)
ASSIGNED_FROM = date(2026, 1, 1)


def refuse_in_production():
    env = (os.getenv("LOGITRACK_ENV") or os.getenv("APP_ENV") or "").strip().lower()
    if env in ("prod", "production"):
        sys.exit("Refusing to add demo data: LOGITRACK_ENV/APP_ENV says production.")


def _record(db: Session, entity: str, key: str):
    db.add(DemoSeedRecord(entity=entity, entity_key=key))


def seed_fleet(db: Session, password_hash: str | None, dry_run: bool = False) -> dict:
    """Add the demo drivers and vehicles that do not exist yet. Returns counts of what was added/present."""
    role = db.query(Role).filter(Role.role_name == "DRIVER").first()
    if role is None:
        raise RuntimeError("The DRIVER role does not exist; load the base schema and seed data first.")
    report = {"drivers_created": 0, "drivers_present": 0, "vehicles_created": 0, "vehicles_present": 0,
              "assignments_created": 0, "assignments_present": 0}

    for index, (name, vehicle_type, capacity, fuel) in enumerate(DEMO_FLEET, start=1):
        username = f"demo_driver{index:02d}"
        registration = f"DEMO-FLT-{index:03d}"

        user = db.query(User).filter(User.username == username).first()
        if user is None:
            report["drivers_created"] += 1
            if dry_run:
                user = None
            else:
                user = User(role_id=role.role_id, username=username, email=f"{username}@{DEMO_EMAIL_DOMAIN}",
                            password_hash=password_hash, is_active=True)
                db.add(user)
                db.flush()
                _record(db, "user", username)
        else:
            report["drivers_present"] += 1

        employee = driver = None
        if user is not None and user.user_id is not None:
            employee = db.query(Employee).filter(Employee.user_id == user.user_id).first()
            if employee is None:
                employee = Employee(user_id=user.user_id, name=f"{name} (Demo)", phone=f"+91-00000-{index:05d}",
                                    department="Logistics", hire_date=HIRE_DATE, employment_status="ACTIVE")
                db.add(employee)
                db.flush()
                _record(db, "employee", username)
            driver = db.query(Driver).filter(Driver.employee_id == employee.employee_id).first()
            if driver is None:
                driver = Driver(employee_id=employee.employee_id, license_no=f"DEMO-DL-{index:04d}",
                                license_expiry=LICENCE_EXPIRY, availability_status="AVAILABLE")
                db.add(driver)
                db.flush()
                _record(db, "driver", username)

        vehicle = db.query(Vehicle).filter(Vehicle.registration_no == registration).first()
        if vehicle is None:
            report["vehicles_created"] += 1
            if not dry_run:
                vehicle = Vehicle(registration_no=registration, vehicle_type=vehicle_type, capacity=capacity,
                                  fuel_type=fuel, status="ACTIVE", purchase_date=PURCHASE_DATE)
                db.add(vehicle)
                db.flush()
                _record(db, "vehicle", registration)
        else:
            report["vehicles_present"] += 1

        if driver is not None and vehicle is not None:
            current = db.query(DriverVehicleAssignment).filter(
                DriverVehicleAssignment.driver_id == driver.employee_id,
                DriverVehicleAssignment.vehicle_id == vehicle.vehicle_id,
                DriverVehicleAssignment.assigned_to.is_(None),
            ).first()
            if current is None:
                db.add(DriverVehicleAssignment(driver_id=driver.employee_id, vehicle_id=vehicle.vehicle_id,
                                               assigned_from=ASSIGNED_FROM))
                db.flush()
                _record(db, "assignment", f"{username}:{registration}")
                report["assignments_created"] += 1
            else:
                report["assignments_present"] += 1
        elif dry_run and (user is None or vehicle is None):
            report["assignments_created"] += 1
    return report


def _demo_quantity(warehouse_id: int, product_id: int) -> int:
    """Deterministic, modest, always positive: 20-79 units."""
    return 20 + (warehouse_id * 7 + product_id * 13) % 60


def seed_inventory(db: Session, dry_run: bool = False) -> dict:
    """Make sure every warehouse stocks at least MIN_PRODUCTS_PER_WAREHOUSE catalogue products.

    Only (warehouse, product) pairs with no inventory row yet are inserted; existing rows are never touched.
    Products are the existing catalogue (none are created). Which products a warehouse gets is rotated by
    warehouse so the sites differ.
    """
    products = [p.product_id for p in db.query(Product).order_by(Product.product_id)]
    report = {"warehouses": 0, "products": len(products), "inventory_rows_created": 0, "inventory_rows_present": 0,
              "per_warehouse_added": {}}
    if not products:
        return report
    for warehouse in db.query(Warehouse).order_by(Warehouse.warehouse_id):
        report["warehouses"] += 1
        stocked = {row.product_id for row in db.query(Inventory).filter(Inventory.warehouse_id == warehouse.warehouse_id)}
        report["inventory_rows_present"] += len(stocked)
        needed = max(0, min(MIN_PRODUCTS_PER_WAREHOUSE, len(products)) - len(stocked))
        offset = (warehouse.warehouse_id * 3) % len(products)
        rotated = products[offset:] + products[:offset]
        added = 0
        for product_id in rotated:
            if added >= needed:
                break
            if product_id in stocked:
                continue
            added += 1
            if not dry_run:
                db.add(Inventory(warehouse_id=warehouse.warehouse_id, product_id=product_id,
                                 quantity=_demo_quantity(warehouse.warehouse_id, product_id),
                                 reorder_level=DEMO_REORDER_LEVEL))
                db.flush()
                _record(db, "inventory", f"{warehouse.warehouse_id}:{product_id}")
        report["inventory_rows_created"] += added
        report["per_warehouse_added"][warehouse.warehouse_id] = added
    return report


def totals(db: Session) -> dict:
    def n(model, *criteria):
        return db.query(func.count()).select_from(model).filter(*criteria).scalar()
    return {
        "warehouses": n(Warehouse), "products": n(Product), "inventory_rows": n(Inventory),
        "drivers": n(Driver), "drivers_available": n(Driver, Driver.availability_status == "AVAILABLE"),
        "vehicles": n(Vehicle), "vehicles_active": n(Vehicle, Vehicle.status == "ACTIVE"),
    }


def seed(db: Session, password: str | None, dry_run: bool = False) -> dict:
    """Run both seeds in one transaction (rolled back on any error, and on dry run)."""
    if not dry_run:
        if not password or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"The demo password must be at least {MIN_PASSWORD_LENGTH} characters.")
    try:
        fleet = seed_fleet(db, hash_password(password) if (password and not dry_run) else None, dry_run)
        stock = seed_inventory(db, dry_run)
        result = {"fleet": fleet, "inventory": stock, "totals_after": totals(db), "dry_run": dry_run}
        if dry_run:
            db.rollback()
        else:
            db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def read_password() -> str:
    from_env = os.getenv("LOGITRACK_DEMO_PASSWORD")
    if from_env:
        return from_env
    first = getpass.getpass("Password for the new demo driver accounts: ")
    if first != getpass.getpass("Repeat password: "):
        sys.exit("The passwords do not match. Nothing was changed.")
    return first


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="report what would be added; change nothing")
    args = parser.parse_args()
    refuse_in_production()
    session = SessionLocal()
    try:
        outcome = seed(session, None if args.dry_run else read_password(), args.dry_run)
    except ValueError as error:
        sys.exit(str(error))
    finally:
        session.close()
    label = "Would add" if outcome["dry_run"] else "Added"
    fleet, stock = outcome["fleet"], outcome["inventory"]
    print(f"{label}: {fleet['drivers_created']} driver(s), {fleet['vehicles_created']} vehicle(s), "
          f"{fleet['assignments_created']} driver-vehicle assignment(s), {stock['inventory_rows_created']} inventory row(s).")
    print(f"Already present: {fleet['drivers_present']} demo driver(s), {fleet['vehicles_present']} demo vehicle(s), "
          f"{stock['inventory_rows_present']} inventory row(s) (left untouched).")
    print("Per-warehouse inventory rows added:", stock["per_warehouse_added"])
    print("Totals after:" if not outcome["dry_run"] else "Totals (unchanged, dry run):", outcome["totals_after"])
