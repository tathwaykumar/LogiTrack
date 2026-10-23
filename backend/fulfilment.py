"""Order fulfilment: stock allocation, planning, driver/vehicle assignment and stock release.

The functions here work on a SQLAlchemy session and never commit; the calling endpoint owns the
transaction. Callers hold a row lock on the order before changing it (that serialises retries and
concurrent requests for one order), and driver/vehicle allocation additionally takes a transaction-level
advisory lock so two concurrent orders can never be given the same capacity.

Nothing is fabricated: when stock, a route, a warehouse, a driver or a vehicle is missing, the reason is
recorded on the order's fulfilment plan and the order stays pending.
"""
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from models import (
    Delivery, Driver, DriverVehicleAssignment, Employee, Inventory, Invoice, Order, OrderFulfilment,
    OrderFulfilmentEvent, OrderInventoryReservation, OrderItem, Payment, Product, Route, Shipment,
    ShipmentItem, ShipmentTracking, User, Vehicle, Warehouse,
)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


# Configuration (see docs/SETUP.md). Read at call time so tests can change them.
MAX_OPEN_DELIVERIES_PER_DRIVER = _int_env("MAX_OPEN_DELIVERIES_PER_DRIVER", 3)
UNPAID_ORDER_TTL_MINUTES = _int_env("UNPAID_ORDER_TTL_MINUTES", 1440)

DRIVER_AVAILABLE_STATUS = "AVAILABLE"
# Vehicle status has no CHECK constraint: seed data uses ACTIVE and the vehicle screen uses AVAILABLE
# for the same "in service" meaning.
ELIGIBLE_VEHICLE_STATUSES = ("ACTIVE", "AVAILABLE")
# Deliveries that still occupy a driver and a vehicle (a failed attempt is retried by the same driver).
LOAD_DELIVERY_STATUSES = ("PENDING", "OUT_FOR_DELIVERY", "FAILED")
ACTIVE_WAREHOUSE_STATUS = "ACTIVE"
ADVISORY_LOCK_KEY = 7340001  # one global lock for driver/vehicle allocation

# Why a driver/vehicle pair is not eligible.
PAIR_REASONS = {
    "DRIVER_NOT_AVAILABLE": "driver is not marked AVAILABLE",
    "LICENCE_EXPIRED": "driver's licence has expired",
    "EMPLOYEE_INACTIVE": "driver's employee record is not ACTIVE",
    "USER_INACTIVE": "driver's login is deactivated",
    "NO_CURRENT_VEHICLE": "driver has no current vehicle assignment",
    "VEHICLE_NOT_IN_SERVICE": "vehicle is not in service",
    "VEHICLE_SHARED": "vehicle is currently assigned to more than one driver",
    "DRIVER_AT_LIMIT": "driver already has the maximum number of open deliveries",
    "VEHICLE_CAPACITY": "vehicle does not have enough free capacity for this shipment",
}

BLOCK_TO_RESULT = {
    "RESERVATION_MISSING": "RESERVATION_MISSING",
    "RESERVATION_INCOMPLETE": "RESERVATION_INCOMPLETE",
    "WAREHOUSE_INACTIVE": "WAREHOUSE_UNAVAILABLE",
}


# ---------------------------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------------------------
def log_event(db: Session, order_id: int, event_type: str, detail: str | None = None,
              shipment_id: int | None = None, actor_user_id: int | None = None):
    event = OrderFulfilmentEvent(
        order_id=order_id,
        shipment_id=shipment_id,
        event_type=event_type,
        detail=(detail or "")[:500] or None,
        actor_user_id=actor_user_id,
        created_at=datetime.now(),
    )
    db.add(event)
    return event


# ---------------------------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------------------------
def normalise_place(value: str) -> str:
    """Lower-case, turn punctuation into spaces, drop trailing PIN/postal digits."""
    words = re.sub(r"[^\w\s]|_", " ", (value or "").lower()).split()
    while words and words[-1].isdigit():
        words.pop()
    return " ".join(words)


def address_mentions_city(shipping_address: str, city: str) -> bool:
    """True when a comma/line-separated address part ends with the city name.

    Matching whole trailing words means "Flat 3, Chennai - 600040" and "VIT University Vellore" name
    their city, while a street such as "12 Bangalore Road" does not name Bangalore. Only used for orders
    that carry no destination city (older orders).
    """
    target = normalise_place(city)
    if not target:
        return False
    for part in re.split(r"[,;\n]", shipping_address or ""):
        segment = normalise_place(part)
        if segment == target or segment.endswith(" " + target):
            return True
    return False


@dataclass
class RouteResult:
    route: Route | None
    basis: str
    code: str | None = None
    detail: str | None = None


def find_route(db: Session, origin_city: str, destination_city: str | None, shipping_address: str) -> RouteResult:
    """The single active route from origin_city to the order's destination, or why there is none.

    With a destination city (chosen at checkout) the match is an exact comparison of normalised city
    names. Without one (older orders) it falls back to reading the city from the address, and the result
    says so. Never falls back to an unrelated route.
    """
    routes = (
        db.query(Route)
        .filter(
            func.lower(func.trim(Route.source)) == (origin_city or "").strip().lower(),
            Route.route_status == "ACTIVE",
        )
        .order_by(Route.route_id)
        .all()
    )
    has_destination = bool(destination_city and destination_city.strip())
    basis = "DESTINATION_CITY" if has_destination else "ADDRESS_TEXT"
    target_label = destination_city.strip() if has_destination else "the city named in the shipping address"

    if has_destination:
        target = normalise_place(destination_city)
        matches = [r for r in routes if normalise_place(r.destination) == target]
    else:
        matches = [r for r in routes if address_mentions_city(shipping_address, r.destination)]

    if len(matches) == 1:
        return RouteResult(matches[0], basis)
    if not matches:
        detail = (
            f"No active route is configured from {origin_city} to {target_label}."
            if routes else f"No active route leaves {origin_city}."
        )
        return RouteResult(None, basis, "NO_ROUTE", detail)
    return RouteResult(None, basis, "AMBIGUOUS_ROUTE",
                       f"{len(matches)} active routes match {origin_city} to {target_label}; "
                       "an operator must create the shipment with the intended route.")


def select_route(db: Session, origin_city: str, shipping_address: str, destination_city: str | None = None):
    return find_route(db, origin_city, destination_city, shipping_address).route


# ---------------------------------------------------------------------------------------------
# Stock allocation (checkout)
# ---------------------------------------------------------------------------------------------
@dataclass
class AllocationPlan:
    allocations: dict          # product_id -> [(Inventory row, quantity)]
    strategy: str              # SINGLE_WAREHOUSE | MULTI_WAREHOUSE
    origin_warehouse_id: int
    note: str
    products: dict = field(default_factory=dict)


def allocate_stock(db: Session, requested: dict[int, int]) -> AllocationPlan:
    """Lock the needed stock and choose where it comes from.

    Only ACTIVE warehouses are used, and only their real stock decides: routes play no part. If one
    warehouse holds every item, the order is served from it (the lowest id when several could). Otherwise
    stock is taken from several warehouses in id order, the shipment originates at the warehouse supplying
    the most units, and the note says that moving stock between warehouses is not modelled. Raises
    HTTPException (404 unknown product, 409 insufficient stock).
    """
    products: dict[int, Product] = {}
    rows: dict[int, list[Inventory]] = {}
    for product_id in sorted(requested):
        product = db.query(Product).filter(Product.product_id == product_id).with_for_update().first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {product_id} was not found")
        inventory_rows = (
            db.query(Inventory)
            .join(Warehouse, Warehouse.warehouse_id == Inventory.warehouse_id)
            .filter(
                Inventory.product_id == product_id,
                Inventory.quantity > 0,
                Warehouse.status == ACTIVE_WAREHOUSE_STATUS,
            )
            .order_by(Inventory.warehouse_id)
            .with_for_update(of=Inventory)
            .all()
        )
        available = sum(row.quantity for row in inventory_rows)
        if available < requested[product_id]:
            raise HTTPException(
                status_code=409,
                detail=f"Insufficient stock for {product.product_name}. Only {available} available.",
            )
        products[product_id] = product
        rows[product_id] = inventory_rows

    warehouses = {w.warehouse_id: w for w in db.query(Warehouse).all()}

    # Warehouses that alone can supply every item.
    candidates = None
    for product_id, inventory_rows in rows.items():
        ids = {r.warehouse_id for r in inventory_rows if r.quantity >= requested[product_id]}
        candidates = ids if candidates is None else candidates & ids
    candidates = sorted(candidates or [])

    if candidates:
        chosen = candidates[0]
        warehouse = warehouses[chosen]
        note = f"{warehouse.warehouse_name} ({warehouse.city}) holds every item in this order."
        if len(candidates) > 1:
            note += f" {len(candidates) - 1} other warehouse(s) could also serve it; the lowest-numbered was chosen."
        allocations = {
            product_id: [(next(r for r in inventory_rows if r.warehouse_id == chosen), requested[product_id])]
            for product_id, inventory_rows in rows.items()
        }
        return AllocationPlan(allocations, "SINGLE_WAREHOUSE", chosen, note, products)

    allocations: dict[int, list] = {}
    units_by_warehouse: dict[int, int] = {}
    for product_id, inventory_rows in rows.items():
        remaining = requested[product_id]
        allocations[product_id] = []
        for row in inventory_rows:
            amount = min(row.quantity, remaining)
            if amount:
                allocations[product_id].append((row, amount))
                units_by_warehouse[row.warehouse_id] = units_by_warehouse.get(row.warehouse_id, 0) + amount
                remaining -= amount
            if remaining == 0:
                break
    origin = min(units_by_warehouse, key=lambda wid: (-units_by_warehouse[wid], wid))
    parts = ", ".join(
        f"{warehouses[wid].warehouse_name} ({units_by_warehouse[wid]} units)" for wid in sorted(units_by_warehouse)
    )
    note = (f"No single active warehouse holds every item, so stock is taken from {len(units_by_warehouse)} "
            f"warehouses: {parts}. The shipment originates at {warehouses[origin].warehouse_name}, which supplies "
            "the most units. Transfers between warehouses are not modelled, so items from the other "
            "warehouses are not moved to the origin.")
    return AllocationPlan(allocations, "MULTI_WAREHOUSE", origin, note, products)


# ---------------------------------------------------------------------------------------------
# Weights and fleet evaluation
# ---------------------------------------------------------------------------------------------
def order_weight(db: Session, order_id: int) -> tuple[Decimal | None, int]:
    """Total kg of an order and how many lines have no product weight.

    The total is None when any line has no weight, because a capacity check on a partial sum would
    be misleading.
    """
    total = Decimal(0)
    unknown = 0
    for quantity, weight in (
        db.query(OrderItem.quantity, Product.weight)
        .join(Product, Product.product_id == OrderItem.product_id)
        .filter(OrderItem.order_id == order_id)
    ):
        if weight is None:
            unknown += 1
        else:
            total += Decimal(quantity) * weight
    return (None if unknown else total), unknown


@dataclass
class PairEvaluation:
    driver_id: int
    driver_name: str
    vehicle_id: int | None
    registration_no: str | None
    vehicle_type: str | None
    eligible: bool
    reason_codes: list[str]
    open_deliveries: int
    remaining_capacity: float | None

    @property
    def reasons(self) -> list[str]:
        return [PAIR_REASONS[code] for code in self.reason_codes]


def evaluate_fleet(db: Session, today: date, weight_kg: Decimal | None = None,
                   exclude_delivery_id: int | None = None) -> list[PairEvaluation]:
    """Evaluate every (driver, current vehicle) pair against the assignment rules.

    A driver with no current vehicle appears once with NO_CURRENT_VEHICLE. weight_kg=None skips the
    vehicle-capacity check (weight unknown). exclude_delivery_id ignores one delivery's load, so a
    shipment being reassigned does not count against its own current driver and vehicle.
    """
    drivers = (
        db.query(Driver, Employee, User)
        .join(Employee, Employee.employee_id == Driver.employee_id)
        .outerjoin(User, User.user_id == Employee.user_id)
        .order_by(Driver.employee_id)
        .all()
    )
    vehicles = {v.vehicle_id: v for v in db.query(Vehicle).all()}
    assignments: dict[int, list[int]] = {}
    holders: dict[int, set[int]] = {}
    for a in db.query(DriverVehicleAssignment).filter(
        DriverVehicleAssignment.assigned_from <= today,
        (DriverVehicleAssignment.assigned_to.is_(None)) | (DriverVehicleAssignment.assigned_to >= today),
    ).order_by(DriverVehicleAssignment.assignment_id):
        assignments.setdefault(a.driver_id, [])
        if a.vehicle_id not in assignments[a.driver_id]:
            assignments[a.driver_id].append(a.vehicle_id)
        holders.setdefault(a.vehicle_id, set()).add(a.driver_id)

    open_by_driver = dict(
        db.query(Delivery.driver_id, func.count(Delivery.delivery_id))
        .filter(Delivery.delivery_status.in_(LOAD_DELIVERY_STATUSES),
                Delivery.delivery_id != (exclude_delivery_id or -1))
        .group_by(Delivery.driver_id).all()
    )
    load_by_vehicle = dict(
        db.query(Delivery.vehicle_id, func.coalesce(func.sum(ShipmentItem.quantity * func.coalesce(Product.weight, 0)), 0))
        .join(ShipmentItem, ShipmentItem.shipment_id == Delivery.shipment_id)
        .join(Product, Product.product_id == ShipmentItem.product_id)
        .filter(Delivery.vehicle_id.isnot(None), Delivery.delivery_status.in_(LOAD_DELIVERY_STATUSES),
                Delivery.delivery_id != (exclude_delivery_id or -1))
        .group_by(Delivery.vehicle_id).all()
    )

    results = []
    for driver, employee, user in drivers:
        base = []
        if driver.availability_status != DRIVER_AVAILABLE_STATUS:
            base.append("DRIVER_NOT_AVAILABLE")
        if driver.license_expiry is None or driver.license_expiry < today:
            base.append("LICENCE_EXPIRED")
        if employee.employment_status != "ACTIVE":
            base.append("EMPLOYEE_INACTIVE")
        if user is not None and user.is_active is False:
            base.append("USER_INACTIVE")
        open_count = int(open_by_driver.get(driver.employee_id, 0))
        if open_count >= MAX_OPEN_DELIVERIES_PER_DRIVER:
            base.append("DRIVER_AT_LIMIT")

        vehicle_ids = assignments.get(driver.employee_id) or [None]
        for vehicle_id in vehicle_ids:
            codes = list(base)
            vehicle = vehicles.get(vehicle_id) if vehicle_id else None
            remaining = None
            if vehicle is None:
                codes.append("NO_CURRENT_VEHICLE")
            else:
                if vehicle.status not in ELIGIBLE_VEHICLE_STATUSES:
                    codes.append("VEHICLE_NOT_IN_SERVICE")
                if len(holders.get(vehicle_id, ())) > 1:
                    codes.append("VEHICLE_SHARED")
                remaining = float(vehicle.capacity) - float(load_by_vehicle.get(vehicle_id, 0) or 0)
                if weight_kg is not None and remaining < float(weight_kg):
                    codes.append("VEHICLE_CAPACITY")
            results.append(PairEvaluation(
                driver_id=driver.employee_id, driver_name=employee.name, vehicle_id=vehicle_id,
                registration_no=vehicle.registration_no if vehicle else None,
                vehicle_type=vehicle.vehicle_type if vehicle else None,
                eligible=not codes, reason_codes=codes, open_deliveries=open_count, remaining_capacity=remaining,
            ))
    return results


def lock_allocation(db: Session):
    """Serialise driver/vehicle allocation across transactions (released at commit or rollback)."""
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY})


def find_eligible_driver(db: Session, today: date, weight_kg: Decimal | None = None):
    """Return (driver_id, vehicle_id) for the least-loaded eligible driver, or None.

    Takes the allocation lock, locks the chosen driver and vehicle rows, then re-evaluates so a
    concurrent change cannot slip in between choosing and recording the assignment.
    """
    lock_allocation(db)
    eligible = sorted(
        (e for e in evaluate_fleet(db, today, weight_kg) if e.eligible),
        key=lambda e: (e.open_deliveries, e.driver_id, e.vehicle_id),
    )
    for pair in eligible:
        db.query(Driver).filter(Driver.employee_id == pair.driver_id).with_for_update().first()
        db.query(Vehicle).filter(Vehicle.vehicle_id == pair.vehicle_id).with_for_update().first()
        for fresh in evaluate_fleet(db, today, weight_kg):
            if fresh.driver_id == pair.driver_id and fresh.vehicle_id == pair.vehicle_id and fresh.eligible:
                return pair.driver_id, pair.vehicle_id
    return None


def explain_no_assignment(db: Session, today: date, weight_kg: Decimal | None) -> str:
    """A human-readable reason why no driver and vehicle could be assigned."""
    evaluations = evaluate_fleet(db, today, weight_kg)
    if not evaluations:
        return "No drivers are registered."
    counts: dict[str, int] = {}
    for e in evaluations:
        for code in e.reason_codes:
            counts[code] = counts.get(code, 0) + 1
    parts = [f"{n} pair(s): {PAIR_REASONS[code]}" for code, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    return "No eligible driver and vehicle are available. " + "; ".join(parts) + "."


def assign_eligible_driver(db: Session, shipment: Shipment, delivery_address: str, *,
                           weight_kg: Decimal | None = None, actor_user_id: int | None = None):
    """Create the delivery for a shipment if an eligible driver and vehicle exist; never fabricate one."""
    candidate = find_eligible_driver(db, date.today(), weight_kg)
    if not candidate:
        return None
    driver_id, vehicle_id = candidate
    delivery = Delivery(
        shipment_id=shipment.shipment_id, driver_id=driver_id, vehicle_id=vehicle_id,
        delivery_address=delivery_address, delivery_status="PENDING", assigned_at=datetime.now(),
    )
    db.add(delivery)
    db.flush()
    log_event(db, shipment.order_id, "DRIVER_ASSIGNED",
              f"Driver {driver_id} and vehicle {vehicle_id} assigned automatically.",
              shipment.shipment_id, actor_user_id)
    return {"delivery_id": delivery.delivery_id, "driver_id": driver_id, "vehicle_id": vehicle_id}


def validate_manual_assignment(db: Session, driver_id: int, vehicle_id: int | None, weight_kg: Decimal | None,
                               exclude_delivery_id: int | None = None) -> PairEvaluation:
    """Check an operator's choice with the same rules as automatic assignment; 409/404 if it fails."""
    pairs = [e for e in evaluate_fleet(db, date.today(), weight_kg, exclude_delivery_id) if e.driver_id == driver_id]
    if not pairs:
        raise HTTPException(status_code=404, detail="Driver not found")
    if vehicle_id is None:
        if len(pairs) == 1:
            match = pairs[0]
        else:
            usable = [e for e in pairs if e.eligible]
            if len(usable) != 1:
                raise HTTPException(
                    status_code=422,
                    detail="Specify vehicle_id: this driver has several vehicle assignments"
                           + ("." if usable else ", none of which is eligible: " + "; ".join(sorted({r for e in pairs for r in e.reasons})) + "."),
                )
            match = usable[0]
        if not match.eligible:
            raise HTTPException(status_code=409, detail="This driver and vehicle cannot take the shipment: " + "; ".join(match.reasons) + ".")
        return match
    match = next((e for e in pairs if e.vehicle_id == vehicle_id), None)
    if match is None:
        raise HTTPException(status_code=409, detail="That vehicle is not currently assigned to this driver (driver_vehicle_assignment).")
    if not match.eligible:
        raise HTTPException(status_code=409, detail="This driver and vehicle cannot take the shipment: " + "; ".join(match.reasons) + ".")
    return match


# ---------------------------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------------------------
def active_reservations(db: Session, order_id: int):
    return (
        db.query(OrderInventoryReservation)
        .filter(OrderInventoryReservation.order_id == order_id, OrderInventoryReservation.released_at.is_(None))
        .order_by(OrderInventoryReservation.warehouse_id, OrderInventoryReservation.product_id)
        .all()
    )


def _set_plan(db: Session, order: Order, status: str, *, code=None, detail=None, origin=None, route=None,
              basis=None, note=None, actor_user_id=None, event_type=None):
    plan = db.query(OrderFulfilment).filter(OrderFulfilment.order_id == order.order_id).first()
    previous = None
    if plan is None:
        plan = OrderFulfilment(order_id=order.order_id, fulfilment_status=status, planned_at=datetime.now())
        db.add(plan)
    else:
        previous = (plan.fulfilment_status, plan.reason_code, plan.origin_warehouse_id, plan.route_id)
    plan.fulfilment_status = status
    plan.reason_code = code
    plan.reason_detail = (detail or "")[:500] or None
    plan.origin_warehouse_id = origin
    plan.route_id = route
    plan.route_basis = basis
    if note is not None:
        plan.selection_note = note[:1000]
    plan.updated_at = datetime.now()
    db.flush()
    if previous != (status, code, origin, route):
        log_event(db, order.order_id, event_type or ("BLOCKED" if status == "BLOCKED" else "PLANNED"),
                  detail or plan.selection_note, actor_user_id=actor_user_id)
    return plan


def plan_order(db: Session, order: Order, *, selection_note: str | None = None,
               actor_user_id: int | None = None) -> OrderFulfilment:
    """Work out (or re-work out) which warehouse an order ships from; record it (with its route, if one is configured).

    Idempotent: there is one plan row per order, updated in place. Does not touch drivers or vehicles
    (that happens at dispatch, after payment), but records whether any eligible pair exists right now.
    """
    ordered = {i.product_id: i.quantity for i in db.query(OrderItem).filter(OrderItem.order_id == order.order_id)}
    reservations = active_reservations(db, order.order_id)
    if not reservations:
        return _set_plan(db, order, "BLOCKED", code="RESERVATION_MISSING",
                         detail="No inventory reservation is recorded for this order, so there is no known source "
                                "warehouse. Operations follow-up is required.",
                         note=selection_note, actor_user_id=actor_user_id)

    reserved: dict[int, int] = {}
    units_by_warehouse: dict[int, int] = {}
    for r in reservations:
        reserved[r.product_id] = reserved.get(r.product_id, 0) + r.reserved_quantity
        units_by_warehouse[r.warehouse_id] = units_by_warehouse.get(r.warehouse_id, 0) + r.reserved_quantity
    if reserved != ordered:
        return _set_plan(db, order, "BLOCKED", code="RESERVATION_INCOMPLETE",
                         detail="Recorded inventory reservations do not match the order items.",
                         note=selection_note, actor_user_id=actor_user_id)

    origin_id = min(units_by_warehouse, key=lambda wid: (-units_by_warehouse[wid], wid))
    warehouse = db.query(Warehouse).filter(Warehouse.warehouse_id == origin_id).first()
    if warehouse.status != ACTIVE_WAREHOUSE_STATUS:
        return _set_plan(db, order, "BLOCKED", code="WAREHOUSE_INACTIVE",
                         detail=f"{warehouse.warehouse_name} is {warehouse.status}, so it cannot dispatch.",
                         origin=origin_id, note=selection_note, actor_user_id=actor_user_id)

    # A configured route is reference data, never a prerequisite: record it when exactly one active route
    # matches, otherwise leave it empty (no route, distance or ETA is made up).
    result = find_route(db, warehouse.city, order.destination_city, order.shipping_address)
    route_id = result.route.route_id if result.route is not None else None
    route_basis = result.basis if result.route is not None else None

    weight, _unknown = order_weight(db, order.order_id)
    code = detail = None
    if not any(e.eligible for e in evaluate_fleet(db, date.today(), weight)):
        code = "NO_ELIGIBLE_DRIVER"
        detail = ("No eligible driver and vehicle right now; allocation is checked again when the order is approved. "
                  + explain_no_assignment(db, date.today(), weight))
    return _set_plan(db, order, "PLANNED", code=code, detail=detail, origin=origin_id, route=route_id,
                     basis=route_basis, note=selection_note, actor_user_id=actor_user_id)


# ---------------------------------------------------------------------------------------------
# Dispatch (after successful payment)
# ---------------------------------------------------------------------------------------------
def unfulfilled(status: str, message: str, **extra):
    return {
        "status": status, "message": message, "shipment_id": None, "shipment_status": None,
        "origin_warehouse_id": None, "driver_id": None, "vehicle_id": None, **extra,
    }


def fulfilment_summary(db: Session, order: Order):
    """Describe the existing fulfilment state of an order without changing it."""
    shipment = (
        db.query(Shipment)
        .filter(Shipment.order_id == order.order_id, Shipment.shipment_status != "CANCELLED")
        .first()
    )
    plan = db.query(OrderFulfilment).filter(OrderFulfilment.order_id == order.order_id).first()
    if not shipment:
        return unfulfilled(
            "NOT_FULFILLED",
            (plan.reason_detail if plan and plan.reason_detail else
             "No shipment exists for this order yet. Operations follow-up is required."),
            reason_code=plan.reason_code if plan else None,
        )
    delivery = db.query(Delivery).filter(Delivery.shipment_id == shipment.shipment_id).first()
    return {
        "status": "DRIVER_ASSIGNED" if delivery else "PENDING_ASSIGNMENT",
        "message": ("Shipment created and driver assigned." if delivery
                    else "Shipment created and awaiting driver assignment."),
        "shipment_id": shipment.shipment_id,
        "shipment_status": shipment.shipment_status,
        "origin_warehouse_id": shipment.warehouse_id,
        "driver_id": delivery.driver_id if delivery else None,
        "vehicle_id": delivery.vehicle_id if delivery else None,
        "reason_code": plan.reason_code if plan else None,
    }


def is_paid(db: Session, order_id: int) -> bool:
    return db.query(Payment.payment_id).filter(
        Payment.order_id == order_id, Payment.payment_status == "SUCCESS").first() is not None


def awaiting_approval(message: str = "Payment received. The order is awaiting approval by operations."):
    """The result of a successful payment: nothing is dispatched until an Operations Manager approves."""
    return unfulfilled("AWAITING_APPROVAL", message)


def recover_missing_reservation(db: Session, order: Order, *, confirm_stock_not_deducted: bool,
                                actor_user_id: int | None = None) -> dict:
    """Reserve stock for a PAID order that has none (it predates stock reservations).

    The caller holds the order row lock, which serialises repeated and concurrent attempts; the stock rows
    are then locked by allocate_stock, so two orders cannot take the same units. Everything happens in the
    caller's transaction: on any failure nothing is reserved and nothing is claimed.

    Safety rules:
    * the order must exist, be uncancelled, un-shipped and genuinely paid (a SUCCESS payment);
    * required stock comes from the actual order items;
    * an order that already has an active reservation is left alone (idempotent, never a duplicate);
    * an order whose reservation was released is refused: its stock history is ambiguous;
    * the caller must confirm the stock was not already taken from inventory when the order was placed. The
      database cannot show whether an old order deducted it, so a person has to vouch for that;
    * it does NOT approve the order, change its status, or create shipment/payment/tracking events.
    """
    if order.order_status == "CANCELLED":
        raise HTTPException(status_code=409, detail="This order is cancelled, so no stock can be reserved for it.")
    if not is_paid(db, order.order_id):
        raise HTTPException(status_code=409, detail="This order has no successful payment, so its stock cannot be recovered.")
    if db.query(Shipment.shipment_id).filter(Shipment.order_id == order.order_id,
                                             Shipment.shipment_status != "CANCELLED").first():
        raise HTTPException(status_code=409, detail="This order already has a shipment; stock cannot be re-reserved.")

    requested: dict[int, int] = {}
    for item in db.query(OrderItem).filter(OrderItem.order_id == order.order_id):
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity
    if not requested:
        raise HTTPException(status_code=409, detail="This order has no items, so there is nothing to reserve.")

    existing = active_reservations(db, order.order_id)
    if existing:
        reserved: dict[int, int] = {}
        for r in existing:
            reserved[r.product_id] = reserved.get(r.product_id, 0) + r.reserved_quantity
        if reserved != requested:
            raise HTTPException(status_code=409, detail="Recorded reservations do not match the order items; this needs manual review.")
        return {"status": "ALREADY_RESERVED", "recovered": False, "message": "This order already has its stock reserved. Nothing was changed."}
    if db.query(OrderInventoryReservation.reservation_id).filter(OrderInventoryReservation.order_id == order.order_id).first():
        raise HTTPException(status_code=409, detail="This order's reservation was released earlier, so its stock history needs manual review.")
    if not confirm_stock_not_deducted:
        raise HTTPException(
            status_code=409,
            detail="Confirm that stock for this order was not already taken from inventory when it was placed, then try again.",
        )

    allocation = allocate_stock(db, requested)   # locks the stock; 409 with the shortfall if it is not there
    now = datetime.now()
    taken = []
    for product_id in sorted(requested):
        for inventory_row, amount in allocation.allocations[product_id]:
            inventory_row.quantity -= amount
            inventory_row.last_updated = now
            db.add(OrderInventoryReservation(order_id=order.order_id, warehouse_id=inventory_row.warehouse_id,
                                             product_id=product_id, reserved_quantity=amount))
            taken.append(f"{amount} x product {product_id} from warehouse {inventory_row.warehouse_id}")
    db.flush()
    log_event(db, order.order_id, "STOCK_RECOVERED",
              "Stock reserved after the fact for a paid order that predates reservations: " + "; ".join(taken) + ".",
              actor_user_id=actor_user_id)
    plan = plan_order(db, order, selection_note=allocation.note, actor_user_id=actor_user_id)
    return {"status": "RESERVED", "recovered": True, "reserved": taken, "fulfilment_status": plan.fulfilment_status,
            "approved": plan.approved_at is not None,
            "message": "Stock reserved. The order still needs to be approved before a shipment is created."}


def approve_paid_order(db: Session, order: Order, *, actor_user_id: int | None = None):
    """Operations approval of a paid order, then dispatch (shipment + driver/vehicle allocation).

    The caller holds the order row lock. Only a successfully paid, uncancelled order can be approved.
    Idempotent: the first approval records who and when; repeating it only re-runs dispatch for an order
    that still has no shipment or no driver, and never creates a second shipment.
    """
    if order.order_status == "CANCELLED":
        raise HTTPException(status_code=409, detail="This order is cancelled and cannot be approved.")
    if not is_paid(db, order.order_id):
        raise HTTPException(status_code=409, detail="This order has not been paid, so it cannot be approved.")
    if not active_reservations(db, order.order_id):
        # Approving would only record a dead end. Staff must resolve the missing stock first.
        raise HTTPException(
            status_code=409,
            detail="No stock is reserved for this order (it predates reservations or its reservation was released). "
                   "Recover the reservation first, then approve.",
        )
    plan = db.query(OrderFulfilment).filter(OrderFulfilment.order_id == order.order_id).first()
    if plan is None:
        plan = plan_order(db, order, actor_user_id=actor_user_id)
    if plan.approved_at is None:
        plan.approved_at = datetime.now()
        plan.approved_by_user_id = actor_user_id
        db.flush()
        log_event(db, order.order_id, "APPROVED", "Order approved by operations.", actor_user_id=actor_user_id)
    return fulfil_paid_order(db, order, actor_user_id=actor_user_id)


def fulfil_paid_order(db: Session, order: Order, *, actor_user_id: int | None = None):
    """Create the single shipment for a paid order and try to assign a driver and vehicle.

    The caller must hold a row lock on the order, which serialises repeated or concurrent requests, and
    the order must be paid. The plan is refreshed first, so route changes made since checkout are picked
    up. Nothing is fabricated: if planning is blocked the paid order stays CONFIRMED with no shipment
    and the plan says why.
    """
    if db.query(Shipment.shipment_id).filter(
        Shipment.order_id == order.order_id, Shipment.shipment_status != "CANCELLED"
    ).first():
        return fulfilment_summary(db, order)

    plan = plan_order(db, order, actor_user_id=actor_user_id)
    if plan.fulfilment_status == "BLOCKED":
        return unfulfilled(
            BLOCK_TO_RESULT.get(plan.reason_code, "BLOCKED"),
            f"{plan.reason_detail} No shipment was created. Operations follow-up is required.",
            reason_code=plan.reason_code,
        )

    route = db.query(Route).filter(Route.route_id == plan.route_id).first() if plan.route_id else None
    warehouse = db.query(Warehouse).filter(Warehouse.warehouse_id == plan.origin_warehouse_id).first()
    reservations = active_reservations(db, order.order_id)
    units_by_warehouse: dict[int, int] = {}
    for r in reservations:
        units_by_warehouse[r.warehouse_id] = units_by_warehouse.get(r.warehouse_id, 0) + r.reserved_quantity

    now = datetime.now()
    shipment = Shipment(
        order_id=order.order_id, warehouse_id=warehouse.warehouse_id, route_id=route.route_id if route else None,
        shipment_date=now,
        estimated_delivery=now + route.estimated_duration if route and route.estimated_duration else None,
        shipment_status="CREATED",
    )
    db.add(shipment)
    db.flush()
    for item in db.query(OrderItem).filter(OrderItem.order_id == order.order_id).order_by(OrderItem.product_id):
        db.add(ShipmentItem(shipment_id=shipment.shipment_id, order_id=order.order_id,
                            product_id=item.product_id, quantity=item.quantity))
    db.flush()
    log_event(db, order.order_id, "SHIPMENT_CREATED",
              f"Shipment {shipment.shipment_id} created from {warehouse.warehouse_name}"
              + (f" via route {route.route_name}." if route else " (no configured route; none is required)."),
              shipment.shipment_id, actor_user_id)

    weight, _unknown = order_weight(db, order.order_id)
    assignment = assign_eligible_driver(db, shipment, order.shipping_address, weight_kg=weight,
                                        actor_user_id=actor_user_id)

    remarks = []
    if len(units_by_warehouse) > 1:
        remarks.append("Consolidated from warehouses " + ", ".join(str(w) for w in sorted(units_by_warehouse)))
    remarks.append("Driver assigned" if assignment else "Awaiting driver assignment")
    db.add(ShipmentTracking(
        shipment_id=shipment.shipment_id, status="CREATED",
        location=f"{warehouse.warehouse_name}, {warehouse.city}"[:150],
        tracking_timestamp=now, remarks="; ".join(remarks)[:255],
    ))

    if assignment:
        order.order_status = "PROCESSING"
        _set_plan(db, order, "ASSIGNED", origin=warehouse.warehouse_id, route=plan.route_id,
                  basis=plan.route_basis, actor_user_id=actor_user_id, event_type="ASSIGNED")
        message = "Shipment created and driver assigned."
    else:
        reason = explain_no_assignment(db, date.today(), weight)
        _set_plan(db, order, "AWAITING_ASSIGNMENT", code="NO_ELIGIBLE_DRIVER", detail=reason,
                  origin=warehouse.warehouse_id, route=plan.route_id, basis=plan.route_basis,
                  actor_user_id=actor_user_id, event_type="ASSIGNMENT_PENDING")
        message = "Shipment created. No eligible driver and vehicle are available yet, so it is awaiting assignment."
    db.flush()

    return {
        "status": "DRIVER_ASSIGNED" if assignment else "PENDING_ASSIGNMENT",
        "message": message,
        "shipment_id": shipment.shipment_id, "shipment_status": "CREATED",
        "origin_warehouse_id": warehouse.warehouse_id,
        "source_warehouse_ids": sorted(units_by_warehouse),
        "route_id": route.route_id if route else None,
        "driver_id": assignment["driver_id"] if assignment else None,
        "vehicle_id": assignment["vehicle_id"] if assignment else None,
        "reason_code": None if assignment else "NO_ELIGIBLE_DRIVER",
    }


# ---------------------------------------------------------------------------------------------
# Cancellation and stock release
# ---------------------------------------------------------------------------------------------
def release_order_stock(db: Session, order_id: int) -> int:
    """Return an order's reserved stock to inventory. Safe to call repeatedly: returns the units
    released by this call, and 0 once everything was released.

    Exactly-once is guaranteed by the released_at marker: only rows where it is NULL are processed,
    each is marked in the same transaction as the stock is added back, and the caller holds the order
    lock.
    """
    released = 0
    rows = (
        db.query(OrderInventoryReservation)
        .filter(OrderInventoryReservation.order_id == order_id, OrderInventoryReservation.released_at.is_(None))
        .order_by(OrderInventoryReservation.warehouse_id, OrderInventoryReservation.product_id)
        .with_for_update()
        .all()
    )
    now = datetime.now()
    for reservation in rows:
        stock = (
            db.query(Inventory)
            .filter(Inventory.warehouse_id == reservation.warehouse_id, Inventory.product_id == reservation.product_id)
            .with_for_update()
            .first()
        )
        stock.quantity += reservation.reserved_quantity
        stock.last_updated = now
        reservation.released_at = now
        released += reservation.reserved_quantity
    db.flush()
    return released


def cancel_order(db: Session, order: Order, *, actor_user_id: int | None = None, reason: str = "CANCELLED"):
    """Cancel an unpaid order and release its stock. The caller holds the order lock.

    Allowed only while the order is PENDING, has no successful payment and has no active shipment; a
    paid or dispatched order needs a refund/return workflow that does not exist, so it is refused (409).
    Repeating the call on a cancelled order changes nothing.
    """
    if order.order_status == "CANCELLED":
        return {"already_cancelled": True, "units_released": 0}
    payment = db.query(Payment).filter(Payment.order_id == order.order_id).first()
    if payment and payment.payment_status in ("SUCCESS", "REFUNDED"):
        raise HTTPException(status_code=409, detail="A paid order cannot be cancelled here; it needs a refund workflow, which is not implemented.")
    if order.order_status != "PENDING":
        raise HTTPException(status_code=409, detail=f"An order that is {order.order_status} is already being fulfilled and cannot be cancelled.")
    if db.query(Shipment.shipment_id).filter(Shipment.order_id == order.order_id, Shipment.shipment_status != "CANCELLED").first():
        raise HTTPException(status_code=409, detail="This order already has an active shipment and cannot be cancelled.")

    units = release_order_stock(db, order.order_id)
    order.order_status = "CANCELLED"
    invoice = db.query(Invoice).filter(Invoice.order_id == order.order_id).first()
    if invoice and invoice.invoice_status == "ISSUED":
        invoice.invoice_status = "CANCELLED"
    plan = db.query(OrderFulfilment).filter(OrderFulfilment.order_id == order.order_id).first()
    if plan is not None:
        plan.fulfilment_status = "CANCELLED"
        plan.reason_code = reason
        plan.reason_detail = f"Order cancelled ({reason.lower().replace('_', ' ')}); reserved stock released."
        plan.updated_at = datetime.now()
    log_event(db, order.order_id, "CANCELLED", f"Order cancelled ({reason}); {units} unit(s) returned to stock.",
              actor_user_id=actor_user_id)
    db.flush()
    return {"already_cancelled": False, "units_released": units}


def release_abandoned_orders(db: Session, older_than_minutes: int | None = None, *,
                             actor_user_id: int | None = None) -> list[dict]:
    """Cancel unpaid orders older than the limit, releasing their stock. Returns what was released.

    Each order is locked and re-checked individually, so an order paid a moment ago is skipped.
    """
    minutes = older_than_minutes if older_than_minutes and older_than_minutes > 0 else UNPAID_ORDER_TTL_MINUTES
    cutoff = datetime.now() - timedelta(minutes=minutes)
    ids = [
        order_id for (order_id,) in db.query(Order.order_id)
        .filter(Order.order_status == "PENDING", Order.order_date < cutoff)
        .order_by(Order.order_id)
    ]
    results = []
    for order_id in ids:
        order = db.query(Order).filter(Order.order_id == order_id).with_for_update().first()
        try:
            outcome = cancel_order(db, order, actor_user_id=actor_user_id, reason="ABANDONED")
        except HTTPException:
            continue
        if not outcome["already_cancelled"]:
            results.append({"order_id": order_id, "units_released": outcome["units_released"]})
    return results



def record_assignment(db: Session, order: Order, shipment: Shipment, *, actor_user_id: int | None = None):
    """After a driver was assigned outside fulfil_paid_order (retry or manual): move the order from
    CONFIRMED to PROCESSING and mark the plan ASSIGNED, if the order has one."""
    if order.order_status == "CONFIRMED":
        order.order_status = "PROCESSING"
    plan = db.query(OrderFulfilment).filter(OrderFulfilment.order_id == order.order_id).first()
    if plan is not None and plan.fulfilment_status in ("AWAITING_ASSIGNMENT", "ASSIGNED", "PLANNED"):
        _set_plan(db, order, "ASSIGNED", origin=shipment.warehouse_id, route=shipment.route_id,
                  basis=plan.route_basis, actor_user_id=actor_user_id, event_type="ASSIGNED")
