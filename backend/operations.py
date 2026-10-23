"""Read-only views over real data: operations dashboard, warehouse overview and order tracking.

Nothing here writes to the database or invents values. Where a fact is not stored (an old order's
assignment time, a warehouse's incoming transfers, live GPS) the view says so instead of guessing.
"""
from datetime import date, datetime

from sqlalchemy import String, cast, exists, func, or_
from sqlalchemy.orm import Session, aliased

from fulfilment import (
    ACTIVE_WAREHOUSE_STATUS, LOAD_DELIVERY_STATUSES, MAX_OPEN_DELIVERIES_PER_DRIVER, evaluate_fleet,
    explain_no_assignment, order_weight,
)
from models import (
    Customer, Delivery, Driver, Employee, Inventory, Invoice, Order, OrderFulfilment,
    OrderFulfilmentEvent, OrderInventoryReservation, OrderItem, Payment, Product, Route, Shipment,
    ShipmentTracking, Vehicle, Warehouse,
)

CLOSED_SHIPMENT = ("DELIVERED", "CANCELLED")
IN_FLIGHT = ("PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY")
SHIPMENT_FLOW = ["CREATED", "PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"]
ORDER_RANK = ["PENDING", "CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED"]


def _f(value):
    return float(value) if value is not None else None


def _duration_text(value):
    return str(value) if value is not None else None


# ---------------------------------------------------------------------------------------------
# Order tracking (customer, driver and staff views share this)
# ---------------------------------------------------------------------------------------------
SHIPMENT_STAGE_LABELS = {
    "CREATED": "Preparing shipment", "PICKED_UP": "Picked up", "IN_TRANSIT": "In transit",
    "OUT_FOR_DELIVERY": "Out for delivery", "DELIVERED": "Delivered", "CANCELLED": "Cancelled",
}


def order_stage(order, payment, plan, shipment, delivery) -> dict:
    """One plain-language stage for an order, safe to show a customer. Derived only from stored rows."""
    if order.order_status == "CANCELLED":
        return {"key": "CANCELLED", "label": "Cancelled"}
    paid = payment is not None and payment.payment_status == "SUCCESS"
    if shipment is None:
        if not paid:
            if payment is not None and payment.payment_status == "FAILED":
                return {"key": "PAYMENT_FAILED", "label": "Payment failed"}
            return {"key": "AWAITING_PAYMENT", "label": "Awaiting payment"}
        if plan is None or plan.approved_at is None:
            return {"key": "AWAITING_APPROVAL", "label": "Awaiting approval"}
        return {"key": "PREPARING", "label": "Preparing shipment"}
    status = shipment.shipment_status
    if status == "CREATED":
        if delivery is not None:
            return {"key": "ASSIGNED", "label": "Driver assigned"}
        return {"key": "PREPARING", "label": "Preparing shipment"}
    return {"key": status, "label": SHIPMENT_STAGE_LABELS.get(status, status.replace("_", " ").title())}


def build_milestones(order, payment, plan, shipment, delivery, events, audience="staff"):
    """The journey as persisted facts. Stages never recorded are 'skipped' or 'not_recorded', never invented.
    Customers get the same journey without internal planning steps or allocation diagnostics."""
    first_event = {}
    for e in events:
        first_event.setdefault(e.status, e)

    def milestone(key, label, state, at=None, detail=None):
        return {"key": key, "label": label, "state": state, "at": at, "detail": detail}

    steps = [milestone("ORDER_PLACED", "Order placed", "done", order.order_date)]

    if payment is not None and payment.payment_status == "SUCCESS":
        steps.append(milestone("PAYMENT_CONFIRMED", "Payment confirmed", "done", payment.payment_date))
    elif payment is not None and payment.payment_status == "FAILED":
        steps.append(milestone("PAYMENT_CONFIRMED", "Payment confirmed", "failed", payment.payment_date, "The last payment attempt failed."))
    else:
        steps.append(milestone("PAYMENT_CONFIRMED", "Payment confirmed", "upcoming", None, "Awaiting payment."))

    staff = audience == "staff"
    paid = payment is not None and payment.payment_status == "SUCCESS"
    if plan is not None and plan.approved_at is not None:
        steps.append(milestone("ORDER_APPROVED", "Approved by operations", "done", plan.approved_at))
    elif shipment is not None:
        # Shipped before approvals were recorded. Staff are told so; customers simply are not shown a step
        # that was never recorded (no approval is claimed, and none is invented).
        if staff:
            steps.append(milestone("ORDER_APPROVED", "Approved by operations", "not_recorded", None,
                                   "Shipped before approval was recorded."))
    else:
        steps.append(milestone("ORDER_APPROVED", "Approved by operations", "upcoming", None,
                               "Waiting for an Operations Manager to approve this paid order." if paid and staff else None))

    if staff:
        if plan is not None:
            if plan.fulfilment_status == "BLOCKED":
                steps.append(milestone("SHIPMENT_PLANNED", "Shipment planned", "blocked", plan.planned_at, plan.reason_detail))
            else:
                steps.append(milestone("SHIPMENT_PLANNED", "Shipment planned", "done", plan.planned_at))
        else:
            steps.append(milestone("SHIPMENT_PLANNED", "Shipment planned", "not_recorded", None, "No planning record exists for this order (placed before planning was recorded)."))

    if shipment is not None:
        steps.append(milestone("SHIPMENT_CREATED", "Shipment created", "done", shipment.shipment_date))
    else:
        steps.append(milestone("SHIPMENT_CREATED", "Shipment created", "upcoming"))

    if delivery is not None:
        steps.append(milestone("DRIVER_ASSIGNED", "Driver and vehicle assigned", "done", delivery.assigned_at,
                               None if (delivery.assigned_at or not staff) else "Assignment time was not recorded."))
    else:
        detail = plan.reason_detail if (staff and plan is not None and shipment is not None and plan.reason_code) else None
        steps.append(milestone("DRIVER_ASSIGNED", "Driver and vehicle assigned", "upcoming", None, detail))

    reached = SHIPMENT_FLOW.index(shipment.shipment_status) if shipment is not None and shipment.shipment_status in SHIPMENT_FLOW else -1
    for key, label, status in (
        ("PICKED_UP", "Picked up", "PICKED_UP"), ("IN_TRANSIT", "In transit", "IN_TRANSIT"),
        ("OUT_FOR_DELIVERY", "Out for delivery", "OUT_FOR_DELIVERY"), ("DELIVERED", "Delivered", "DELIVERED"),
    ):
        event = first_event.get(status)
        if event is not None:
            steps.append(milestone(key, label, "done", event.tracking_timestamp, event.location))
        elif reached >= SHIPMENT_FLOW.index(status):
            steps.append(milestone(key, label, "skipped" if staff else "done", None,
                                   "Reached without a recorded event for this stage." if staff else None))
        else:
            steps.append(milestone(key, label, "upcoming"))

    cancelled_at = None
    if shipment is not None and shipment.shipment_status == "CANCELLED":
        event = first_event.get("CANCELLED")
        cancelled_at = event.tracking_timestamp if event else None
    if order.order_status == "CANCELLED" or (shipment is not None and shipment.shipment_status == "CANCELLED"):
        for step in steps:
            if step["state"] in ("upcoming", "blocked"):
                step["state"] = "not_reached"
        steps.append(milestone("CANCELLED", "Cancelled", "cancelled", cancelled_at,
                               "Order cancelled." if order.order_status == "CANCELLED" else "Shipment cancelled."))
    else:
        for step in steps:
            if step["state"] == "upcoming":
                step["state"] = "current"
                break
    return steps


def _explanation(order, payment, plan, shipment, delivery, audience="staff"):
    """Staff get the technical reason; customers and drivers get a calm, plain-language status."""
    if order.order_status == "CANCELLED":
        return "This order was cancelled."
    stage = order_stage(order, payment, plan, shipment, delivery)["key"]
    if audience == "driver":
        return None
    if audience != "staff":
        return {
            "AWAITING_PAYMENT": "Awaiting payment. We will start preparing your order once it is paid.",
            "PAYMENT_FAILED": "Your last payment attempt did not go through. You can try paying again.",
            "AWAITING_APPROVAL": "Payment received. Your order is awaiting approval.",
            "PREPARING": "We are preparing your shipment.",
            "ASSIGNED": "Your driver is assigned. Your order will be picked up soon.",
        }.get(stage)
    if shipment is None:
        if plan is not None and plan.fulfilment_status == "BLOCKED":
            return f"Fulfilment is blocked: {plan.reason_detail}"
        if stage == "PAYMENT_FAILED":
            return "The last payment attempt failed. The order will not be dispatched until payment succeeds."
        if stage == "AWAITING_PAYMENT":
            return "Awaiting payment. The shipment is planned but will not be dispatched until payment succeeds."
        if stage == "AWAITING_APPROVAL":
            return "Paid and waiting for an Operations Manager to approve it. No shipment is created before approval."
        return "Approved; the shipment has not been created yet." + (f" {plan.reason_detail}" if plan and plan.reason_detail else "")
    if delivery is None and shipment.shipment_status == "CREATED":
        return "Awaiting driver assignment." + (f" {plan.reason_detail}" if plan and plan.reason_detail else "")
    if delivery is not None and delivery.delivery_status == "FAILED":
        return "The last delivery attempt failed; another attempt is expected."
    if shipment.shipment_status not in CLOSED_SHIPMENT and shipment.estimated_delivery and shipment.estimated_delivery < datetime.now():
        return "This shipment is later than its estimated delivery time."
    return None


def _warnings(order, shipment):
    warnings = []
    if shipment is not None:
        if shipment.shipment_status == "DELIVERED" and order.order_status != "DELIVERED":
            warnings.append(f"Order status is {order.order_status} but its shipment is DELIVERED (recorded before orders and shipments were kept in sync).")
        elif shipment.shipment_status in IN_FLIGHT and order.order_status in ("PENDING", "CONFIRMED", "PROCESSING"):
            warnings.append(f"Order status is {order.order_status} but its shipment is {shipment.shipment_status}.")
    return warnings


def order_tracking_view(db: Session, order: Order, audience: str, shipment_id: int | None = None) -> dict:
    """audience: 'staff' (ADMIN/OPERATIONS_MANAGER), 'driver' or 'customer'. shipment_id selects one of
    an order's shipments (for example a cancelled one); by default the active shipment is shown."""
    customer = db.query(Customer).filter(Customer.customer_id == order.customer_id).first()
    payment = db.query(Payment).filter(Payment.order_id == order.order_id).first()
    invoice = db.query(Invoice).filter(Invoice.order_id == order.order_id).first()
    plan = db.query(OrderFulfilment).filter(OrderFulfilment.order_id == order.order_id).first()
    shipment_query = db.query(Shipment).filter(Shipment.order_id == order.order_id)
    if shipment_id is not None:
        shipment_query = shipment_query.filter(Shipment.shipment_id == shipment_id)
    shipment = shipment_query.order_by((Shipment.shipment_status == "CANCELLED"), Shipment.shipment_id.desc()).first()
    delivery = db.query(Delivery).filter(Delivery.shipment_id == shipment.shipment_id).first() if shipment else None
    events = (
        db.query(ShipmentTracking).filter(ShipmentTracking.shipment_id == shipment.shipment_id)
        .order_by(ShipmentTracking.tracking_id).all() if shipment else []
    )
    items = (
        db.query(OrderItem, Product).join(Product, Product.product_id == OrderItem.product_id)
        .filter(OrderItem.order_id == order.order_id).order_by(OrderItem.product_id).all()
    )

    warehouse_id = shipment.warehouse_id if shipment else (plan.origin_warehouse_id if plan else None)
    route_id = shipment.route_id if shipment else (plan.route_id if plan else None)
    warehouse = db.query(Warehouse).filter(Warehouse.warehouse_id == warehouse_id).first() if warehouse_id else None
    route = db.query(Route).filter(Route.route_id == route_id).first() if route_id else None

    assignment = None
    if delivery is not None:
        driver_employee = db.query(Employee).filter(Employee.employee_id == delivery.driver_id).first()
        vehicle = db.query(Vehicle).filter(Vehicle.vehicle_id == delivery.vehicle_id).first() if delivery.vehicle_id else None
        assignment = {
            "delivery_id": delivery.delivery_id,
            "delivery_status": delivery.delivery_status,
            "driver_name": driver_employee.name if driver_employee else None,
            "vehicle_registration": vehicle.registration_no if vehicle else None,
            "vehicle_type": vehicle.vehicle_type if vehicle else None,
            "vehicle_recorded": vehicle is not None,
            "assigned_at": delivery.assigned_at,
            "delivery_address": delivery.delivery_address,
        }
        if audience != "customer":
            assignment["driver_id"] = delivery.driver_id
            assignment["vehicle_id"] = delivery.vehicle_id

    last = events[-1] if events else None
    view = {
        "order": {
            "order_id": order.order_id, "order_date": order.order_date, "order_status": order.order_status,
            "shipping_address": order.shipping_address, "destination_city": order.destination_city,
            "customer_id": order.customer_id,
            "customer_name": customer.name if customer and audience != "driver" else None,
        },
        "items": [
            {"product_id": i.product_id, "product_name": p.product_name, "quantity": i.quantity,
             "unit_price": _f(i.unit_price), "item_total": _f(i.quantity * i.unit_price)}
            for i, p in items
        ],
        "payment": {"payment_status": payment.payment_status, "payment_date": payment.payment_date,
                    "amount": _f(payment.amount)} if payment and audience != "driver" else None,
        "invoice_status": invoice.invoice_status if invoice and audience != "driver" else None,
        "stage": order_stage(order, payment, plan, shipment, delivery),
        "fulfilment": ({
            "status": plan.fulfilment_status, "reason_code": plan.reason_code, "reason_detail": plan.reason_detail,
            "route_basis": plan.route_basis, "planned_at": plan.planned_at, "approved_at": plan.approved_at,
            "selection_note": plan.selection_note,
        } if plan and audience == "staff" else None),
        # Customers see the origin city, and the route, only once a shipment exists; never a warehouse name or address.
        "warehouse": (
            {"city": warehouse.city} if audience == "customer" and shipment is not None
            else None if audience == "customer"
            else {"warehouse_id": warehouse.warehouse_id, "warehouse_name": warehouse.warehouse_name,
                  "city": warehouse.city, "address": warehouse.address}
        ) if warehouse else None,
        "route": {
            "route_id": route.route_id, "route_name": route.route_name, "source": route.source,
            "destination": route.destination, "distance_km": _f(route.distance_km),
            "estimated_duration": _duration_text(route.estimated_duration),
            "intermediate_stops": None,  # intermediate warehouses / transfer points are not modelled
        } if route and (audience != "customer" or shipment is not None) else None,
        "shipment": {
            "shipment_id": shipment.shipment_id, "shipment_status": shipment.shipment_status,
            "shipment_date": shipment.shipment_date, "estimated_delivery": shipment.estimated_delivery,
            "actual_delivery": shipment.actual_delivery,
        } if shipment else None,
        "assignment": assignment,
        "milestones": build_milestones(order, payment, plan, shipment, delivery, events, audience),
        "tracking_events": [
            {"tracking_id": e.tracking_id, "status": e.status, "location": e.location,
             "tracking_timestamp": e.tracking_timestamp, "remarks": e.remarks}
            for e in events
        ],
        "latest_event": {"status": last.status, "location": last.location,
                         "tracking_timestamp": last.tracking_timestamp, "remarks": last.remarks} if last else None,
        "explanation": _explanation(order, payment, plan, shipment, delivery, audience),
        "warnings": _warnings(order, shipment) if audience == "staff" else [],
        "live_tracking": {"supported": False, "note": "Tracking is event-based; there is no GPS or live vehicle location."},
    }
    if audience == "staff":
        view["fulfilment_events"] = [
            {"event_id": e.event_id, "event_type": e.event_type, "detail": e.detail,
             "shipment_id": e.shipment_id, "actor_user_id": e.actor_user_id, "created_at": e.created_at}
            for e in db.query(OrderFulfilmentEvent).filter(OrderFulfilmentEvent.order_id == order.order_id)
            .order_by(OrderFulfilmentEvent.event_id)
        ]
    return view


# ---------------------------------------------------------------------------------------------
# Warehouses
# ---------------------------------------------------------------------------------------------
def warehouse_overview(db: Session) -> list[dict]:
    warehouses = db.query(Warehouse).order_by(Warehouse.warehouse_id).all()
    managers = {e.employee_id: e.name for e in db.query(Employee).all()}
    products = {p.product_id: p for p in db.query(Product).all()}

    stock: dict[int, list[Inventory]] = {}
    for row in db.query(Inventory).order_by(Inventory.warehouse_id, Inventory.product_id):
        stock.setdefault(row.warehouse_id, []).append(row)

    # Reserved = stock allocated to orders whose shipment has not been picked up yet.
    picked_up = exists().where(
        Shipment.order_id == Order.order_id, Shipment.shipment_status.notin_(("CREATED", "CANCELLED")))
    reserved: dict[tuple[int, int], int] = {}
    for warehouse_id, product_id, qty in (
        db.query(OrderInventoryReservation.warehouse_id, OrderInventoryReservation.product_id,
                 func.sum(OrderInventoryReservation.reserved_quantity))
        .join(Order, Order.order_id == OrderInventoryReservation.order_id)
        .filter(OrderInventoryReservation.released_at.is_(None), Order.order_status.notin_(("CANCELLED", "DELIVERED")), ~picked_up)
        .group_by(OrderInventoryReservation.warehouse_id, OrderInventoryReservation.product_id)
    ):
        reserved[(warehouse_id, product_id)] = int(qty)

    shipment_counts: dict[int, dict[str, int]] = {}
    for warehouse_id, status, count in (
        db.query(Shipment.warehouse_id, Shipment.shipment_status, func.count(Shipment.shipment_id))
        .group_by(Shipment.warehouse_id, Shipment.shipment_status)
    ):
        shipment_counts.setdefault(warehouse_id, {})[status] = count

    routes_from: dict[str, int] = {}
    for (source,) in db.query(Route.source).filter(Route.route_status == "ACTIVE"):
        routes_from[source.strip().lower()] = routes_from.get(source.strip().lower(), 0) + 1

    # Orders being fulfilled by each warehouse: shipment origin, else the plan's origin (not yet shipped).
    order_rows: dict[int, dict[int, dict]] = {}
    for order, customer, shipment_id, shipment_status, ship_wh, plan in (
        db.query(Order, Customer, Shipment.shipment_id, Shipment.shipment_status, Shipment.warehouse_id, OrderFulfilment)
        .join(Customer, Customer.customer_id == Order.customer_id)
        .outerjoin(Shipment, (Shipment.order_id == Order.order_id) & (Shipment.shipment_status != "CANCELLED"))
        .outerjoin(OrderFulfilment, OrderFulfilment.order_id == Order.order_id)
        .filter(Order.order_status.notin_(("CANCELLED", "DELIVERED")))
        .order_by(Order.order_id.desc())
    ):
        wh = ship_wh or (plan.origin_warehouse_id if plan else None)
        if wh is None or (shipment_status == "DELIVERED"):
            continue
        order_rows.setdefault(wh, {})[order.order_id] = {
            "order_id": order.order_id, "order_status": order.order_status, "customer_name": customer.name,
            "shipment_id": shipment_id, "shipment_status": shipment_status,
            "fulfilment_status": plan.fulfilment_status if plan else None,
        }

    result = []
    for w in warehouses:
        lines = []
        available_total = reserved_total = 0
        low = 0
        for row in stock.get(w.warehouse_id, []):
            res = reserved.get((w.warehouse_id, row.product_id), 0)
            is_low = row.quantity <= row.reorder_level
            low += 1 if is_low else 0
            available_total += row.quantity
            reserved_total += res
            product = products.get(row.product_id)
            lines.append({
                "product_id": row.product_id, "product_name": product.product_name if product else None,
                "available": row.quantity, "reserved": res, "on_hand": row.quantity + res,
                "reorder_level": row.reorder_level, "low_stock": is_low, "out_of_stock": row.quantity == 0,
                "last_updated": row.last_updated,
            })
        on_hand = available_total + reserved_total
        capacity = _f(w.capacity)
        counts = shipment_counts.get(w.warehouse_id, {})
        orders = list(order_rows.get(w.warehouse_id, {}).values())
        gaps = []
        if w.capacity is None:
            gaps.append("No storage capacity is recorded.")
        if not lines:
            gaps.append("No inventory is recorded for this warehouse.")
        if w.manager_employee_id is None:
            gaps.append("No manager is assigned.")
        result.append({
            "warehouse_id": w.warehouse_id, "warehouse_name": w.warehouse_name, "address": w.address, "city": w.city,
            "status": w.status, "is_active": w.status == ACTIVE_WAREHOUSE_STATUS,
            "manager_employee_id": w.manager_employee_id, "manager_name": managers.get(w.manager_employee_id),
            "capacity": capacity,
            "units_available": available_total, "units_reserved": reserved_total, "units_on_hand": on_hand,
            # The schema does not say what capacity is measured in; it is compared with units on hand.
            "utilisation_percent": round(on_hand / capacity * 100, 2) if capacity else None,
            "utilisation_basis": "units on hand / capacity (capacity unit not defined in the schema)",
            "low_stock_lines": low, "inventory": lines,
            "outgoing_shipments": {
                "awaiting_pickup": counts.get("CREATED", 0),
                "in_flight": sum(counts.get(s, 0) for s in IN_FLIGHT),
                "delivered": counts.get("DELIVERED", 0), "cancelled": counts.get("CANCELLED", 0),
            },
            "incoming_shipments": {"supported": False, "note": "Transfers between warehouses are not modelled."},
            "orders_in_fulfilment": {"count": len(orders), "orders": orders[:20]},
            "outgoing_routes": routes_from.get((w.city or "").strip().lower(), 0),
            "data_gaps": gaps,
        })
    return result


# ---------------------------------------------------------------------------------------------
# Operations summary and lists
# ---------------------------------------------------------------------------------------------
def operations_summary(db: Session) -> dict:
    now = datetime.now()
    paid = exists().where(Payment.order_id == Order.order_id, Payment.payment_status == "SUCCESS")
    active_shipment = exists().where(Shipment.order_id == Order.order_id, Shipment.shipment_status != "CANCELLED")
    live = Order.order_status.notin_(("CANCELLED", "DELIVERED"))

    total_orders = db.query(func.count(Order.order_id)).scalar()
    awaiting_payment = db.query(func.count(Order.order_id)).filter(Order.order_status == "PENDING", ~paid).scalar()
    paid_unshipped = db.query(func.count(Order.order_id)).filter(live, paid, ~active_shipment).scalar()
    approved = exists().where(OrderFulfilment.order_id == Order.order_id, OrderFulfilment.approved_at.isnot(None))
    awaiting_approval = db.query(func.count(Order.order_id)).filter(live, paid, ~active_shipment, ~approved).scalar()
    blocked_orders = (
        db.query(func.count(OrderFulfilment.order_id))
        .join(Order, Order.order_id == OrderFulfilment.order_id)
        .filter(OrderFulfilment.fulfilment_status == "BLOCKED", Order.order_status != "CANCELLED").scalar()
    )

    def shipments(*conditions):
        return db.query(func.count(Shipment.shipment_id)).filter(*conditions).scalar()

    has_delivery = exists().where(Delivery.shipment_id == Shipment.shipment_id)
    awaiting_assignment = shipments(Shipment.shipment_status == "CREATED", ~has_delivery)
    delayed = shipments(Shipment.shipment_status.notin_(CLOSED_SHIPMENT), Shipment.estimated_delivery.isnot(None), Shipment.estimated_delivery < now)

    evaluations = evaluate_fleet(db, date.today(), None)
    drivers_total = db.query(func.count(Driver.employee_id)).scalar()
    eligible_drivers = {e.driver_id for e in evaluations if e.eligible}
    vehicles_total = db.query(func.count(Vehicle.vehicle_id)).scalar()
    vehicles_in_service = db.query(func.count(Vehicle.vehicle_id)).filter(Vehicle.status.in_(("ACTIVE", "AVAILABLE"))).scalar()
    vehicles_in_use = db.query(func.count(func.distinct(Delivery.vehicle_id))).filter(
        Delivery.vehicle_id.isnot(None), Delivery.delivery_status.in_(LOAD_DELIVERY_STATUSES)).scalar()
    available_vehicles = len({e.vehicle_id for e in evaluations if e.eligible and e.vehicle_id})

    low_stock = db.query(func.count()).select_from(Inventory).filter(Inventory.quantity <= Inventory.reorder_level).scalar()

    mismatch = (
        db.query(Order.order_id, Order.order_status, Shipment.shipment_status)
        .join(Shipment, (Shipment.order_id == Order.order_id) & (Shipment.shipment_status != "CANCELLED"))
        .filter(or_(
            (Shipment.shipment_status == "DELIVERED") & (Order.order_status != "DELIVERED"),
            Shipment.shipment_status.in_(IN_FLIGHT) & Order.order_status.in_(("PENDING", "CONFIRMED", "PROCESSING")),
        )).all()
    )
    return {
        "orders": {
            "total": total_orders, "awaiting_payment": awaiting_payment,
            "awaiting_approval": awaiting_approval, "awaiting_fulfilment": paid_unshipped - awaiting_approval,
            "blocked": blocked_orders,
        },
        "shipments": {
            "total": shipments(), "awaiting_assignment": awaiting_assignment,
            "in_transit": shipments(Shipment.shipment_status.in_(IN_FLIGHT)),
            "awaiting_pickup": shipments(Shipment.shipment_status == "CREATED"),
            "delivered": shipments(Shipment.shipment_status == "DELIVERED"),
            "cancelled": shipments(Shipment.shipment_status == "CANCELLED"),
            "delayed": delayed,
        },
        "fleet": {
            "drivers_total": drivers_total, "drivers_available": len(eligible_drivers),
            "vehicles_total": vehicles_total, "vehicles_in_service": vehicles_in_service,
            "vehicles_in_use": vehicles_in_use, "vehicles_available": available_vehicles,
            "max_open_deliveries_per_driver": MAX_OPEN_DELIVERIES_PER_DRIVER,
        },
        "warehouses": {
            "total": db.query(func.count(Warehouse.warehouse_id)).scalar(),
            "active": db.query(func.count(Warehouse.warehouse_id)).filter(Warehouse.status == ACTIVE_WAREHOUSE_STATUS).scalar(),
            "low_stock_lines": low_stock,
        },
        "data_consistency": {
            "order_shipment_mismatches": len(mismatch),
            "order_ids": [m[0] for m in mismatch][:20],
            "note": "Orders whose status disagrees with their shipment, usually recorded before statuses were kept in sync. Shown, not rewritten.",
        },
        "delay_rule": "A shipment is delayed when it is not delivered or cancelled and its estimated delivery time has passed.",
    }


SHIPMENT_SORTS = {
    "shipment_id": Shipment.shipment_id, "shipment_date": Shipment.shipment_date,
    "estimated_delivery": Shipment.estimated_delivery, "status": Shipment.shipment_status,
    "customer": Customer.name, "warehouse": Warehouse.warehouse_name,
}


def shipment_rows(db: Session, *, q=None, status=None, warehouse_id=None, assignment=None, delayed=None,
                  sort="shipment_id", direction="desc", page=1, page_size=25) -> dict:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    driver_emp = aliased(Employee)
    query = (
        db.query(Shipment, Order, Customer, Warehouse, Route, Delivery, driver_emp, Vehicle, OrderFulfilment)
        .join(Order, Order.order_id == Shipment.order_id)
        .join(Customer, Customer.customer_id == Order.customer_id)
        .join(Warehouse, Warehouse.warehouse_id == Shipment.warehouse_id)
        .outerjoin(Route, Route.route_id == Shipment.route_id)
        .outerjoin(Delivery, Delivery.shipment_id == Shipment.shipment_id)
        .outerjoin(driver_emp, driver_emp.employee_id == Delivery.driver_id)
        .outerjoin(Vehicle, Vehicle.vehicle_id == Delivery.vehicle_id)
        .outerjoin(OrderFulfilment, OrderFulfilment.order_id == Order.order_id)
    )
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(
            cast(Shipment.shipment_id, String).ilike(like), cast(Order.order_id, String).ilike(like),
            Customer.name.ilike(like), Warehouse.warehouse_name.ilike(like),
            driver_emp.name.ilike(like), Vehicle.registration_no.ilike(like),
        ))
    if status:
        query = query.filter(Shipment.shipment_status == status.upper())
    if warehouse_id:
        query = query.filter(Shipment.warehouse_id == warehouse_id)
    if assignment == "unassigned":
        query = query.filter(Delivery.delivery_id.is_(None), Shipment.shipment_status.notin_(CLOSED_SHIPMENT))
    elif assignment == "assigned":
        query = query.filter(Delivery.delivery_id.isnot(None))
    if delayed:
        query = query.filter(Shipment.shipment_status.notin_(CLOSED_SHIPMENT), Shipment.estimated_delivery < datetime.now())

    total = query.count()
    column = SHIPMENT_SORTS.get(sort, Shipment.shipment_id)
    query = query.order_by(column.asc() if direction == "asc" else column.desc(), Shipment.shipment_id.desc())
    now = datetime.now()
    items = []
    for shipment, order, customer, warehouse, route, delivery, driver, vehicle, plan in query.offset((page - 1) * page_size).limit(page_size):
        pending = None
        if delivery is None and shipment.shipment_status == "CREATED":
            pending = (plan.reason_detail if plan and plan.reason_detail else "Awaiting driver assignment.")
        elif delivery is not None and delivery.delivery_status == "FAILED":
            pending = "The last delivery attempt failed."
        items.append({
            "shipment_id": shipment.shipment_id, "order_id": order.order_id, "order_status": order.order_status,
            "customer_id": customer.customer_id, "customer_name": customer.name,
            "warehouse_id": warehouse.warehouse_id, "warehouse_name": warehouse.warehouse_name, "warehouse_city": warehouse.city,
            "route_id": route.route_id if route else None, "route_name": route.route_name if route else None,
            "route_source": route.source if route else None, "route_destination": route.destination if route else None,
            "destination_city": order.destination_city, "shipping_address": order.shipping_address,
            "shipment_status": shipment.shipment_status, "shipment_date": shipment.shipment_date,
            "estimated_delivery": shipment.estimated_delivery, "actual_delivery": shipment.actual_delivery,
            "delayed": bool(shipment.shipment_status not in CLOSED_SHIPMENT and shipment.estimated_delivery and shipment.estimated_delivery < now),
            "delivery_id": delivery.delivery_id if delivery else None,
            "delivery_status": delivery.delivery_status if delivery else None,
            "driver_id": delivery.driver_id if delivery else None, "driver_name": driver.name if driver else None,
            "vehicle_id": delivery.vehicle_id if delivery else None,
            "vehicle_registration": vehicle.registration_no if vehicle else None,
            "vehicle_recorded": bool(delivery is None or vehicle is not None),
            "assigned_at": delivery.assigned_at if delivery else None,
            "fulfilment_status": plan.fulfilment_status if plan else None,
            "pending_reason": pending,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size}


def _order_exception(db: Session, order: Order, plan, payment, shipment_id):
    """The operational exception on an order, for staff only: what is wrong and what to do."""
    if shipment_id is not None or order.order_status == "CANCELLED":
        return None
    if plan is not None and plan.fulfilment_status == "BLOCKED":
        return {"code": plan.reason_code, "detail": plan.reason_detail}
    paid = payment is not None and payment.payment_status == "SUCCESS"
    if paid and not db.query(OrderInventoryReservation.reservation_id).filter(
            OrderInventoryReservation.order_id == order.order_id, OrderInventoryReservation.released_at.is_(None)).first():
        return {"code": "RESERVATION_MISSING",
                "detail": "Paid, but no stock is reserved for this order (it predates reservations). "
                          "Recover the reservation, then approve."}
    return None


def order_rows(db: Session, *, stage="attention", q=None, page=1, page_size=25) -> dict:
    """Orders for the operations desk. stage: attention (blocked, or paid but not shipped),
    awaiting_approval (paid, not yet approved), awaiting_payment, or all."""
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    # An aliased Payment keeps the sub-query independent of the Payment joined in the outer query.
    paid_payment = aliased(Payment)
    paid = exists().where(paid_payment.order_id == Order.order_id, paid_payment.payment_status == "SUCCESS")
    active_shipment = exists().where(Shipment.order_id == Order.order_id, Shipment.shipment_status != "CANCELLED")
    query = (
        db.query(Order, Customer, OrderFulfilment, Payment, Warehouse)
        .join(Customer, Customer.customer_id == Order.customer_id)
        .outerjoin(OrderFulfilment, OrderFulfilment.order_id == Order.order_id)
        .outerjoin(Payment, Payment.order_id == Order.order_id)
        .outerjoin(Warehouse, Warehouse.warehouse_id == OrderFulfilment.origin_warehouse_id)
    )
    if stage == "awaiting_approval":
        query = query.filter(Order.order_status != "CANCELLED", ~active_shipment, paid,
                             OrderFulfilment.approved_at.is_(None))
    elif stage == "attention":
        query = query.filter(Order.order_status != "CANCELLED", ~active_shipment,
                             or_(OrderFulfilment.fulfilment_status == "BLOCKED", paid))
    elif stage == "awaiting_payment":
        query = query.filter(Order.order_status == "PENDING", ~paid)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(cast(Order.order_id, String).ilike(like), Customer.name.ilike(like)))
    total = query.count()
    rows = []
    for order, customer, plan, payment, warehouse in query.order_by(Order.order_id.desc()).offset((page - 1) * page_size).limit(page_size):
        shipment_id = db.query(Shipment.shipment_id).filter(Shipment.order_id == order.order_id, Shipment.shipment_status != "CANCELLED").scalar()
        rows.append({
            "order_id": order.order_id, "order_date": order.order_date, "order_status": order.order_status,
            "customer_name": customer.name, "destination_city": order.destination_city, "shipping_address": order.shipping_address,
            "payment_status": payment.payment_status if payment else None,
            "fulfilment_status": plan.fulfilment_status if plan else None,
            "reason_code": plan.reason_code if plan else None, "reason_detail": plan.reason_detail if plan else None,
            "origin_warehouse_name": warehouse.warehouse_name if warehouse else None,
            "shipment_id": shipment_id,
            "has_plan": plan is not None,
            "exception": _order_exception(db, order, plan, payment, shipment_id),
            "approved": bool(plan and plan.approved_at),
            "approved_at": plan.approved_at if plan else None,
        })
    return {"items": rows, "total": total, "page": page, "page_size": page_size,
            "pages": (total + page_size - 1) // page_size}


def assignment_options(db: Session, shipment: Shipment) -> dict:
    """Every driver/vehicle pair with whether it could take this shipment, and why not."""
    weight, unknown = order_weight(db, shipment.order_id)
    delivery = db.query(Delivery).filter(Delivery.shipment_id == shipment.shipment_id).first()
    evaluations = evaluate_fleet(db, date.today(), weight, delivery.delivery_id if delivery else None)
    return {
        "shipment_id": shipment.shipment_id,
        "shipment_weight_kg": _f(weight),
        "weight_note": None if weight is not None else f"{unknown} order line(s) have no product weight, so vehicle capacity is not checked.",
        "current": {"driver_id": delivery.driver_id, "vehicle_id": delivery.vehicle_id, "delivery_status": delivery.delivery_status} if delivery else None,
        "options": [
            {"driver_id": e.driver_id, "driver_name": e.driver_name, "vehicle_id": e.vehicle_id,
             "vehicle_registration": e.registration_no, "vehicle_type": e.vehicle_type,
             "eligible": e.eligible, "reasons": e.reasons, "open_deliveries": e.open_deliveries,
             "remaining_capacity_kg": e.remaining_capacity}
            for e in evaluations
        ],
        "summary": None if any(e.eligible for e in evaluations) else explain_no_assignment(db, date.today(), weight),
    }
