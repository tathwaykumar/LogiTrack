from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey, Date, Numeric, PrimaryKeyConstraint, Interval, ForeignKeyConstraint, UniqueConstraint, Index, text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Role(Base):
    __tablename__ = "role"

    role_id = Column(Integer, primary_key=True, index=True)
    role_name = Column(String(50), nullable=False, unique=True)
    description = Column(String(255))


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("role.role_id"), nullable=False)
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP)
    is_active = Column(Boolean, default=True)

class Customer(Base):
    __tablename__ = "customer"

    customer_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    address = Column(String(255))
    created_at = Column(TIMESTAMP)

class Employee(Base):
    __tablename__ = "employee"

    employee_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), unique=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20))
    department = Column(String(50))
    hire_date = Column(Date)
    salary = Column(Numeric(10, 2))
    employment_status = Column(String(30), default="ACTIVE")


class Driver(Base):
    __tablename__ = "driver"

    employee_id = Column(
        Integer,
        ForeignKey("employee.employee_id"),
        primary_key=True
    )
    license_no = Column(String(50), nullable=False, unique=True)
    license_expiry = Column(Date, nullable=False)
    availability_status = Column(String(30), default="AVAILABLE")

class Vehicle(Base):
    __tablename__ = "vehicle"

    vehicle_id = Column(Integer, primary_key=True, index=True)
    registration_no = Column(String(30), nullable=False, unique=True)
    vehicle_type = Column(String(50), nullable=False)
    capacity = Column(Numeric(10, 2), nullable=False)
    fuel_type = Column(String(30))
    status = Column(String(30), default="ACTIVE")
    purchase_date = Column(Date)

class DriverVehicleAssignment(Base):
    __tablename__ = "driver_vehicle_assignment"

    assignment_id = Column(Integer, primary_key=True, index=True)
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

class VehicleMaintenance(Base):
    __tablename__ = "vehicle_maintenance"

    maintenance_id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(
        Integer,
        ForeignKey("vehicle.vehicle_id"),
        nullable=False
    )
    maintenance_date = Column(Date, nullable=False)
    maintenance_type = Column(String(50), nullable=False)
    cost = Column(Numeric(10, 2), nullable=False)
    description = Column(String(255))

class Warehouse(Base):
    __tablename__ = "warehouse"

    warehouse_id = Column(Integer, primary_key=True, index=True)
    warehouse_name = Column(String(100), nullable=False)
    address = Column(String(255), nullable=False)
    city = Column(String(50), nullable=False)
    capacity = Column(Numeric(12, 2))
    manager_employee_id = Column(
        Integer,
        ForeignKey("employee.employee_id")
    )
    status = Column(String(30), default="ACTIVE")

class Product(Base):
    __tablename__ = "product"

    product_id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String(100), nullable=False)
    category = Column(String(50))
    unit_price = Column(Numeric(10, 2), nullable=False)
    weight = Column(Numeric(10, 2))
    description = Column(String(255))

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
    quantity = Column(Integer, nullable=False, default=0)
    reorder_level = Column(Integer, nullable=False, default=0)
    last_updated = Column(TIMESTAMP)

    __table_args__ = (
        PrimaryKeyConstraint("warehouse_id", "product_id"),
    )

class Order(Base):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customer.customer_id"),
        nullable=False
    )
    order_date = Column(TIMESTAMP)
    order_status = Column(
        String(30),
        nullable=False,
        default="PENDING"
    )
    shipping_address = Column(String(255), nullable=False)

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

class OrderInventoryReservation(Base):
    __tablename__ = "order_inventory_reservation"

    reservation_id = Column(Integer, primary_key=True, index=True)
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
        server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        UniqueConstraint(
            "order_id", "warehouse_id", "product_id",
            name="uq_reservation_order_warehouse_product"
        ),
        ForeignKeyConstraint(
            ["order_id", "product_id"],
            ["order_item.order_id", "order_item.product_id"]
        ),
    )

class Route(Base):
    __tablename__ = "route"

    route_id = Column(Integer, primary_key=True, index=True)
    route_name = Column(String(100), nullable=False)
    source = Column(String(100), nullable=False)
    destination = Column(String(100), nullable=False)
    distance_km = Column(Numeric(10, 2), nullable=False)
    estimated_duration = Column(Interval)
    route_status = Column(String(30), default="ACTIVE")

class Shipment(Base):
    __tablename__ = "shipment"

    shipment_id = Column(Integer, primary_key=True, index=True)

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

    route_id = Column(
        Integer,
        ForeignKey("route.route_id"),
        nullable=False
    )

    shipment_date = Column(TIMESTAMP)
    estimated_delivery = Column(TIMESTAMP)
    actual_delivery = Column(TIMESTAMP)

    shipment_status = Column(
        String(30),
        nullable=False,
        default="CREATED"
    )

    __table_args__ = (
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
    )

class ShipmentTracking(Base):
    __tablename__ = "shipment_tracking"

    tracking_id = Column(Integer, primary_key=True, index=True)

    shipment_id = Column(
        Integer,
        ForeignKey("shipment.shipment_id"),
        nullable=False
    )

    status = Column(String(50), nullable=False)
    location = Column(String(150))
    tracking_timestamp = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"))
    remarks = Column(String(255))

class Delivery(Base):
    __tablename__ = "delivery"

    delivery_id = Column(Integer, primary_key=True, index=True)

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
        default="PENDING"
    )

    delivery_address = Column(String(255), nullable=False)

class Payment(Base):
    __tablename__ = "payment"

    payment_id = Column(Integer, primary_key=True, index=True)

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
        default="PENDING"
    )

    payment_date = Column(TIMESTAMP)
    transaction_reference = Column(String(100), unique=True)

class Invoice(Base):
    __tablename__ = "invoice"

    invoice_id = Column(Integer, primary_key=True, index=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.order_id"),
        nullable=False,
        unique=True
    )

    invoice_date = Column(TIMESTAMP)
    subtotal = Column(Numeric(12, 2), nullable=False)
    tax = Column(Numeric(12, 2), nullable=False, default=0)
    total_amount = Column(Numeric(12, 2), nullable=False)
    invoice_status = Column(
        String(30),
        nullable=False,
        default="ISSUED"
    )
