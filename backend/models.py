"""SQLAlchemy models for the LogiTrack database.

The authoritative schema is database/schema.sql plus database/migrations/*.sql. These models mirror it
(columns, nullability, defaults, foreign keys, unique and check constraints, indexes) and
tests/test_models_match_schema.py fails if they drift apart. Triggers, functions and the
shipment_summary view exist only in the SQL files; build the database from them, not with create_all().
"""
from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, ForeignKey, ForeignKeyConstraint, Index, Integer,
    Interval, Numeric, PrimaryKeyConstraint, String, TIMESTAMP, UniqueConstraint, text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()

NOW = text("CURRENT_TIMESTAMP")


class Role(Base):
    __tablename__ = "role"

    role_id = Column(Integer, primary_key=True)
    role_name = Column(String(50), nullable=False, unique=True)
    description = Column(String(255))


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey("role.role_id"), nullable=False)
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP, server_default=NOW)
    is_active = Column(Boolean, default=True, server_default=text("true"))


class Customer(Base):
    __tablename__ = "customer"

    customer_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    address = Column(String(255))
    created_at = Column(TIMESTAMP, server_default=NOW)


class Employee(Base):
    __tablename__ = "employee"

    employee_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), unique=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    department = Column(String(50))
    hire_date = Column(Date)
    salary = Column(Numeric(10, 2))
    employment_status = Column(String(30), default="ACTIVE", server_default="ACTIVE")

    __table_args__ = (
        CheckConstraint("salary IS NULL OR salary >= 0", name="chk_employee_salary"),
    )


class Driver(Base):
    __tablename__ = "driver"

    employee_id = Column(
        Integer,
        ForeignKey("employee.employee_id"),
        primary_key=True
    )
    license_no = Column(String(50), nullable=False, unique=True)
    license_expiry = Column(Date, nullable=False)
    availability_status = Column(String(30), default="AVAILABLE", server_default="AVAILABLE")


class Vehicle(Base):
    __tablename__ = "vehicle"

    vehicle_id = Column(Integer, primary_key=True)
    registration_no = Column(String(30), nullable=False, unique=True)
    vehicle_type = Column(String(50), nullable=False)
    capacity = Column(Numeric(10, 2), nullable=False)
    fuel_type = Column(String(30))
    status = Column(String(30), default="ACTIVE", server_default="ACTIVE")
    purchase_date = Column(Date)

    __table_args__ = (
        CheckConstraint("capacity > 0", name="chk_vehicle_capacity"),
    )


class DriverVehicleAssignment(Base):
    __tablename__ = "driver_vehicle_assignment"

    assignment_id = Column(Integer, primary_key=True)
    driver_id = Column(
        Integer,
        ForeignKey("driver.employee_id"),
        nullable=False
    )
    vehicle_id = Column(
        Integer,
        ForeignKey("vehicle.vehicle_id"),
        nullable=False
    )
    assigned_from = Column(Date, nullable=False)
    assigned_to = Column(Date)

    __table_args__ = (
        CheckConstraint("assigned_to IS NULL OR assigned_to >= assigned_from", name="chk_assignment_dates"),
    )


class VehicleMaintenance(Base):
    __tablename__ = "vehicle_maintenance"

    maintenance_id = Column(Integer, primary_key=True)
    vehicle_id = Column(
        Integer,
        ForeignKey("vehicle.vehicle_id"),
        nullable=False
    )
    maintenance_date = Column(Date, nullable=False)
    maintenance_type = Column(String(50), nullable=False)
    cost = Column(Numeric(10, 2), nullable=False)
    description = Column(String(255))

    __table_args__ = (
        CheckConstraint("cost >= 0", name="chk_maintenance_cost"),
    )


class Warehouse(Base):
    __tablename__ = "warehouse"

    warehouse_id = Column(Integer, primary_key=True)
    warehouse_name = Column(String(100), nullable=False)
    address = Column(String(255), nullable=False)
    city = Column(String(50), nullable=False)
    capacity = Column(Numeric(12, 2))
    manager_employee_id = Column(
        Integer,
        ForeignKey("employee.employee_id")
    )
    status = Column(String(30), default="ACTIVE", server_default="ACTIVE")

    __table_args__ = (
        CheckConstraint("capacity IS NULL OR capacity > 0", name="chk_warehouse_capacity"),
    )


class Product(Base):
    __tablename__ = "product"

    product_id = Column(Integer, primary_key=True)
    product_name = Column(String(100), nullable=False)
    category = Column(String(50))
    unit_price = Column(Numeric(10, 2), nullable=False)
    weight = Column(Numeric(10, 2))
    description = Column(String(255))

    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="chk_product_price"),
        CheckConstraint("weight IS NULL OR weight > 0", name="chk_product_weight"),
    )


class Inventory(Base):
    __tablename__ = "inventory"

    warehouse_id = Column(
        Integer,
        ForeignKey("warehouse.warehouse_id"),
        nullable=False
    )
    product_id = Column(
        Integer,
        ForeignKey("product.product_id"),
        nullable=False
    )
    quantity = Column(Integer, nullable=False, default=0, server_default=text("0"))
    reorder_level = Column(Integer, nullable=False, default=0, server_default=text("0"))
    last_updated = Column(TIMESTAMP, server_default=NOW)

    __table_args__ = (
        PrimaryKeyConstraint("warehouse_id", "product_id"),
        CheckConstraint("quantity >= 0", name="chk_inventory_quantity"),
        CheckConstraint("reorder_level >= 0", name="chk_inventory_reorder"),
        Index("idx_inventory_product", "product_id"),
    )


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True)
    customer_id = Column(
        Integer,
        ForeignKey("customer.customer_id"),
        nullable=False
    )
    order_date = Column(TIMESTAMP, server_default=NOW)
    order_status = Column(
        String(30),
        nullable=False,
        default="PENDING",
        server_default="PENDING"
    )
    shipping_address = Column(String(255), nullable=False)
    destination_city = Column(String(100))

    __table_args__ = (
        CheckConstraint(
            "order_status IN ('PENDING', 'CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED')",
            name="chk_order_status"
        ),
        Index("idx_orders_customer", "customer_id"),
    )


class OrderItem(Base):
    __tablename__ = "order_item"

    order_id = Column(
        Integer,
        ForeignKey("orders.order_id"),
        primary_key=True
    )
    product_id = Column(
        Integer,
        ForeignKey("product.product_id"),
        primary_key=True
    )
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_order_item_quantity"),
        CheckConstraint("unit_price >= 0", name="chk_order_item_price"),
    )


class OrderInventoryReservation(Base):
    __tablename__ = "order_inventory_reservation"

    reservation_id = Column(Integer, primary_key=True)
    order_id = Column(
        Integer,
        ForeignKey("orders.order_id"),
        nullable=False
    )
    warehouse_id = Column(
        Integer,
        ForeignKey("warehouse.warehouse_id"),
        nullable=False
    )
    product_id = Column(
        Integer,
        ForeignKey("product.product_id"),
        nullable=False
    )
    reserved_quantity = Column(Integer, nullable=False)
    created_at = Column(
        TIMESTAMP,
        nullable=False,
        server_default=NOW
    )
    # Set when the reserved stock has been returned to inventory (exactly once).
    released_at = Column(TIMESTAMP)

    __table_args__ = (
        UniqueConstraint(
            "order_id", "warehouse_id", "product_id",
            name="uq_reservation_order_warehouse_product"
        ),
        ForeignKeyConstraint(
            ["order_id", "product_id"],
            ["order_item.order_id", "order_item.product_id"]
        ),
        CheckConstraint("reserved_quantity > 0", name="chk_reservation_quantity"),
        Index("idx_reservation_warehouse_product", "warehouse_id", "product_id"),
        Index("idx_reservation_product", "product_id"),
        Index("idx_reservation_active", "order_id", postgresql_where=text("released_at IS NULL")),
    )


class Route(Base):
    __tablename__ = "route"

    route_id = Column(Integer, primary_key=True)
    route_name = Column(String(100), nullable=False)
    source = Column(String(100), nullable=False)
    destination = Column(String(100), nullable=False)
    distance_km = Column(Numeric(10, 2), nullable=False)
    estimated_duration = Column(Interval)
    route_status = Column(String(30), default="ACTIVE", server_default="ACTIVE")

    __table_args__ = (
        CheckConstraint("distance_km > 0", name="chk_route_distance"),
    )


class Shipment(Base):
    __tablename__ = "shipment"

    shipment_id = Column(Integer, primary_key=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.order_id"),
        nullable=False
    )

    warehouse_id = Column(
        Integer,
        ForeignKey("warehouse.warehouse_id"),
        nullable=False
    )

    # Optional since migration 007: a shipment does not need a configured route.
    route_id = Column(
        Integer,
        ForeignKey("route.route_id"),
        nullable=True
    )

    shipment_date = Column(TIMESTAMP, server_default=NOW)
    estimated_delivery = Column(TIMESTAMP)
    actual_delivery = Column(TIMESTAMP)

    shipment_status = Column(
        String(30),
        nullable=False,
        default="CREATED",
        server_default="CREATED"
    )

    __table_args__ = (
        # Migration 004: lets shipment_item reference the (shipment, order) pair.
        UniqueConstraint("shipment_id", "order_id", name="uq_shipment_id_order"),
        CheckConstraint(
            "actual_delivery IS NULL OR actual_delivery >= shipment_date",
            name="chk_shipment_dates"
        ),
        CheckConstraint(
            "shipment_status IN ('CREATED', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED')",
            name="chk_shipment_status"
        ),
        Index("idx_shipment_status", "shipment_status"),
        # Migration 002: at most one non-cancelled shipment per order.
        Index(
            "uq_shipment_order_active",
            "order_id",
            unique=True,
            postgresql_where=text("shipment_status <> 'CANCELLED'")
        ),
    )


class ShipmentItem(Base):
    __tablename__ = "shipment_item"

    shipment_id = Column(
        Integer,
        ForeignKey("shipment.shipment_id"),
        primary_key=True
    )

    order_id = Column(
        Integer,
        nullable=False
    )

    product_id = Column(
        Integer,
        primary_key=True
    )

    quantity = Column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "product_id"],
            ["order_item.order_id", "order_item.product_id"]
        ),
        # Migration 004: the item's order must be the shipment's own order.
        ForeignKeyConstraint(
            ["shipment_id", "order_id"],
            ["shipment.shipment_id", "shipment.order_id"],
            name="fk_shipment_item_shipment_order"
        ),
        CheckConstraint("quantity > 0", name="chk_shipment_item_quantity"),
    )


class ShipmentTracking(Base):
    __tablename__ = "shipment_tracking"

    tracking_id = Column(Integer, primary_key=True)

    shipment_id = Column(
        Integer,
        ForeignKey("shipment.shipment_id"),
        nullable=False
    )

    status = Column(String(50), nullable=False)
    location = Column(String(150))
    tracking_timestamp = Column(TIMESTAMP, server_default=NOW)
    remarks = Column(String(255))

    __table_args__ = (
        Index("idx_tracking_shipment", "shipment_id"),
    )


class Delivery(Base):
    __tablename__ = "delivery"

    delivery_id = Column(Integer, primary_key=True)

    shipment_id = Column(
        Integer,
        ForeignKey("shipment.shipment_id"),
        nullable=False,
        unique=True
    )

    driver_id = Column(
        Integer,
        ForeignKey("driver.employee_id"),
        nullable=False
    )

    delivery_date = Column(TIMESTAMP)

    delivery_status = Column(
        String(30),
        nullable=False,
        default="PENDING",
        server_default="PENDING"
    )

    delivery_address = Column(String(255), nullable=False)

    # Added by migration 005. NULL for deliveries recorded before then (never captured).
    vehicle_id = Column(Integer, ForeignKey("vehicle.vehicle_id"))
    assigned_at = Column(TIMESTAMP, server_default=NOW)

    __table_args__ = (
        CheckConstraint(
            "delivery_status IN ('PENDING', 'OUT_FOR_DELIVERY', 'DELIVERED', 'FAILED', 'CANCELLED')",
            name="chk_delivery_status"
        ),
        Index("idx_delivery_vehicle", "vehicle_id"),
        Index("idx_delivery_driver_status", "driver_id", "delivery_status"),
    )


class Payment(Base):
    __tablename__ = "payment"

    payment_id = Column(Integer, primary_key=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.order_id"),
        nullable=False,
        unique=True
    )

    amount = Column(Numeric(12, 2), nullable=False)
    payment_method = Column(String(30), nullable=False)

    payment_status = Column(
        String(30),
        nullable=False,
        default="PENDING",
        server_default="PENDING"
    )

    payment_date = Column(TIMESTAMP, server_default=NOW)
    transaction_reference = Column(String(100), unique=True)

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_payment_amount"),
        CheckConstraint(
            "payment_status IN ('PENDING', 'SUCCESS', 'FAILED', 'REFUNDED')",
            name="chk_payment_status"
        ),
    )


class Invoice(Base):
    __tablename__ = "invoice"

    invoice_id = Column(Integer, primary_key=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.order_id"),
        nullable=False,
        unique=True
    )

    invoice_date = Column(TIMESTAMP, server_default=NOW)
    subtotal = Column(Numeric(12, 2), nullable=False)
    tax = Column(Numeric(12, 2), nullable=False, default=0, server_default=text("0"))
    total_amount = Column(Numeric(12, 2), nullable=False)
    invoice_status = Column(
        String(30),
        nullable=False,
        default="ISSUED",
        server_default="ISSUED"
    )

    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="chk_invoice_subtotal"),
        CheckConstraint("tax >= 0", name="chk_invoice_tax"),
        CheckConstraint("total_amount >= 0", name="chk_invoice_total"),
        CheckConstraint("total_amount = subtotal + tax", name="chk_invoice_calculation"),
    )


class OrderFulfilment(Base):
    """One planning record per order placed through checkout (migration 005)."""
    __tablename__ = "order_fulfilment"

    order_id = Column(Integer, ForeignKey("orders.order_id"), primary_key=True)
    fulfilment_status = Column(String(30), nullable=False)
    reason_code = Column(String(50))
    reason_detail = Column(String(500))
    origin_warehouse_id = Column(Integer, ForeignKey("warehouse.warehouse_id"))
    route_id = Column(Integer, ForeignKey("route.route_id"))
    route_basis = Column(String(30))
    selection_note = Column(String(1000))
    planned_at = Column(TIMESTAMP, nullable=False, server_default=NOW)
    updated_at = Column(TIMESTAMP, nullable=False, server_default=NOW)
    approved_at = Column(TIMESTAMP)
    approved_by_user_id = Column(Integer, ForeignKey("users.user_id"))

    __table_args__ = (
        CheckConstraint(
            "fulfilment_status IN ('PLANNED', 'BLOCKED', 'AWAITING_ASSIGNMENT', 'ASSIGNED', 'CANCELLED')",
            name="chk_fulfilment_status"
        ),
        CheckConstraint(
            "route_basis IS NULL OR route_basis IN ('DESTINATION_CITY', 'ADDRESS_TEXT')",
            name="chk_fulfilment_route_basis"
        ),
        Index("idx_fulfilment_status", "fulfilment_status"),
        Index("idx_fulfilment_warehouse", "origin_warehouse_id"),
    )


class OrderFulfilmentEvent(Base):
    """Append-only audit trail of planning and allocation decisions (migration 005)."""
    __tablename__ = "order_fulfilment_event"

    event_id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.order_id"), nullable=False)
    shipment_id = Column(Integer, ForeignKey("shipment.shipment_id"))
    event_type = Column(String(40), nullable=False)
    detail = Column(String(500))
    actor_user_id = Column(Integer, ForeignKey("users.user_id"))
    created_at = Column(TIMESTAMP, nullable=False, server_default=NOW)

    __table_args__ = (
        Index("idx_fulfilment_event_order", "order_id", "event_id"),
    )


class DemoSeedRecord(Base):
    """Rows added by the development demo seed (migration 006); never written by the application."""
    __tablename__ = "demo_seed_record"

    entity = Column(String(30), primary_key=True)
    entity_key = Column(String(100), primary_key=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=NOW)
