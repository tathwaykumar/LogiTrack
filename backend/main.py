import re
from datetime import date, datetime

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pwdlib.exceptions import UnknownHashError
from pydantic import BaseModel, Field
from sqlalchemy import case, exists, func, or_, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, aliased

from auth import hash_password, verify_password
from jwt_utils import create_access_token, decode_access_token
from models import (
    Customer, Delivery, Driver, DriverVehicleAssignment, Employee, Inventory,
    Invoice, Order, OrderInventoryReservation, OrderItem, Payment, Product,
    Role, Route, Shipment,
    ShipmentItem, ShipmentTracking, User, Vehicle, VehicleMaintenance, Warehouse,
)

from database import get_db

app = FastAPI(title="LogiTrack API")
security = HTTPBearer()
TRACKING_STATUSES = {
    "CREATED", "PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"
}
# Partial unique index: one non-cancelled shipment per order.
ACTIVE_SHIPMENT_INDEX = "uq_shipment_order_active"
ACTIVE_SHIPMENT_CONFLICT = "This order already has an active (non-cancelled) shipment"


def is_active_shipment_conflict(error: IntegrityError) -> bool:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == ACTIVE_SHIPMENT_INDEX


# Status rules. The shipment status (advanced by tracking events) is the source of
# truth and the delivery status is derived from it. The database enforces the same
# rules (migration 003, SQLSTATE LT409); these checks give clear 409s up front.
SHIPMENT_FLOW = ["CREATED", "PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"]
TERMINAL_SHIPMENT_STATUSES = {"DELIVERED", "CANCELLED"}
DELIVERY_STATUSES = {"PENDING", "OUT_FOR_DELIVERY", "DELIVERED", "FAILED", "CANCELLED"}
STATUS_CONFLICT_SQLSTATE = "LT409"


def delivery_status_for_shipment(shipment_status: str) -> str:
    if shipment_status in ("OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"):
        return shipment_status
    return "PENDING"


def shipment_transition_error(shipment_id: int, current: str, new: str) -> str | None:
    """Return why current -> new is not allowed, or None when it is allowed."""
    if current in TERMINAL_SHIPMENT_STATUSES:
        return f"Shipment {shipment_id} is {current} and accepts no further status updates."
    if new == "CANCELLED" or new == current:
        return None
    if SHIPMENT_FLOW.index(new) < SHIPMENT_FLOW.index(current):
        return f"Shipment {shipment_id} cannot move back from {current} to {new}."
    return None


def is_status_conflict(error: Exception) -> bool:
    return getattr(getattr(error, "orig", None), "pgcode", None) == STATUS_CONFLICT_SQLSTATE


def status_conflict_detail(error: Exception) -> str:
    diag = getattr(getattr(error, "orig", None), "diag", None)
    return getattr(diag, "message_primary", None) or "This status change is not allowed."


def lock_shipment(db: Session, shipment_id: int):
    """Lock the shipment row so concurrent status updates are serialised."""
    return (
        db.query(Shipment)
        .filter(Shipment.shipment_id == shipment_id)
        .with_for_update()
        .populate_existing()
        .first()
    )


def record_tracking_event(db: Session, shipment: Shipment, status: str, location=None, remarks=None):
    """Validate and add a tracking event for a locked shipment.

    The database trigger then moves the shipment status and syncs the delivery.
    """
    problem = shipment_transition_error(shipment.shipment_id, shipment.shipment_status, status)
    if problem:
        raise HTTPException(status_code=409, detail=problem)
    event = ShipmentTracking(
        shipment_id=shipment.shipment_id,
        status=status,
        location=location,
        tracking_timestamp=datetime.now(),
        remarks=remarks,
    )
    # Flushed by commit_status_change(), which maps trigger violations to 409.
    db.add(event)
    return event


def commit_status_change(db: Session):
    """Commit, mapping database status-rule and uniqueness violations to 409."""
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if is_active_shipment_conflict(error):
            raise HTTPException(status_code=409, detail=ACTIVE_SHIPMENT_CONFLICT)
        raise
    except DBAPIError as error:
        db.rollback()
        if is_status_conflict(error):
            raise HTTPException(status_code=409, detail=status_conflict_detail(error))
        raise

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    token = credentials.credentials

    try:
        payload = decode_access_token(token)

        return {
            "user_id": payload["user_id"],
            "username": payload["username"],
            "role_id": payload["role_id"]
        }

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
def require_roles(*allowed_roles):
    def role_checker(
        current_user: dict = Security(get_current_user),
        db: Session = Depends(get_db)
    ):
        role = db.query(Role).filter(
            Role.role_id == current_user["role_id"]
        ).first()

        if not role:
            raise HTTPException(
                status_code=403,
                detail="Role not found"
            )

        if role.role_name not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this resource"
            )

        return current_user

    return role_checker
class OrderCreate(BaseModel):
    customer_id: int
    order_status: str = "PENDING"
    shipping_address: str

class OrderItemCreate(BaseModel):
    order_id: int
    product_id: int
    quantity: int
    unit_price: float


class ShopCheckoutItem(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=10000)

    class Config:
        extra = "forbid"


class ShopCheckoutRequest(BaseModel):
    items: list[ShopCheckoutItem] = Field(min_length=1, max_length=50)
    shipping_address: str = Field(min_length=1, max_length=255)

    class Config:
        extra = "forbid"


class ProfileUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=50)
    email: str | None = Field(default=None, min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    current_password: str | None = Field(default=None, max_length=128)

    class Config:
        extra = "forbid"


def profile_response(user: User, db: Session):
    customer = db.query(Customer).filter(Customer.user_id == user.user_id).first()
    employee = db.query(Employee).filter(Employee.user_id == user.user_id).first()
    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "profile_type": "CUSTOMER" if customer else "EMPLOYEE" if employee else None,
        "name": customer.name if customer else employee.name if employee else None,
        "phone": customer.phone if customer else employee.phone if employee else None,
        "address": customer.address if customer else None,
    }


@app.get("/")
def root():
    return {
        "message": "LogiTrack API is running"
    }


@app.get("/profile")
def get_profile(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.user_id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")
    return profile_response(user, db)


@app.patch("/profile")
def update_profile(
    updates: ProfileUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.user_id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")

    if updates.username is not None:
        username = updates.username.strip()
        if not username:
            raise HTTPException(status_code=422, detail="Username cannot be blank")
        duplicate = db.query(User).filter(User.username == username, User.user_id != user.user_id).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Username is already in use")
        user.username = username

    if updates.email is not None:
        email = updates.email.strip()
        if not email or "@" not in email:
            raise HTTPException(status_code=422, detail="Enter a valid email address")
        duplicate = db.query(User).filter(User.email == email, User.user_id != user.user_id).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Email is already in use")
        user.email = email

    if updates.password is not None:
        if not updates.current_password:
            raise HTTPException(status_code=422, detail="Current password is required to set a new password")
        try:
            password_is_valid = verify_password(updates.current_password, user.password_hash)
        except UnknownHashError:
            password_is_valid = False
        if not password_is_valid:
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        user.password_hash = hash_password(updates.password)

    customer = db.query(Customer).filter(Customer.user_id == user.user_id).first()
    employee = db.query(Employee).filter(Employee.user_id == user.user_id).first()
    if updates.name is not None:
        name = updates.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name cannot be blank")
        if customer:
            customer.name = name
        elif employee:
            employee.name = name
        else:
            raise HTTPException(status_code=422, detail="This account has no editable profile name")
    if updates.phone is not None:
        if customer:
            customer.phone = updates.phone.strip() or None
        elif employee:
            employee.phone = updates.phone.strip() or None
        else:
            raise HTTPException(status_code=422, detail="This account has no editable profile phone")
    if updates.address is not None:
        if not customer:
            raise HTTPException(status_code=422, detail="Address is available only for customer profiles")
        customer.address = updates.address.strip() or None

    db.commit()
    db.refresh(user)
    return profile_response(user, db)


@app.get("/db-test")
def database_test(
    current_user: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db)
):
    result = db.execute(text("SELECT 1"))
    return {
        "database": "connected",
        "result": result.scalar()
    }

@app.get("/roles")
def get_roles(
    current_user: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db)
):
    roles = db.query(Role).all()

    return [
        {
            "role_id": role.role_id,
            "role_name": role.role_name,
            "description": role.description
        }
        for role in roles
    ]
@app.get("/customers")
def get_customers(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    customers = db.query(Customer).all()

    return [
        {
            "customer_id": customer.customer_id,
            "user_id": customer.user_id,
            "name": customer.name,
            "phone": customer.phone,
            "address": customer.address
        }
        for customer in customers
    ]

@app.get("/customers/{customer_id}")
def get_customer(
    customer_id: int,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    customer = (
        db.query(Customer)
        .filter(Customer.customer_id == customer_id)
        .first()
    )

    if not customer:
        return {"error": "Customer not found"}

    return {
        "customer_id": customer.customer_id,
        "user_id": customer.user_id,
        "name": customer.name,
        "phone": customer.phone,
        "address": customer.address
    }


@app.get("/orders")
def get_orders(
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER", "CUSTOMER")
    ),
    db: Session = Depends(get_db)
):
    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if role.role_name in ["ADMIN", "OPERATIONS_MANAGER"]:
        orders = db.query(Order).all()
    else:
        customer = db.query(Customer).filter(
            Customer.user_id == current_user["user_id"]
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer profile not found"
            )

        orders = db.query(Order).filter(
            Order.customer_id == customer.customer_id
        ).all()

    result = []

    for order in orders:
        items = (
            db.query(OrderItem, Product)
            .join(
                Product,
                OrderItem.product_id == Product.product_id
            )
            .filter(OrderItem.order_id == order.order_id)
            .all()
        )

        result.append({
            "order_id": order.order_id,
            "customer_id": order.customer_id,
            "order_status": order.order_status,
            "shipping_address": order.shipping_address,
            "items": [
                {
                    "product_id": item.product_id,
                    "product_name": product.product_name,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                    "item_total": float(
                        item.quantity * item.unit_price
                    )
                }
                for item, product in items
            ]
        })

    return result
@app.get("/orders/{order_id}")
def get_order_details(
    order_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(
        Order.order_id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    # Get user's role
    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if not role:
        raise HTTPException(
            status_code=403,
            detail="Role not found"
        )

    # CUSTOMER can only access their own orders
    if role.role_name == "CUSTOMER":

        customer = db.query(Customer).filter(
            Customer.user_id == current_user["user_id"]
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer profile not found"
            )

        if order.customer_id != customer.customer_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this order"
            )

    items = db.query(OrderItem).filter(
        OrderItem.order_id == order_id
    ).all()

    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "order_status": order.order_status,
        "shipping_address": order.shipping_address,
        "items": [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price
            }
            for item in items
        ]
    }
@app.get("/orders/{order_id}/total")
def get_order_total(
    order_id: int,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER", "CUSTOMER")
    ),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(
        Order.order_id == order_id
    ).first()

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    # Get user's role
    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if not role:
        raise HTTPException(
            status_code=403,
            detail="Role not found"
        )

    # CUSTOMER can only calculate the total of their own order
    if role.role_name == "CUSTOMER":

        customer = db.query(Customer).filter(
            Customer.user_id == current_user["user_id"]
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer profile not found"
            )

        if order.customer_id != customer.customer_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this order"
            )

    # Call PostgreSQL stored function
    result = db.execute(
        text("SELECT calculate_order_total(:order_id)"),
        {"order_id": order_id}
    )

    total = result.scalar()

    return {
        "order_id": order_id,
        "total": float(total or 0)
    }

@app.post("/orders")
def create_order(
    order_data: OrderCreate,
    authorized_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER", "CUSTOMER")
    ),
    db: Session = Depends(get_db)
):
    role = db.query(Role).filter(
        Role.role_id == authorized_user["role_id"]
    ).first()

    # CUSTOMER can only create an order for themselves
    if role.role_name == "CUSTOMER":

        customer = db.query(Customer).filter(
            Customer.user_id == authorized_user["user_id"]
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer profile not found"
            )

        customer_id = customer.customer_id

    # ADMIN and OPERATIONS_MANAGER can create orders for any customer
    else:
        customer = db.query(Customer).filter(
            Customer.customer_id == order_data.customer_id
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer not found"
            )

        customer_id = order_data.customer_id

    new_order = Order(
        customer_id=customer_id,
        order_status=order_data.order_status,
        shipping_address=order_data.shipping_address
    )

    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    return {
        "message": "Order created successfully",
        "order_id": new_order.order_id,
        "customer_id": new_order.customer_id,
        "order_status": new_order.order_status,
        "shipping_address": new_order.shipping_address
    }

@app.post("/order-items")
def create_order_item(
    item: OrderItemCreate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    new_item = OrderItem(
        order_id=item.order_id,
        product_id=item.product_id,
        quantity=item.quantity,
        unit_price=item.unit_price
    )

    db.add(new_item)
    db.commit()
    db.refresh(new_item)

    return {
        "message": "Order item created successfully",
        "order_id": new_item.order_id,
        "product_id": new_item.product_id,
        "quantity": new_item.quantity,
        "unit_price": new_item.unit_price
    }

@app.get("/shipments")
def get_shipments(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get user's role
    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if not role:
        raise HTTPException(
            status_code=403,
            detail="Role not found"
        )

    # CUSTOMER can only see shipments belonging to their orders
    if role.role_name == "CUSTOMER":

        customer = db.query(Customer).filter(
            Customer.user_id == current_user["user_id"]
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer profile not found"
            )

        shipments = (
            db.query(Shipment)
            .join(
                Order,
                Shipment.order_id == Order.order_id
            )
            .filter(
                Order.customer_id == customer.customer_id
            )
            .all()
        )

    elif role.role_name == "DRIVER":
        employee = db.query(Employee).filter(
            Employee.user_id == current_user["user_id"]
        ).first()

        if not employee:
            raise HTTPException(status_code=404, detail="Driver profile not found")

        shipments = (
            db.query(Shipment)
            .join(Delivery, Delivery.shipment_id == Shipment.shipment_id)
            .filter(Delivery.driver_id == employee.employee_id)
            .all()
        )
    else:
        # ADMIN and OPERATIONS_MANAGER can see all shipments
        shipments = db.query(Shipment).all()

    return [
        {
            "shipment_id": shipment.shipment_id,
            "order_id": shipment.order_id,
            "warehouse_id": shipment.warehouse_id,
            "route_id": shipment.route_id,
            "shipment_date": shipment.shipment_date,
            "estimated_delivery": shipment.estimated_delivery,
            "actual_delivery": shipment.actual_delivery,
            "shipment_status": shipment.shipment_status
        }
        for shipment in shipments
    ]

@app.get("/shipment-details")
def get_shipment_details(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    results = (
        db.query(
            Shipment.shipment_id,
            Order.order_id,
            Customer.name.label("customer_name"),
            Warehouse.warehouse_name,
            Route.route_name,
            Shipment.shipment_status
        )
        .join(Order, Shipment.order_id == Order.order_id)
        .join(Customer, Order.customer_id == Customer.customer_id)
        .join(Warehouse, Shipment.warehouse_id == Warehouse.warehouse_id)
        .join(Route, Shipment.route_id == Route.route_id)
        .all()
    )

    return [
        {
            "shipment_id": row.shipment_id,
            "order_id": row.order_id,
            "customer_name": row.customer_name,
            "warehouse_name": row.warehouse_name,
            "route_name": row.route_name,
            "shipment_status": row.shipment_status
        }
        for row in results
    ]

@app.get("/tracking/{shipment_id}")
def get_tracking(
    shipment_id: int,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    tracking = (
        db.query(ShipmentTracking)
        .filter(ShipmentTracking.shipment_id == shipment_id)
        .order_by(ShipmentTracking.tracking_id)  # insertion order = order the status trigger applied
        .all()
    )

    return [
        {
            "tracking_id": item.tracking_id,
            "shipment_id": item.shipment_id,
            "status": item.status,
            "location": item.location,
            "tracking_timestamp": item.tracking_timestamp,
            "remarks": item.remarks
        }
        for item in tracking
    ]

@app.get("/deliveries")
def get_deliveries(
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER", "DRIVER", "CUSTOMER")
    ),
    db: Session = Depends(get_db)
):
    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if role.role_name == "DRIVER":
        employee = db.query(Employee).filter(
            Employee.user_id == current_user["user_id"]
        ).first()

        if not employee:
            raise HTTPException(
                status_code=404,
                detail="Driver profile not found"
            )

        deliveries = db.query(Delivery).filter(
            Delivery.driver_id == employee.employee_id
        ).all()
    elif role.role_name == "CUSTOMER":
        customer = db.query(Customer).filter(
            Customer.user_id == current_user["user_id"]
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer profile not found"
            )

        deliveries = (
            db.query(Delivery)
            .join(Shipment, Delivery.shipment_id == Shipment.shipment_id)
            .join(Order, Shipment.order_id == Order.order_id)
            .filter(Order.customer_id == customer.customer_id)
            .all()
        )
    else:
        deliveries = db.query(Delivery).all()

    return [
        {
            "delivery_id": delivery.delivery_id,
            "shipment_id": delivery.shipment_id,
            "driver_id": delivery.driver_id,
            "delivery_date": delivery.delivery_date,
            "delivery_status": delivery.delivery_status,
            "delivery_address": delivery.delivery_address
        }
        for delivery in deliveries
    ]

@app.get("/payments")
def get_payments(
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER", "CUSTOMER")
    ),
    db: Session = Depends(get_db)
):
    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if role.role_name == "CUSTOMER":
        customer = db.query(Customer).filter(
            Customer.user_id == current_user["user_id"]
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer profile not found"
            )

        payments = (
            db.query(Payment)
            .join(Order, Payment.order_id == Order.order_id)
            .filter(Order.customer_id == customer.customer_id)
            .all()
        )
    else:
        payments = db.query(Payment).all()

    return [
        {
            "payment_id": payment.payment_id,
            "order_id": payment.order_id,
            "amount": payment.amount,
            "payment_method": payment.payment_method,
            "payment_status": payment.payment_status,
            "payment_date": payment.payment_date,
            "transaction_reference": payment.transaction_reference
        }
        for payment in payments
    ]

@app.get("/invoices")
def get_invoices(
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER", "CUSTOMER")
    ),
    db: Session = Depends(get_db)
):
    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if role.role_name == "CUSTOMER":
        customer = db.query(Customer).filter(
            Customer.user_id == current_user["user_id"]
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer profile not found"
            )

        invoices = (
            db.query(Invoice)
            .join(Order, Invoice.order_id == Order.order_id)
            .filter(Order.customer_id == customer.customer_id)
            .all()
        )
    else:
        invoices = db.query(Invoice).all()

    return [
        {
            "invoice_id": invoice.invoice_id,
            "order_id": invoice.order_id,
            "invoice_date": invoice.invoice_date,
            "subtotal": invoice.subtotal,
            "tax": invoice.tax,
            "total_amount": invoice.total_amount,
            "invoice_status": invoice.invoice_status
        }
        for invoice in invoices
    ]

@app.get("/inventory")
def get_inventory(current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")), db: Session = Depends(get_db)):
    inventory = db.query(Inventory).all()

    return [
        {
            "warehouse_id": item.warehouse_id,
            "product_id": item.product_id,
            "quantity": item.quantity,
            "reorder_level": item.reorder_level,
            "last_updated": item.last_updated
        }
        for item in inventory
    ]

@app.get("/products")
def get_products(current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER", "DRIVER", "CUSTOMER")), db: Session = Depends(get_db)):
    products = db.query(Product).all()

    return [
        {
            "product_id": product.product_id,
            "product_name": product.product_name,
            "category": product.category,
            "unit_price": product.unit_price,
            "weight": product.weight,
            "description": product.description
        }
        for product in products
    ]


@app.get("/shop/products")
def get_shop_products(
    current_user: dict = Depends(require_roles("CUSTOMER")),
    db: Session = Depends(get_db),
):
    """Return the customer catalog with stock aggregated from existing inventory."""
    products = (
        db.query(
            Product,
            func.coalesce(func.sum(Inventory.quantity), 0).label("available_stock"),
        )
        .outerjoin(Inventory, Inventory.product_id == Product.product_id)
        .group_by(Product.product_id)
        .order_by(Product.product_name)
        .all()
    )

    return [
        {
            "product_id": product.product_id,
            "product_name": product.product_name,
            "category": product.category,
            "unit_price": float(product.unit_price),
            "weight": float(product.weight) if product.weight is not None else None,
            "description": product.description,
            "available_stock": int(available_stock),
        }
        for product, available_stock in products
    ]


@app.post("/shop/checkout", status_code=201)
def checkout_shop_order(
    checkout: ShopCheckoutRequest,
    current_user: dict = Depends(require_roles("CUSTOMER")),
    db: Session = Depends(get_db),
):
    """Create an order and receipt while locking inventory against overselling."""
    shipping_address = checkout.shipping_address.strip()
    if not shipping_address:
        raise HTTPException(status_code=422, detail="Shipping address is required")

    requested_quantities: dict[int, int] = {}
    for item in checkout.items:
        requested_quantities[item.product_id] = (
            requested_quantities.get(item.product_id, 0) + item.quantity
        )

    if any(quantity > 10000 for quantity in requested_quantities.values()):
        raise HTTPException(status_code=422, detail="Requested quantity is too large")

    customer = db.query(Customer).filter(
        Customer.user_id == current_user["user_id"]
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")

    try:
        product_details = {}
        inventory_allocations = {}

        # Lock products and inventory in product/warehouse order. This prevents
        # two concurrent checkouts from consuming the same remaining stock.
        for product_id in sorted(requested_quantities):
            product = (
                db.query(Product)
                .filter(Product.product_id == product_id)
                .with_for_update()
                .first()
            )
            if not product:
                raise HTTPException(
                    status_code=404,
                    detail=f"Product {product_id} was not found",
                )

            inventory_rows = (
                db.query(Inventory)
                .filter(
                    Inventory.product_id == product_id,
                    Inventory.quantity > 0,
                )
                .order_by(Inventory.warehouse_id)
                .with_for_update()
                .all()
            )
            available_stock = sum(row.quantity for row in inventory_rows)
            required_quantity = requested_quantities[product_id]
            if available_stock < required_quantity:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Insufficient stock for {product.product_name}. "
                        f"Only {available_stock} available."
                    ),
                )

            remaining = required_quantity
            allocations = []
            for row in inventory_rows:
                amount = min(row.quantity, remaining)
                if amount:
                    allocations.append((row, amount))
                    remaining -= amount
                if remaining == 0:
                    break

            product_details[product_id] = product
            inventory_allocations[product_id] = allocations

        order = Order(
            customer_id=customer.customer_id,
            order_date=datetime.now(),
            order_status="PENDING",
            shipping_address=shipping_address,
        )
        db.add(order)
        db.flush()

        receipt_items = []
        for product_id in sorted(requested_quantities):
            product = product_details[product_id]
            quantity = requested_quantities[product_id]
            order_item = OrderItem(
                order_id=order.order_id,
                product_id=product_id,
                quantity=quantity,
                unit_price=product.unit_price,
            )
            db.add(order_item)
            # Reservations reference order_item, so it must exist first.
            db.flush()

            # Deduct stock and record exactly where it came from in the same
            # transaction, so a failed checkout rolls back both together.
            for inventory_row, amount in inventory_allocations[product_id]:
                inventory_row.quantity -= amount
                inventory_row.last_updated = datetime.now()
                db.add(OrderInventoryReservation(
                    order_id=order.order_id,
                    warehouse_id=inventory_row.warehouse_id,
                    product_id=product_id,
                    reserved_quantity=amount,
                ))

            receipt_items.append({
                "product_id": product_id,
                "product_name": product.product_name,
                "quantity": quantity,
                "unit_price": float(product.unit_price),
                "item_total": float(product.unit_price * quantity),
            })

        db.flush()
        subtotal = db.execute(
            text("SELECT calculate_order_total(:order_id)"),
            {"order_id": order.order_id},
        ).scalar() or 0

        invoice = Invoice(
            order_id=order.order_id,
            invoice_date=datetime.now(),
            subtotal=subtotal,
            tax=0,
            total_amount=subtotal,
            invoice_status="ISSUED",
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The order could not be completed. Please refresh and try again.",
        )
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Order placed successfully. Payment is pending.",
        "order": {
            "order_id": order.order_id,
            "order_status": order.order_status,
            "shipping_address": order.shipping_address,
            "items": receipt_items,
        },
        "invoice": {
            "invoice_id": invoice.invoice_id,
            "invoice_status": invoice.invoice_status,
            "subtotal": float(invoice.subtotal),
            "tax": float(invoice.tax),
            "total_amount": float(invoice.total_amount),
        },
    }


class SimulatedPaymentRequest(BaseModel):
    order_id: int = Field(gt=0)
    outcome: str = Field(min_length=1, max_length=20)

    class Config:
        extra = "forbid"


@app.get("/shop/payment-orders")
def get_shop_payment_orders(
    current_user: dict = Depends(require_roles("CUSTOMER")),
    db: Session = Depends(get_db),
):
    customer = db.query(Customer).filter(
        Customer.user_id == current_user["user_id"]
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")

    records = (
        db.query(Order, Invoice, Payment)
        .join(Invoice, Invoice.order_id == Order.order_id)
        .outerjoin(Payment, Payment.order_id == Order.order_id)
        .filter(
            Order.customer_id == customer.customer_id,
            Order.order_status == "PENDING",
        )
        .order_by(Order.order_date.desc(), Order.order_id.desc())
        .all()
    )

    return [
        {
            "order_id": order.order_id,
            "order_status": order.order_status,
            "invoice_id": invoice.invoice_id,
            "invoice_status": invoice.invoice_status,
            "total_amount": float(invoice.total_amount),
            "payment_id": payment.payment_id if payment else None,
            "payment_status": payment.payment_status if payment else None,
        }
        for order, invoice, payment in records
    ]


SIMULATION_MODE = "DEVELOPMENT_ONLY_SIMULATION"
DRIVER_AVAILABLE_STATUS = "AVAILABLE"
# Vehicle status has no CHECK constraint: seed data uses ACTIVE and the
# vehicle screen uses AVAILABLE for the same "in service" meaning.
ELIGIBLE_VEHICLE_STATUSES = ("ACTIVE", "AVAILABLE")
OPEN_DELIVERY_STATUSES = ("PENDING", "OUT_FOR_DELIVERY")


def find_eligible_driver(db: Session, today: date):
    """Return (driver_id, vehicle_id) for the least-loaded eligible driver, or None.

    Eligible means: driver AVAILABLE with an unexpired licence, employee ACTIVE
    (and login not disabled), and a current vehicle assignment to an in-service
    vehicle that is not concurrently assigned to a different driver.
    """
    other_assignment = aliased(DriverVehicleAssignment)
    vehicle_shared = exists().where(
        other_assignment.vehicle_id == DriverVehicleAssignment.vehicle_id,
        other_assignment.driver_id != DriverVehicleAssignment.driver_id,
        other_assignment.assigned_from <= today,
        or_(other_assignment.assigned_to.is_(None), other_assignment.assigned_to >= today),
    )
    open_deliveries = (
        select(func.count(Delivery.delivery_id))
        .where(
            Delivery.driver_id == Driver.employee_id,
            Delivery.delivery_status.in_(OPEN_DELIVERY_STATUSES),
        )
        .correlate(Driver)
        .scalar_subquery()
    )

    def eligible_query():
        return (
            db.query(Driver.employee_id, DriverVehicleAssignment.vehicle_id)
            .join(Employee, Employee.employee_id == Driver.employee_id)
            .outerjoin(User, User.user_id == Employee.user_id)
            .join(DriverVehicleAssignment, DriverVehicleAssignment.driver_id == Driver.employee_id)
            .join(Vehicle, Vehicle.vehicle_id == DriverVehicleAssignment.vehicle_id)
            .filter(
                Driver.availability_status == DRIVER_AVAILABLE_STATUS,
                Driver.license_expiry >= today,
                Employee.employment_status == "ACTIVE",
                or_(Employee.user_id.is_(None), func.coalesce(User.is_active, True)),
                DriverVehicleAssignment.assigned_from <= today,
                or_(
                    DriverVehicleAssignment.assigned_to.is_(None),
                    DriverVehicleAssignment.assigned_to >= today,
                ),
                Vehicle.status.in_(ELIGIBLE_VEHICLE_STATUSES),
                ~vehicle_shared,
            )
        )

    candidates = (
        eligible_query()
        .order_by(open_deliveries, Driver.employee_id, DriverVehicleAssignment.vehicle_id)
        .all()
    )
    for driver_id, vehicle_id in candidates:
        # Lock, then re-check, so a concurrent status change cannot slip
        # between choosing the driver and recording the delivery.
        db.query(Driver).filter(Driver.employee_id == driver_id).with_for_update().first()
        db.query(Vehicle).filter(Vehicle.vehicle_id == vehicle_id).with_for_update().first()
        still_eligible = eligible_query().filter(
            Driver.employee_id == driver_id,
            DriverVehicleAssignment.vehicle_id == vehicle_id,
        ).first()
        if still_eligible:
            return driver_id, vehicle_id

    return None


def assign_eligible_driver(db: Session, shipment: Shipment, delivery_address: str):
    """Create the delivery for a shipment if an eligible driver exists; never fabricate one."""
    candidate = find_eligible_driver(db, date.today())
    if not candidate:
        return None

    driver_id, vehicle_id = candidate
    delivery = Delivery(
        shipment_id=shipment.shipment_id,
        driver_id=driver_id,
        delivery_address=delivery_address,
        delivery_status="PENDING",
    )
    db.add(delivery)
    db.flush()
    return {
        "delivery_id": delivery.delivery_id,
        "driver_id": driver_id,
        "vehicle_id": vehicle_id,
    }


def normalise_place(value: str) -> str:
    """Lower-case, turn punctuation into spaces, drop trailing PIN/postal digits."""
    words = re.sub(r"[^\w\s]|_", " ", value.lower()).split()
    while words and words[-1].isdigit():
        words.pop()
    return " ".join(words)


def address_mentions_city(shipping_address: str, city: str) -> bool:
    """True when a comma/line-separated address part ends with the city name.

    Matching whole trailing words means "Flat 3, Chennai - 600040" and
    "VIT University Vellore" name their city, while a street such as
    "12 Bangalore Road" does not name Bangalore.
    """
    target = normalise_place(city)
    if not target:
        return False
    for part in re.split(r"[,;\n]", shipping_address):
        segment = normalise_place(part)
        if segment == target or segment.endswith(" " + target):
            return True
    return False


def select_route(db: Session, origin_city: str, shipping_address: str):
    """Return the single active route from the origin city to the destination
    city named in the shipping address, or None when there is no match or the
    match is ambiguous. Never falls back to an unrelated route."""
    routes = (
        db.query(Route)
        .filter(
            func.lower(func.trim(Route.source)) == origin_city.strip().lower(),
            Route.route_status == "ACTIVE",
        )
        .order_by(Route.route_id)
        .all()
    )
    matches = [
        route for route in routes
        if address_mentions_city(shipping_address, route.destination)
    ]
    return matches[0] if len(matches) == 1 else None


def unfulfilled(status: str, message: str):
    return {
        "status": status,
        "message": message,
        "shipment_id": None,
        "shipment_status": None,
        "origin_warehouse_id": None,
        "driver_id": None,
        "vehicle_id": None,
    }


def fulfilment_summary(db: Session, order: Order):
    """Describe the existing fulfilment state of an order without changing it."""
    shipment = (
        db.query(Shipment)
        .filter(
            Shipment.order_id == order.order_id,
            Shipment.shipment_status != "CANCELLED",
        )
        .first()
    )
    if not shipment:
        return unfulfilled(
            "NOT_FULFILLED",
            "No shipment exists for this order yet. Operations follow-up is required.",
        )

    delivery = db.query(Delivery).filter(Delivery.shipment_id == shipment.shipment_id).first()
    return {
        "status": "DRIVER_ASSIGNED" if delivery else "PENDING_ASSIGNMENT",
        "message": (
            "Shipment created and driver assigned." if delivery
            else "Shipment created and awaiting driver assignment."
        ),
        "shipment_id": shipment.shipment_id,
        "shipment_status": shipment.shipment_status,
        "origin_warehouse_id": shipment.warehouse_id,
        "driver_id": delivery.driver_id if delivery else None,
        "vehicle_id": None,
    }


def fulfil_paid_order(db: Session, order: Order):
    """Create the single shipment for a paid order from its recorded reservations.

    The caller must hold a row lock on the order, which serialises repeated or
    concurrent requests. Nothing is fabricated: when the sourcing record or a
    route is missing, the paid order stays CONFIRMED with no shipment so that
    operations can follow up.
    """
    # uq_shipment_order_active also enforces this in the database.
    active_shipment = db.query(Shipment.shipment_id).filter(
        Shipment.order_id == order.order_id,
        Shipment.shipment_status != "CANCELLED",
    ).first()
    if active_shipment:
        return fulfilment_summary(db, order)

    reservations = (
        db.query(OrderInventoryReservation)
        .filter(OrderInventoryReservation.order_id == order.order_id)
        .order_by(OrderInventoryReservation.warehouse_id, OrderInventoryReservation.product_id)
        .all()
    )
    if not reservations:
        return unfulfilled(
            "RESERVATION_MISSING",
            "No inventory reservation is recorded for this order, so no shipment was created. "
            "Operations follow-up is required.",
        )

    ordered_quantities = {
        item.product_id: item.quantity
        for item in db.query(OrderItem).filter(OrderItem.order_id == order.order_id).all()
    }
    reserved_quantities: dict[int, int] = {}
    units_by_warehouse: dict[int, int] = {}
    for reservation in reservations:
        reserved_quantities[reservation.product_id] = (
            reserved_quantities.get(reservation.product_id, 0) + reservation.reserved_quantity
        )
        units_by_warehouse[reservation.warehouse_id] = (
            units_by_warehouse.get(reservation.warehouse_id, 0) + reservation.reserved_quantity
        )
    if reserved_quantities != ordered_quantities:
        return unfulfilled(
            "RESERVATION_INCOMPLETE",
            "Recorded inventory reservations do not match the order items, so no shipment "
            "was created. Operations follow-up is required.",
        )

    # The schema allows one origin per shipment; use the warehouse that
    # supplied the most units. Every source stays recorded in the reservations.
    origin_id = min(units_by_warehouse, key=lambda wid: (-units_by_warehouse[wid], wid))
    warehouse = db.query(Warehouse).filter(Warehouse.warehouse_id == origin_id).first()
    route = select_route(db, warehouse.city, order.shipping_address)
    if not route:
        return unfulfilled(
            "ROUTE_UNAVAILABLE",
            f"No single active route from {warehouse.city} matches the destination city in "
            "the shipping address, so no shipment was created. Operations follow-up is required.",
        )

    now = datetime.now()
    shipment = Shipment(
        order_id=order.order_id,
        warehouse_id=origin_id,
        route_id=route.route_id,
        shipment_date=now,
        estimated_delivery=now + route.estimated_duration if route.estimated_duration else None,
        shipment_status="CREATED",
    )
    db.add(shipment)
    db.flush()

    for product_id, quantity in sorted(ordered_quantities.items()):
        db.add(ShipmentItem(
            shipment_id=shipment.shipment_id,
            order_id=order.order_id,
            product_id=product_id,
            quantity=quantity,
        ))

    assignment = assign_eligible_driver(db, shipment, order.shipping_address)

    remarks = []
    if len(units_by_warehouse) > 1:
        remarks.append(
            "Consolidated from warehouses "
            + ", ".join(str(wid) for wid in sorted(units_by_warehouse))
        )
    remarks.append("Driver assigned" if assignment else "Awaiting driver assignment")
    db.add(ShipmentTracking(
        shipment_id=shipment.shipment_id,
        status="CREATED",
        location=f"{warehouse.warehouse_name}, {warehouse.city}"[:150],
        tracking_timestamp=now,
        remarks="; ".join(remarks)[:255],
    ))

    if assignment:
        order.order_status = "PROCESSING"
    db.flush()

    return {
        "status": "DRIVER_ASSIGNED" if assignment else "PENDING_ASSIGNMENT",
        "message": (
            "Shipment created and driver assigned." if assignment
            else "Shipment created. No eligible driver and vehicle are available yet, "
            "so it is awaiting assignment."
        ),
        "shipment_id": shipment.shipment_id,
        "shipment_status": "CREATED",
        "origin_warehouse_id": origin_id,
        "source_warehouse_ids": sorted(units_by_warehouse),
        "driver_id": assignment["driver_id"] if assignment else None,
        "vehicle_id": assignment["vehicle_id"] if assignment else None,
    }


@app.post("/shop/payments/simulate")
def simulate_shop_payment(
    request: SimulatedPaymentRequest,
    current_user: dict = Depends(require_roles("CUSTOMER")),
    db: Session = Depends(get_db),
):
    """Development-only simulated payment. It never contacts a payment provider."""
    outcome = request.outcome.strip().upper()
    if outcome not in {"SUCCESS", "FAILED"}:
        raise HTTPException(
            status_code=422,
            detail="Simulation outcome must be SUCCESS or FAILED",
        )

    customer = db.query(Customer).filter(
        Customer.user_id == current_user["user_id"]
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")

    try:
        order = (
            db.query(Order)
            .filter(
                Order.order_id == request.order_id,
                Order.customer_id == customer.customer_id,
            )
            .with_for_update()
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        invoice = (
            db.query(Invoice)
            .filter(Invoice.order_id == order.order_id)
            .with_for_update()
            .first()
        )
        if not invoice:
            raise HTTPException(status_code=409, detail="Order receipt invoice is missing")

        payment = (
            db.query(Payment)
            .filter(Payment.order_id == order.order_id)
            .with_for_update()
            .first()
        )

        if payment and payment.payment_status == "SUCCESS":
            if outcome != "SUCCESS":
                raise HTTPException(
                    status_code=409,
                    detail="A successful simulated payment cannot be changed to failed",
                )
            # Repeated success is a read-only no-op: no new shipment or reservation.
            fulfilment = fulfilment_summary(db, order)
            return {
                "message": "This simulated payment was already successful.",
                "mode": SIMULATION_MODE,
                "already_processed": True,
                "fulfilment": fulfilment,
                "payment_id": payment.payment_id,
                "payment_status": payment.payment_status,
                "order_id": order.order_id,
                "order_status": order.order_status,
                "invoice_id": invoice.invoice_id,
                "invoice_status": invoice.invoice_status,
                "total_amount": float(payment.amount),
            }

        total = db.execute(
            text("SELECT calculate_order_total(:order_id)"),
            {"order_id": order.order_id},
        ).scalar() or 0

        if payment is None:
            payment = Payment(
                order_id=order.order_id,
                amount=total,
                payment_method="SIMULATED_TEST_MODE",
                payment_status=outcome,
                payment_date=datetime.now(),
                transaction_reference=f"SIM-{order.order_id}",
            )
            db.add(payment)
        else:
            payment.amount = total
            payment.payment_method = "SIMULATED_TEST_MODE"
            payment.payment_status = outcome
            payment.payment_date = datetime.now()

        if outcome == "SUCCESS":
            if order.order_status != "PENDING":
                raise HTTPException(
                    status_code=409,
                    detail="This order cannot be paid in its current status",
                )
            order.order_status = "CONFIRMED"
            invoice.invoice_status = "PAID"
            db.flush()
            # Shipment, items, tracking and driver assignment commit together
            # with the payment, or not at all.
            fulfilment = fulfil_paid_order(db, order)
        else:
            if order.order_status != "PENDING":
                raise HTTPException(
                    status_code=409,
                    detail="This order cannot receive another simulated payment result",
                )
            invoice.invoice_status = "ISSUED"
            fulfilment = None

        db.commit()
        db.refresh(payment)
        db.refresh(order)
        db.refresh(invoice)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Payment simulation could not be completed")
    except Exception:
        db.rollback()
        raise

    return {
        "message": f"Simulated payment {outcome.lower()}.",
        "mode": SIMULATION_MODE,
        "already_processed": False,
        "fulfilment": fulfilment,
        "payment_id": payment.payment_id,
        "payment_status": payment.payment_status,
        "order_id": order.order_id,
        "order_status": order.order_status,
        "invoice_id": invoice.invoice_id,
        "invoice_status": invoice.invoice_status,
        "total_amount": float(payment.amount),
    }


@app.post("/shipments/{shipment_id}/assign-driver")
def assign_shipment_driver(
    shipment_id: int,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db),
):
    """Assign an eligible driver to a shipment that is awaiting assignment."""
    try:
        shipment = db.query(Shipment).filter(Shipment.shipment_id == shipment_id).first()
        if not shipment:
            raise HTTPException(status_code=404, detail="Shipment not found")

        # Same lock order as payment fulfilment: order first, then shipment.
        order = (
            db.query(Order)
            .filter(Order.order_id == shipment.order_id)
            .with_for_update()
            .first()
        )
        shipment = (
            db.query(Shipment)
            .filter(Shipment.shipment_id == shipment_id)
            .with_for_update()
            .populate_existing()
            .first()
        )

        existing = db.query(Delivery).filter(Delivery.shipment_id == shipment_id).first()
        if existing:
            return {
                "message": "Shipment already has a driver assigned",
                "already_assigned": True,
                "shipment_id": shipment_id,
                "delivery_id": existing.delivery_id,
                "driver_id": existing.driver_id,
                "vehicle_id": None,
                "order_id": order.order_id,
                "order_status": order.order_status,
            }

        if shipment.shipment_status != "CREATED":
            raise HTTPException(
                status_code=409,
                detail="Only shipments awaiting dispatch can be assigned a driver",
            )
        if order.order_status not in ("CONFIRMED", "PROCESSING"):
            raise HTTPException(
                status_code=409,
                detail="This order cannot be assigned a driver in its current status",
            )

        assignment = assign_eligible_driver(db, shipment, order.shipping_address)
        if not assignment:
            raise HTTPException(
                status_code=409,
                detail="No eligible driver and vehicle are available. The shipment remains awaiting assignment.",
            )

        if order.order_status == "CONFIRMED":
            order.order_status = "PROCESSING"
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="The shipment was assigned concurrently. Please refresh.")
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Driver assigned successfully",
        "already_assigned": False,
        "shipment_id": shipment_id,
        "delivery_id": assignment["delivery_id"],
        "driver_id": assignment["driver_id"],
        "vehicle_id": assignment["vehicle_id"],
        "order_id": order.order_id,
        "order_status": order.order_status,
    }


@app.get("/warehouses")
def get_warehouses(current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")), db: Session = Depends(get_db)):
    warehouses = db.query(Warehouse).all()

    return [
        {
            "warehouse_id": warehouse.warehouse_id,
            "warehouse_name": warehouse.warehouse_name,
            "address": warehouse.address,
            "city": warehouse.city,
            "capacity": warehouse.capacity,
            "manager_employee_id": warehouse.manager_employee_id,
            "status": warehouse.status
        }
        for warehouse in warehouses
    ]

@app.get("/employees")
def get_employees(current_user: dict = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    employees = db.query(Employee).all()

    return [
        {
            "employee_id": employee.employee_id,
            "user_id": employee.user_id,
            "name": employee.name,
            "phone": employee.phone,
            "department": employee.department,
            "hire_date": employee.hire_date,
            "salary": employee.salary,
            "employment_status": employee.employment_status
        }
        for employee in employees
    ]

@app.get("/drivers")
def get_drivers(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    drivers = (
        db.query(Driver, Employee)
        .join(Employee, Driver.employee_id == Employee.employee_id)
        .order_by(Employee.name)
        .all()
    )

    return [
        {
            "employee_id": driver.employee_id,
            "name": employee.name,
            "phone": employee.phone,
            "department": employee.department,
            "hire_date": employee.hire_date,
            "employment_status": employee.employment_status,
            "license_no": driver.license_no,
            "license_expiry": driver.license_expiry,
            "availability_status": driver.availability_status
        }
        for driver, employee in drivers
    ]


@app.get("/drivers/me")
def get_my_driver_profile(
    current_user: dict = Depends(require_roles("DRIVER")),
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(
        Employee.user_id == current_user["user_id"]
    ).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Driver profile not found")

    driver = db.query(Driver).filter(
        Driver.employee_id == employee.employee_id
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")

    return [{
        "employee_id": driver.employee_id,
        "name": employee.name,
        "phone": employee.phone,
        "department": employee.department,
        "hire_date": employee.hire_date,
        "employment_status": employee.employment_status,
        "license_no": driver.license_no,
        "license_expiry": driver.license_expiry,
        "availability_status": driver.availability_status
    }]

@app.get("/vehicles")
def get_vehicles(
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    vehicles = db.query(Vehicle).all()

    return [
        {
            "vehicle_id": vehicle.vehicle_id,
            "registration_no": vehicle.registration_no,
            "vehicle_type": vehicle.vehicle_type,
            "capacity": vehicle.capacity,
            "fuel_type": vehicle.fuel_type,
            "status": vehicle.status,
            "purchase_date": vehicle.purchase_date
        }
        for vehicle in vehicles
    ]

@app.get("/assignments")
def get_assignments(
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER", "DRIVER")
    ),
    db: Session = Depends(get_db)
):
    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if role.role_name == "DRIVER":
        employee = db.query(Employee).filter(
            Employee.user_id == current_user["user_id"]
        ).first()

        if not employee:
            raise HTTPException(
                status_code=404,
                detail="Driver profile not found"
            )

        assignments = db.query(DriverVehicleAssignment).filter(
            DriverVehicleAssignment.driver_id == employee.employee_id
        ).all()
    else:
        assignments = db.query(DriverVehicleAssignment).all()

    return [
        {
            "assignment_id": assignment.assignment_id,
            "driver_id": assignment.driver_id,
            "vehicle_id": assignment.vehicle_id,
            "assigned_from": assignment.assigned_from,
            "assigned_to": assignment.assigned_to
        }
        for assignment in assignments
    ]

@app.get("/maintenance")
def get_maintenance(current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")), db: Session = Depends(get_db)):
    maintenance_records = db.query(VehicleMaintenance).all()

    return [
        {
            "maintenance_id": record.maintenance_id,
            "vehicle_id": record.vehicle_id,
            "maintenance_date": record.maintenance_date,
            "maintenance_type": record.maintenance_type,
            "cost": record.cost,
            "description": record.description
        }
        for record in maintenance_records
    ]

@app.get("/routes")
def get_routes(current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER", "DRIVER", "CUSTOMER")), db: Session = Depends(get_db)):
    routes = db.query(Route).all()

    return [
        {
            "route_id": route.route_id,
            "route_name": route.route_name,
            "source": route.source,
            "destination": route.destination,
            "distance_km": route.distance_km,
            "estimated_duration": str(route.estimated_duration)
            if route.estimated_duration else None,
            "route_status": route.route_status
        }
        for route in routes
    ]

@app.get("/users")
def get_users(
    current_user: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db)
):
    users = (
        db.query(User, Role)
        .join(Role, User.role_id == Role.role_id)
        .order_by(User.username)
        .all()
    )

    return [
        {
            "user_id": user.user_id,
            "role_id": user.role_id,
            "role_name": role.role_name,
            "username": user.username,
            "email": user.email,
            "created_at": user.created_at,
            "is_active": user.is_active
        }
        for user, role in users
    ]

@app.get("/order-items")
def get_order_items(current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")), db: Session = Depends(get_db)):
    items = db.query(OrderItem).all()

    return [
        {
            "order_id": item.order_id,
            "product_id": item.product_id,
            "quantity": item.quantity,
            "unit_price": item.unit_price
        }
        for item in items
    ]

@app.get("/shipment-items")
def get_shipment_items(current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")), db: Session = Depends(get_db)):
    items = db.query(ShipmentItem).all()

    return [
        {
            "shipment_id": item.shipment_id,
            "order_id": item.order_id,
            "product_id": item.product_id,
            "quantity": item.quantity
        }
        for item in items
    ]
class ShipmentStatusUpdate(BaseModel):
    status: str


@app.put("/shipments/{shipment_id}/status")
def update_shipment_status(
    shipment_id: int,
    data: ShipmentStatusUpdate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    status = data.status.strip().upper()
    if status not in TRACKING_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid shipment status")

    shipment = lock_shipment(db, shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    if shipment.shipment_status == status:
        db.rollback()
        return {
            "message": "Shipment already has this status",
            "shipment_id": shipment.shipment_id,
            "status": shipment.shipment_status,
            "tracking_event_created": False
        }

    try:
        tracking_event = record_tracking_event(db, shipment, status)
    except HTTPException:
        db.rollback()
        raise
    commit_status_change(db)
    db.refresh(tracking_event)
    db.refresh(shipment)

    return {
        "message": "Shipment status updated successfully",
        "shipment_id": shipment.shipment_id,
        "status": shipment.shipment_status,
        "tracking_id": tracking_event.tracking_id,
        "tracking_timestamp": tracking_event.tracking_timestamp,
        "tracking_event_created": True
    }
class ShipmentCreate(BaseModel):
    order_id: int
    warehouse_id: int
    route_id: int
    estimated_delivery: datetime | None = None
@app.post("/shipments")
def create_shipment(
    shipment: ShipmentCreate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    # Lock the order first, as payment fulfilment does. Otherwise this insert's
    # foreign-key check and the unique index can deadlock with a payment.
    order = (
        db.query(Order)
        .filter(Order.order_id == shipment.order_id)
        .with_for_update()
        .first()
    )
    if not order:
        db.rollback()
        raise HTTPException(status_code=404, detail="Order not found")

    new_shipment = Shipment(
        order_id=shipment.order_id,
        warehouse_id=shipment.warehouse_id,
        route_id=shipment.route_id,
        estimated_delivery=shipment.estimated_delivery
    )

    db.add(new_shipment)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if is_active_shipment_conflict(error):
            raise HTTPException(status_code=409, detail=ACTIVE_SHIPMENT_CONFLICT)
        raise
    db.refresh(new_shipment)

    return {
        "message": "Shipment created successfully",
        "shipment_id": new_shipment.shipment_id,
        "order_id": new_shipment.order_id,
        "warehouse_id": new_shipment.warehouse_id,
        "route_id": new_shipment.route_id,
        "shipment_status": new_shipment.shipment_status
    }
class TrackingCreate(BaseModel):
    shipment_id: int
    status: str
    location: str | None = None
    remarks: str | None = None
@app.post("/tracking")
def create_tracking(
    tracking: TrackingCreate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER", "DRIVER")
    ),
    db: Session = Depends(get_db)
):
    shipment = db.query(Shipment).filter(
        Shipment.shipment_id == tracking.shipment_id
    ).first()

    if not shipment:
        raise HTTPException(
            status_code=404,
            detail="Shipment not found"
        )

    status = tracking.status.strip().upper()
    if status not in TRACKING_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Invalid tracking status"
        )

    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if role and role.role_name == "DRIVER":
        employee = db.query(Employee).filter(
            Employee.user_id == current_user["user_id"]
        ).first()
        assignment = employee and db.query(Delivery).filter(
            Delivery.shipment_id == shipment.shipment_id,
            Delivery.driver_id == employee.employee_id
        ).first()

        if not assignment:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to update this shipment"
            )

    shipment = lock_shipment(db, tracking.shipment_id)
    try:
        new_tracking = record_tracking_event(db, shipment, status, tracking.location, tracking.remarks)
    except HTTPException:
        db.rollback()
        raise
    commit_status_change(db)
    db.refresh(new_tracking)
    db.refresh(shipment)

    return {
        "message": "Tracking event added successfully",
        "tracking_id": new_tracking.tracking_id,
        "shipment_id": new_tracking.shipment_id,
        "status": new_tracking.status,
        "shipment_status": shipment.shipment_status,
        "location": new_tracking.location,
        "tracking_timestamp": new_tracking.tracking_timestamp,
        "remarks": new_tracking.remarks
    }
class DeliveryCreate(BaseModel):
    shipment_id: int
    driver_id: int
    delivery_address: str
    delivery_status: str = "PENDING"
@app.post("/deliveries")
def create_delivery(
    delivery: DeliveryCreate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    new_delivery = Delivery(
        shipment_id=delivery.shipment_id,
        driver_id=delivery.driver_id,
        delivery_address=delivery.delivery_address,
        delivery_status=delivery.delivery_status
    )

    db.add(new_delivery)
    commit_status_change(db)
    db.refresh(new_delivery)

    return {
        "message": "Delivery created successfully",
        "delivery_id": new_delivery.delivery_id,
        "shipment_id": new_delivery.shipment_id,
        "driver_id": new_delivery.driver_id,
        "delivery_status": new_delivery.delivery_status,
        "delivery_address": new_delivery.delivery_address
    }
class PaymentCreate(BaseModel):
    order_id: int
    amount: float
    payment_method: str
    payment_status: str = "PENDING"
    transaction_reference: str | None = None
@app.post("/payments")
def create_payment(
    payment: PaymentCreate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    new_payment = Payment(
        order_id=payment.order_id,
        amount=payment.amount,
        payment_method=payment.payment_method,
        payment_status=payment.payment_status,
        transaction_reference=payment.transaction_reference
    )

    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)

    return {
        "message": "Payment created successfully",
        "payment_id": new_payment.payment_id,
        "order_id": new_payment.order_id,
        "amount": new_payment.amount,
        "payment_method": new_payment.payment_method,
        "payment_status": new_payment.payment_status,
        "transaction_reference": new_payment.transaction_reference
    }
class InvoiceCreate(BaseModel):
    order_id: int
    subtotal: float
    tax: float
    total_amount: float
    invoice_status: str = "ISSUED"
@app.post("/invoices")
def create_invoice(
    invoice: InvoiceCreate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    new_invoice = Invoice(
        order_id=invoice.order_id,
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        total_amount=invoice.total_amount,
        invoice_status=invoice.invoice_status
    )

    db.add(new_invoice)
    db.commit()
    db.refresh(new_invoice)

    return {
        "message": "Invoice created successfully",
        "invoice_id": new_invoice.invoice_id,
        "order_id": new_invoice.order_id,
        "subtotal": new_invoice.subtotal,
        "tax": new_invoice.tax,
        "total_amount": new_invoice.total_amount,
        "invoice_status": new_invoice.invoice_status
    }
class CustomerCreate(BaseModel):
    user_id: int
    name: str
    phone: str | None = None
    address: str | None = None
@app.post("/customers")
def create_customer(
    customer: CustomerCreate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    new_customer = Customer(
        user_id=customer.user_id,
        name=customer.name,
        phone=customer.phone,
        address=customer.address
    )

    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)

    return {
        "message": "Customer created successfully",
        "customer_id": new_customer.customer_id,
        "user_id": new_customer.user_id,
        "name": new_customer.name,
        "phone": new_customer.phone,
        "address": new_customer.address
    }
class ProductCreate(BaseModel):
    product_name: str
    category: str | None = None
    unit_price: float
    weight: float | None = None
    description: str | None = None
@app.post("/products")
def create_product(
    product: ProductCreate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    new_product = Product(
        product_name=product.product_name,
        category=product.category,
        unit_price=product.unit_price,
        weight=product.weight,
        description=product.description
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return {
        "message": "Product created successfully",
        "product_id": new_product.product_id,
        "product_name": new_product.product_name,
        "category": new_product.category,
        "unit_price": new_product.unit_price,
        "weight": new_product.weight,
        "description": new_product.description
    }
class InventoryCreate(BaseModel):
    warehouse_id: int
    product_id: int
    quantity: int
    reorder_level: int = 0
@app.post("/inventory")
def create_inventory(
    inventory: InventoryCreate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    new_inventory = Inventory(
        warehouse_id=inventory.warehouse_id,
        product_id=inventory.product_id,
        quantity=inventory.quantity,
        reorder_level=inventory.reorder_level
    )

    db.add(new_inventory)
    db.commit()
    db.refresh(new_inventory)

    return {
        "message": "Inventory created successfully",
        "warehouse_id": new_inventory.warehouse_id,
        "product_id": new_inventory.product_id,
        "quantity": new_inventory.quantity,
        "reorder_level": new_inventory.reorder_level
    }
class WarehouseCreate(BaseModel):
    warehouse_name: str
    address: str
    city: str
    capacity: float | None = None
    manager_employee_id: int | None = None
    status: str = "ACTIVE"
@app.post("/warehouses")
def create_warehouse(
    warehouse: WarehouseCreate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    new_warehouse = Warehouse(
        warehouse_name=warehouse.warehouse_name,
        address=warehouse.address,
        city=warehouse.city,
        capacity=warehouse.capacity,
        manager_employee_id=warehouse.manager_employee_id,
        status=warehouse.status
    )

    db.add(new_warehouse)
    db.commit()
    db.refresh(new_warehouse)

    return {
        "message": "Warehouse created successfully",
        "warehouse_id": new_warehouse.warehouse_id,
        "warehouse_name": new_warehouse.warehouse_name,
        "address": new_warehouse.address,
        "city": new_warehouse.city,
        "capacity": new_warehouse.capacity,
        "manager_employee_id": new_warehouse.manager_employee_id,
        "status": new_warehouse.status
    }
class EmployeeCreate(BaseModel):
    user_id: int | None = None
    name: str
    phone: str | None = None
    department: str | None = None
    hire_date: date | None = None
    salary: float | None = None
    employment_status: str = "ACTIVE"
@app.post("/employees")
def create_employee(
    employee: EmployeeCreate,
    current_user: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db)
):
    new_employee = Employee(
        user_id=employee.user_id,
        name=employee.name,
        phone=employee.phone,
        department=employee.department,
        hire_date=employee.hire_date,
        salary=employee.salary,
        employment_status=employee.employment_status
    )

    db.add(new_employee)
    db.commit()
    db.refresh(new_employee)

    return {
        "message": "Employee created successfully",
        "employee_id": new_employee.employee_id,
        "user_id": new_employee.user_id,
        "name": new_employee.name,
        "phone": new_employee.phone,
        "department": new_employee.department,
        "hire_date": new_employee.hire_date,
        "salary": new_employee.salary,
        "employment_status": new_employee.employment_status
    }
class VehicleCreate(BaseModel):
    registration_no: str
    vehicle_type: str
    capacity: float
    fuel_type: str | None = None
    status: str = "ACTIVE"
    purchase_date: date | None = None
@app.post("/vehicles")
def create_vehicle(
    vehicle: VehicleCreate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    new_vehicle = Vehicle(
        registration_no=vehicle.registration_no,
        vehicle_type=vehicle.vehicle_type,
        capacity=vehicle.capacity,
        fuel_type=vehicle.fuel_type,
        status=vehicle.status,
        purchase_date=vehicle.purchase_date
    )

    db.add(new_vehicle)
    db.commit()
    db.refresh(new_vehicle)

    return {
        "message": "Vehicle created successfully",
        "vehicle_id": new_vehicle.vehicle_id,
        "registration_no": new_vehicle.registration_no,
        "vehicle_type": new_vehicle.vehicle_type,
        "capacity": new_vehicle.capacity,
        "fuel_type": new_vehicle.fuel_type,
        "status": new_vehicle.status,
        "purchase_date": new_vehicle.purchase_date
    }
class AssignmentCreate(BaseModel):
    driver_id: int
    vehicle_id: int
    assigned_from: date
    assigned_to: date | None = None
@app.post("/assignments")
def create_assignment(
    assignment: AssignmentCreate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    new_assignment = DriverVehicleAssignment(
        driver_id=assignment.driver_id,
        vehicle_id=assignment.vehicle_id,
        assigned_from=assignment.assigned_from,
        assigned_to=assignment.assigned_to
    )

    db.add(new_assignment)
    db.commit()
    db.refresh(new_assignment)

    return {
        "message": "Vehicle assignment created successfully",
        "assignment_id": new_assignment.assignment_id,
        "driver_id": new_assignment.driver_id,
        "vehicle_id": new_assignment.vehicle_id,
        "assigned_from": new_assignment.assigned_from,
        "assigned_to": new_assignment.assigned_to
    }
class MaintenanceCreate(BaseModel):
    vehicle_id: int
    maintenance_date: date
    maintenance_type: str
    cost: float
    description: str | None = None
@app.post("/maintenance")
def create_maintenance(
    maintenance: MaintenanceCreate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    new_maintenance = VehicleMaintenance(
        vehicle_id=maintenance.vehicle_id,
        maintenance_date=maintenance.maintenance_date,
        maintenance_type=maintenance.maintenance_type,
        cost=maintenance.cost,
        description=maintenance.description
    )

    db.add(new_maintenance)
    db.commit()
    db.refresh(new_maintenance)

    return {
        "message": "Vehicle maintenance record created successfully",
        "maintenance_id": new_maintenance.maintenance_id,
        "vehicle_id": new_maintenance.vehicle_id,
        "maintenance_date": new_maintenance.maintenance_date,
        "maintenance_type": new_maintenance.maintenance_type,
        "cost": new_maintenance.cost,
        "description": new_maintenance.description
    }
class RouteCreate(BaseModel):
    route_name: str
    source: str
    destination: str
    distance_km: float
    estimated_duration: str | None = None
    route_status: str = "ACTIVE"
@app.post("/routes")
def create_route(
    route: RouteCreate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    new_route = Route(
        route_name=route.route_name,
        source=route.source,
        destination=route.destination,
        distance_km=route.distance_km,
        estimated_duration=route.estimated_duration,
        route_status=route.route_status
    )

    db.add(new_route)
    db.commit()
    db.refresh(new_route)

    return {
        "message": "Route created successfully",
        "route_id": new_route.route_id,
        "route_name": new_route.route_name,
        "source": new_route.source,
        "destination": new_route.destination,
        "distance_km": new_route.distance_km,
        "estimated_duration": new_route.estimated_duration,
        "route_status": new_route.route_status
    }
class DriverCreate(BaseModel):
    employee_id: int
    license_no: str
    license_expiry: date
    availability_status: str = "AVAILABLE"
@app.post("/drivers")
def create_driver(
    driver: DriverCreate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    new_driver = Driver(
        employee_id=driver.employee_id,
        license_no=driver.license_no,
        license_expiry=driver.license_expiry,
        availability_status=driver.availability_status
    )

    db.add(new_driver)
    db.commit()
    db.refresh(new_driver)

    return {
        "message": "Driver created successfully",
        "employee_id": new_driver.employee_id,
        "license_no": new_driver.license_no,
        "license_expiry": new_driver.license_expiry,
        "availability_status": new_driver.availability_status
    }
class ShipmentItemCreate(BaseModel):
    shipment_id: int
    order_id: int
    product_id: int
    quantity: int
@app.post("/shipment-items")
def create_shipment_item(
    item: ShipmentItemCreate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    new_item = ShipmentItem(
        shipment_id=item.shipment_id,
        order_id=item.order_id,
        product_id=item.product_id,
        quantity=item.quantity
    )

    db.add(new_item)
    db.commit()
    db.refresh(new_item)

    return {
        "message": "Shipment item created successfully",
        "shipment_id": new_item.shipment_id,
        "order_id": new_item.order_id,
        "product_id": new_item.product_id,
        "quantity": new_item.quantity
    }
class UserCreate(BaseModel):
    role_id: int
    username: str
    email: str
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True
@app.post("/users")
def create_user(
    user: UserCreate,
    current_user: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db)
):
    role = db.query(Role).filter(Role.role_id == user.role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    existing_user = db.query(User).filter(
        (User.username == user.username) | (User.email == user.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="A user with that username or email already exists"
        )

    new_user = User(
        role_id=user.role_id,
        username=user.username,
        email=user.email,
        password_hash=hash_password(user.password),
        is_active=user.is_active
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "User created successfully",
        "user_id": new_user.user_id,
        "role_id": new_user.role_id,
        "username": new_user.username,
        "email": new_user.email,
        "is_active": new_user.is_active
    }
class RoleCreate(BaseModel):
    role_name: str
    description: str | None = None
@app.post("/roles")
def create_role(
    role: RoleCreate,
    current_user: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db)
):
    new_role = Role(
        role_name=role.role_name,
        description=role.description
    )

    db.add(new_role)
    db.commit()
    db.refresh(new_role)

    return {
        "message": "Role created successfully",
        "role_id": new_role.role_id,
        "role_name": new_role.role_name,
        "description": new_role.description
    }
class OrderStatusUpdate(BaseModel):
    order_status: str
@app.put("/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.order_id == order_id).first()

    if not order:
        return {"error": "Order not found"}

    order.order_status = data.order_status

    db.commit()
    db.refresh(order)

    return {
        "message": "Order status updated successfully",
        "order_id": order.order_id,
        "order_status": order.order_status
    }
class PaymentStatusUpdate(BaseModel):
    payment_status: str
@app.put("/payments/{payment_id}/status")
def update_payment_status(
    payment_id: int,
    data: PaymentStatusUpdate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    payment = db.query(Payment).filter(
        Payment.payment_id == payment_id
    ).first()

    if not payment:
        return {"error": "Payment not found"}

    payment.payment_status = data.payment_status

    db.commit()
    db.refresh(payment)

    return {
        "message": "Payment status updated successfully",
        "payment_id": payment.payment_id,
        "payment_status": payment.payment_status
    }
class DeliveryStatusUpdate(BaseModel):
    delivery_status: str
@app.put("/deliveries/{delivery_id}/status")
def update_delivery_status(
    delivery_id: int,
    data: DeliveryStatusUpdate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER", "DRIVER")
    ),
    db: Session = Depends(get_db)
):
    status = data.delivery_status.strip().upper()
    if status not in DELIVERY_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid delivery status")

    delivery = db.query(Delivery).filter(
        Delivery.delivery_id == delivery_id
    ).first()

    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")

    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if role.role_name == "DRIVER":
        employee = db.query(Employee).filter(
            Employee.user_id == current_user["user_id"]
        ).first()

        if not employee or delivery.driver_id != employee.employee_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to update this delivery"
            )

    # The shipment status is the source of truth: lock it, then re-read the delivery.
    shipment = lock_shipment(db, delivery.shipment_id)
    db.refresh(delivery)
    tracking_event_created = False
    try:
        if delivery.delivery_status == status:
            pass
        elif delivery.delivery_status in ("DELIVERED", "CANCELLED"):
            raise HTTPException(
                status_code=409,
                detail=f"Delivery {delivery.delivery_id} is {delivery.delivery_status} and can no longer change.",
            )
        elif status in ("OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"):
            # Recorded as a tracking event so the shipment and delivery move together.
            record_tracking_event(db, shipment, status, remarks=f"Recorded via delivery #{delivery.delivery_id} status update")
            tracking_event_created = True
        elif status == "FAILED":
            if shipment.shipment_status != "OUT_FOR_DELIVERY":
                raise HTTPException(
                    status_code=409,
                    detail="A delivery attempt can only fail while the shipment is out for delivery.",
                )
            delivery.delivery_status = "FAILED"
        else:
            # PENDING is derived from the shipment; it cannot be set backwards by hand.
            raise HTTPException(
                status_code=409,
                detail=f"Delivery {delivery.delivery_id} cannot move back to PENDING while its shipment is {shipment.shipment_status}.",
            )
    except HTTPException:
        db.rollback()
        raise
    commit_status_change(db)
    db.refresh(delivery)
    db.refresh(shipment)

    return {
        "message": "Delivery status updated successfully",
        "delivery_id": delivery.delivery_id,
        "delivery_status": delivery.delivery_status,
        "shipment_id": shipment.shipment_id,
        "shipment_status": shipment.shipment_status,
        "tracking_event_created": tracking_event_created,
    }
class InventoryUpdate(BaseModel):
    quantity: int
    reorder_level: int | None = None
@app.put("/inventory/{warehouse_id}/{product_id}")
def update_inventory(
    warehouse_id: int,
    product_id: int,
    data: InventoryUpdate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    inventory = db.query(Inventory).filter(
        Inventory.warehouse_id == warehouse_id,
        Inventory.product_id == product_id
    ).first()

    if not inventory:
        return {"error": "Inventory record not found"}

    inventory.quantity = data.quantity

    if data.reorder_level is not None:
        inventory.reorder_level = data.reorder_level

    db.commit()
    db.refresh(inventory)

    return {
        "message": "Inventory updated successfully",
        "warehouse_id": inventory.warehouse_id,
        "product_id": inventory.product_id,
        "quantity": inventory.quantity,
        "reorder_level": inventory.reorder_level
    }
class VehicleStatusUpdate(BaseModel):
    status: str
@app.put("/vehicles/{vehicle_id}/status")
def update_vehicle_status(
    vehicle_id: int,
    data: VehicleStatusUpdate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    vehicle = db.query(Vehicle).filter(
        Vehicle.vehicle_id == vehicle_id
    ).first()

    if not vehicle:
        return {"error": "Vehicle not found"}

    vehicle.status = data.status

    db.commit()
    db.refresh(vehicle)

    return {
        "message": "Vehicle status updated successfully",
        "vehicle_id": vehicle.vehicle_id,
        "status": vehicle.status
    }
class DriverStatusUpdate(BaseModel):
    availability_status: str
@app.put("/drivers/{employee_id}/status")
def update_driver_status(
    employee_id: int,
    data: DriverStatusUpdate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER", "DRIVER")
    ),
    db: Session = Depends(get_db)
):
    driver = db.query(Driver).filter(
        Driver.employee_id == employee_id
    ).first()

    if not driver:
        return {"error": "Driver not found"}

    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if role.role_name == "DRIVER":
        employee = db.query(Employee).filter(
            Employee.user_id == current_user["user_id"]
        ).first()

        if not employee or driver.employee_id != employee.employee_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to update this driver"
            )

    driver.availability_status = data.availability_status

    db.commit()
    db.refresh(driver)

    return {
        "message": "Driver availability updated successfully",
        "employee_id": driver.employee_id,
        "availability_status": driver.availability_status
    }
class EmployeeStatusUpdate(BaseModel):
    employment_status: str
@app.put("/employees/{employee_id}/status")
def update_employee_status(
    employee_id: int,
    data: EmployeeStatusUpdate,
    current_user: dict = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db)
):
    employee = db.query(Employee).filter(
        Employee.employee_id == employee_id
    ).first()

    if not employee:
        return {"error": "Employee not found"}

    employee.employment_status = data.employment_status

    db.commit()
    db.refresh(employee)

    return {
        "message": "Employee status updated successfully",
        "employee_id": employee.employee_id,
        "employment_status": employee.employment_status
    }
class WarehouseStatusUpdate(BaseModel):
    status: str
@app.put("/warehouses/{warehouse_id}/status")
def update_warehouse_status(
    warehouse_id: int,
    data: WarehouseStatusUpdate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    warehouse = db.query(Warehouse).filter(
        Warehouse.warehouse_id == warehouse_id
    ).first()

    if not warehouse:
        return {"error": "Warehouse not found"}

    warehouse.status = data.status

    db.commit()
    db.refresh(warehouse)

    return {
        "message": "Warehouse status updated successfully",
        "warehouse_id": warehouse.warehouse_id,
        "status": warehouse.status
    }
class ProductPriceUpdate(BaseModel):
    unit_price: float
@app.put("/products/{product_id}/price")
def update_product_price(
    product_id: int,
    data: ProductPriceUpdate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(
        Product.product_id == product_id
    ).first()

    if not product:
        return {"error": "Product not found"}

    product.unit_price = data.unit_price

    db.commit()
    db.refresh(product)

    return {
        "message": "Product price updated successfully",
        "product_id": product.product_id,
        "product_name": product.product_name,
        "unit_price": product.unit_price
    }
class InvoiceStatusUpdate(BaseModel):
    invoice_status: str
@app.put("/invoices/{invoice_id}/status")
def update_invoice_status(
    invoice_id: int,
    data: InvoiceStatusUpdate,
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    invoice = db.query(Invoice).filter(
        Invoice.invoice_id == invoice_id
    ).first()

    if not invoice:
        return {"error": "Invoice not found"}

    invoice.invoice_status = data.invoice_status

    db.commit()
    db.refresh(invoice)

    return {
        "message": "Invoice status updated successfully",
        "invoice_id": invoice.invoice_id,
        "invoice_status": invoice.invoice_status
    }
class RouteStatusUpdate(BaseModel):
    route_status: str
@app.put("/routes/{route_id}/status")
def update_route_status(
    route_id: int,
    data: RouteStatusUpdate,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    route = db.query(Route).filter(
        Route.route_id == route_id
    ).first()

    if not route:
        return {"error": "Route not found"}

    route.route_status = data.route_status

    db.commit()
    db.refresh(route)

    return {
        "message": "Route status updated successfully",
        "route_id": route.route_id,
        "route_status": route.route_status
    }
@app.get("/orders/{order_id}/summary")
def get_order_summary(
    order_id: int,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(
        Order.order_id == order_id
    ).first()

    if not order:
        return {"error": "Order not found"}

    items = db.query(OrderItem).filter(
        OrderItem.order_id == order_id
    ).all()

    result = db.execute(
        text("SELECT calculate_order_total(:order_id)"),
        {"order_id": order_id}
    )

    total = result.scalar() or 0

    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "order_status": order.order_status,
        "shipping_address": order.shipping_address,
        "items": [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price
            }
            for item in items
        ],
        "total": float(total)
    }
@app.get("/shipments/{shipment_id}/timeline")
def get_shipment_timeline(
    shipment_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    shipment = db.query(Shipment).filter(
        Shipment.shipment_id == shipment_id
    ).first()

    if not shipment:
        raise HTTPException(
            status_code=404,
            detail="Shipment not found"
        )

    # Get user's role
    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if not role:
        raise HTTPException(
            status_code=403,
            detail="Role not found"
        )

    # CUSTOMER can only view shipments belonging to their orders
    if role.role_name == "CUSTOMER":

        customer = db.query(Customer).filter(
            Customer.user_id == current_user["user_id"]
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer profile not found"
            )

        order = db.query(Order).filter(
            Order.order_id == shipment.order_id
        ).first()

        if not order or order.customer_id != customer.customer_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this shipment"
            )
    elif role.role_name == "DRIVER":
        employee = db.query(Employee).filter(
            Employee.user_id == current_user["user_id"]
        ).first()
        assignment = employee and db.query(Delivery).filter(
            Delivery.shipment_id == shipment.shipment_id,
            Delivery.driver_id == employee.employee_id
        ).first()

        if not assignment:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this shipment"
            )

    tracking_events = db.query(ShipmentTracking).filter(
        ShipmentTracking.shipment_id == shipment_id
    ).order_by(
        ShipmentTracking.tracking_id  # insertion order = order the status trigger applied
    ).all()

    return {
        "shipment_id": shipment.shipment_id,
        "order_id": shipment.order_id,
        "shipment_status": shipment.shipment_status,
        "shipment_date": shipment.shipment_date,
        "estimated_delivery": shipment.estimated_delivery,
        "tracking_events": [
            {
                "tracking_id": event.tracking_id,
                "status": event.status,
                "location": event.location,
                "tracking_timestamp": event.tracking_timestamp,
                "remarks": event.remarks
            }
            for event in tracking_events
        ]
    }
@app.get("/orders/{order_id}/financial-summary")
def get_order_financial_summary(
    order_id: int,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(
        Order.order_id == order_id
    ).first()

    if not order:
        return {"error": "Order not found"}

    payment = db.query(Payment).filter(
        Payment.order_id == order_id
    ).first()

    invoice = db.query(Invoice).filter(
        Invoice.order_id == order_id
    ).first()

    result = db.execute(
        text("SELECT calculate_order_total(:order_id)"),
        {"order_id": order_id}
    )

    order_total = result.scalar() or 0

    return {
        "order_id": order_id,
        "calculated_order_total": float(order_total),
        "payment": {
            "payment_id": payment.payment_id if payment else None,
            "amount": float(payment.amount) if payment else None,
            "payment_method": payment.payment_method if payment else None,
            "payment_status": payment.payment_status if payment else None
        },
        "invoice": {
            "invoice_id": invoice.invoice_id if invoice else None,
            "subtotal": float(invoice.subtotal) if invoice else None,
            "tax": float(invoice.tax) if invoice else None,
            "total_amount": float(invoice.total_amount) if invoice else None,
            "invoice_status": invoice.invoice_status if invoice else None
        }
    }
@app.get("/dashboard/summary")
def get_dashboard_summary(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    total_orders = db.query(Order).count()

    total_shipments = db.query(Shipment).count()

    total_customers = db.query(Customer).count()

    total_products = db.query(Product).count()

    successful_payments = db.query(Payment).filter(
        Payment.payment_status == "SUCCESS"
    ).count()

    pending_deliveries = db.query(Delivery).filter(
        Delivery.delivery_status == "PENDING"
    ).count()

    return {
        "total_orders": total_orders,
        "total_shipments": total_shipments,
        "total_customers": total_customers,
        "total_products": total_products,
        "successful_payments": successful_payments,
        "pending_deliveries": pending_deliveries
    }
@app.get("/analytics/order-status")
def get_order_status_analytics(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    results = db.query(
        Order.order_status,
        func.count(Order.order_id).label("order_count")
    ).group_by(
        Order.order_status
    ).all()

    return [
        {
            "status": status,
            "count": count
        }
        for status, count in results
    ]
@app.get("/analytics/shipment-status")
def get_shipment_status_analytics(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    results = db.query(
        Shipment.shipment_status,
        func.count(Shipment.shipment_id).label("shipment_count")
    ).group_by(
        Shipment.shipment_status
    ).all()

    return [
        {
            "status": status,
            "count": count
        }
        for status, count in results
    ]
@app.get("/analytics/top-products")
def get_top_products(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    results = db.query(
        Product.product_id,
        Product.product_name,
        func.sum(OrderItem.quantity).label("total_quantity"),
        func.sum(
            OrderItem.quantity * OrderItem.unit_price
        ).label("total_revenue")
    ).join(
        OrderItem,
        Product.product_id == OrderItem.product_id
    ).group_by(
        Product.product_id,
        Product.product_name
    ).order_by(
        func.sum(OrderItem.quantity).desc()
    ).limit(5).all()

    return [
        {
            "product_id": product_id,
            "product_name": product_name,
            "total_quantity": total_quantity,
            "total_revenue": float(total_revenue)
        }
        for product_id, product_name, total_quantity, total_revenue in results
    ]
@app.get("/analytics/warehouse-inventory")
def get_warehouse_inventory(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    results = db.query(
        Warehouse.warehouse_name,
        Product.product_name,
        Inventory.quantity,
        Inventory.reorder_level
    ).join(
        Inventory,
        Warehouse.warehouse_id == Inventory.warehouse_id
    ).join(
        Product,
        Product.product_id == Inventory.product_id
    ).order_by(
        Warehouse.warehouse_name,
        Product.product_name
    ).all()

    return [
        {
            "warehouse": warehouse_name,
            "product": product_name,
            "quantity": quantity,
            "reorder_level": reorder_level,
            "low_stock": quantity <= reorder_level
        }
        for warehouse_name, product_name, quantity, reorder_level in results
    ]
@app.get("/analytics/driver-performance")
def get_driver_performance(
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    results = db.query(
        Driver.employee_id,
        Employee.name,
        func.count(Delivery.delivery_id).label("total_deliveries"),
        func.sum(
            case(
                (Delivery.delivery_status == "DELIVERED", 1),
                else_=0
            )
        ).label("completed_deliveries")
    ).join(
        Employee,
        Driver.employee_id == Employee.employee_id
    ).outerjoin(
        Delivery,
        Driver.employee_id == Delivery.driver_id
    ).group_by(
        Driver.employee_id,
        Employee.name
    ).order_by(
        func.count(Delivery.delivery_id).desc()
    ).all()

    return [
        {
            "driver_id": employee_id,
            "driver_name": name,
            "total_deliveries": total_deliveries,
            "completed_deliveries": completed_deliveries or 0
        }
        for employee_id, name, total_deliveries, completed_deliveries in results
    ]
@app.get("/analytics/revenue")
def get_revenue_analytics(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    result = db.query(
        func.coalesce(
            func.sum(Payment.amount),
            0
        ).label("total_revenue"),
        func.count(Payment.payment_id).label("successful_payments")
    ).filter(
        Payment.payment_status == "SUCCESS"
    ).first()

    invoice_result = db.query(
        func.coalesce(
            func.sum(Invoice.total_amount),
            0
        ).label("total_invoiced")
    ).filter(
        Invoice.invoice_status != "CANCELLED"
    ).first()

    return {
        "total_revenue": float(result.total_revenue),
        "successful_payments": result.successful_payments,
        "total_invoiced": float(invoice_result.total_invoiced)
    }
@app.get("/analytics/low-stock")
def get_low_stock_products(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    results = db.query(
        Warehouse.warehouse_name,
        Product.product_id,
        Product.product_name,
        Inventory.quantity,
        Inventory.reorder_level
    ).join(
        Inventory,
        Warehouse.warehouse_id == Inventory.warehouse_id
    ).join(
        Product,
        Product.product_id == Inventory.product_id
    ).filter(
        Inventory.quantity <= Inventory.reorder_level
    ).order_by(
        Inventory.quantity.asc()
    ).all()

    return [
        {
            "warehouse": warehouse_name,
            "product_id": product_id,
            "product": product_name,
            "quantity": quantity,
            "reorder_level": reorder_level
        }
        for warehouse_name, product_id, product_name, quantity, reorder_level in results
    ]
@app.get("/analytics/delivery-performance")
def get_delivery_performance(
    current_user: dict = Depends(
        require_roles("ADMIN", "OPERATIONS_MANAGER")
    ),
    db: Session = Depends(get_db)
):
    total = db.query(
        func.count(Delivery.delivery_id)
    ).scalar()

    delivered = db.query(
        func.count(Delivery.delivery_id)
    ).filter(
        Delivery.delivery_status == "DELIVERED"
    ).scalar()

    failed = db.query(
        func.count(Delivery.delivery_id)
    ).filter(
        Delivery.delivery_status == "FAILED"
    ).scalar()

    pending = db.query(
        func.count(Delivery.delivery_id)
    ).filter(
        Delivery.delivery_status == "PENDING"
    ).scalar()

    success_rate = (
        (delivered / total) * 100
        if total > 0
        else 0
    )

    return {
        "total_deliveries": total,
        "delivered": delivered,
        "failed": failed,
        "pending": pending,
        "success_rate": round(success_rate, 2)
    }
@app.get("/analytics/delayed-shipments")
def get_delayed_shipments(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    results = db.query(
        Shipment.shipment_id,
        Shipment.order_id,
        Shipment.shipment_status,
        Shipment.estimated_delivery,
        Shipment.shipment_date
    ).filter(
        Shipment.estimated_delivery < func.current_timestamp(),
        Shipment.shipment_status != "DELIVERED",
        Shipment.shipment_status != "CANCELLED"
    ).order_by(
        Shipment.estimated_delivery.asc()
    ).all()

    return [
        {
            "shipment_id": shipment_id,
            "order_id": order_id,
            "status": shipment_status,
            "shipment_date": shipment_date,
            "estimated_delivery": estimated_delivery
        }
        for shipment_id, order_id, shipment_status,
            estimated_delivery, shipment_date in results
    ]
@app.get("/analytics/warehouse-stock-value")
def get_warehouse_stock_value(
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    results = db.query(
        Warehouse.warehouse_name,
        func.sum(
            Inventory.quantity * Product.unit_price
        ).label("stock_value")
    ).join(
        Inventory,
        Warehouse.warehouse_id == Inventory.warehouse_id
    ).join(
        Product,
        Product.product_id == Inventory.product_id
    ).group_by(
        Warehouse.warehouse_id,
        Warehouse.warehouse_name
    ).order_by(
        func.sum(
            Inventory.quantity * Product.unit_price
        ).desc()
    ).all()

    return [
        {
            "warehouse": warehouse_name,
            "stock_value": float(stock_value)
        }
        for warehouse_name, stock_value in results
    ]
@app.get("/customers/{customer_id}/order-history")
def get_customer_order_history(
    customer_id: int,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    customer = db.query(Customer).filter(
        Customer.customer_id == customer_id
    ).first()

    if not customer:
        return {"error": "Customer not found"}

    results = db.query(
        Order.order_id,
        Order.order_date,
        Order.order_status,
        Order.shipping_address,
        func.coalesce(
            func.sum(OrderItem.quantity),
            0
        ).label("total_items")
    ).outerjoin(
        OrderItem,
        Order.order_id == OrderItem.order_id
    ).filter(
        Order.customer_id == customer_id
    ).group_by(
        Order.order_id,
        Order.order_date,
        Order.order_status,
        Order.shipping_address
    ).order_by(
        Order.order_date.desc()
    ).all()

    return {
        "customer_id": customer_id,
        "customer_name": customer.name,
        "orders": [
            {
                "order_id": order_id,
                "order_date": order_date,
                "order_status": order_status,
                "shipping_address": shipping_address,
                "total_items": total_items
            }
            for order_id, order_date, order_status,
                shipping_address, total_items in results
        ]
    }
@app.get("/shipments/{shipment_id}/tracking-details")
def get_tracking_details(
    shipment_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    shipment = db.query(Shipment).filter(
        Shipment.shipment_id == shipment_id
    ).first()

    if not shipment:
        raise HTTPException(
            status_code=404,
            detail="Shipment not found"
        )

    # Get user's role
    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if not role:
        raise HTTPException(
            status_code=403,
            detail="Role not found"
        )

    # CUSTOMER can only view their own shipment details
    if role.role_name == "CUSTOMER":

        customer = db.query(Customer).filter(
            Customer.user_id == current_user["user_id"]
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer profile not found"
            )

        order = db.query(Order).filter(
            Order.order_id == shipment.order_id
        ).first()

        if not order or order.customer_id != customer.customer_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this shipment"
            )

    route = db.query(Route).filter(
        Route.route_id == shipment.route_id
    ).first()

    warehouse = db.query(Warehouse).filter(
        Warehouse.warehouse_id == shipment.warehouse_id
    ).first()

    delivery = db.query(Delivery).filter(
        Delivery.shipment_id == shipment_id
    ).first()

    tracking = db.query(ShipmentTracking).filter(
        ShipmentTracking.shipment_id == shipment_id
    ).order_by(
        ShipmentTracking.tracking_id  # insertion order = order the status trigger applied
    ).all()

    return {
        "shipment_id": shipment.shipment_id,
        "order_id": shipment.order_id,
        "shipment_status": shipment.shipment_status,

        "route": {
            "route_name": route.route_name if route else None,
            "source": route.source if route else None,
            "destination": route.destination if route else None,
            "distance_km": float(route.distance_km) if route else None
        },

        "warehouse": {
            "warehouse_name": warehouse.warehouse_name
            if warehouse else None,
            "city": warehouse.city
            if warehouse else None
        },

        "delivery": {
            "driver_id": delivery.driver_id
            if delivery else None,
            "delivery_status": delivery.delivery_status
            if delivery else None,
            "delivery_date": delivery.delivery_date
            if delivery else None
        },

        "tracking_history": [
            {
                "status": event.status,
                "location": event.location,
                "timestamp": event.tracking_timestamp,
                "remarks": event.remarks
            }
            for event in tracking
        ]
    }
@app.get("/orders/search")
def search_orders(
    status: str | None = None,
    customer_id: int | None = None,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    query = db.query(Order)

    if status:
        query = query.filter(
            Order.order_status == status.upper()
        )

    if customer_id:
        query = query.filter(
            Order.customer_id == customer_id
        )

    orders = query.order_by(
        Order.order_date.desc()
    ).all()

    return [
        {
            "order_id": order.order_id,
            "customer_id": order.customer_id,
            "order_date": order.order_date,
            "order_status": order.order_status,
            "shipping_address": order.shipping_address
        }
        for order in orders
    ]
@app.get("/shipments/search")
def search_shipments(
    status: str | None = None,
    warehouse_id: int | None = None,
    route_id: int | None = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get user's role
    role = db.query(Role).filter(
        Role.role_id == current_user["role_id"]
    ).first()

    if not role:
        raise HTTPException(
            status_code=403,
            detail="Role not found"
        )

    query = db.query(Shipment)

    # CUSTOMER can only see shipments belonging to their orders
    if role.role_name == "CUSTOMER":

        customer = db.query(Customer).filter(
            Customer.user_id == current_user["user_id"]
        ).first()

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer profile not found"
            )

        customer_orders = db.query(Order.order_id).filter(
            Order.customer_id == customer.customer_id
        ).subquery()

        query = query.filter(
            Shipment.order_id.in_(customer_orders)
        )

    # Optional filters
    if status:
        query = query.filter(
            Shipment.shipment_status == status.upper()
        )

    if warehouse_id:
        query = query.filter(
            Shipment.warehouse_id == warehouse_id
        )

    if route_id:
        query = query.filter(
            Shipment.route_id == route_id
        )

    shipments = query.order_by(
        Shipment.shipment_date.desc()
    ).all()

    return [
        {
            "shipment_id": shipment.shipment_id,
            "order_id": shipment.order_id,
            "warehouse_id": shipment.warehouse_id,
            "route_id": shipment.route_id,
            "shipment_date": shipment.shipment_date,
            "estimated_delivery": shipment.estimated_delivery,
            "shipment_status": shipment.shipment_status
        }
        for shipment in shipments
    ]
@app.get("/customers/search")
def search_customers(
    name: str | None = None,
    city: str | None = None,
    current_user: dict = Depends(require_roles("ADMIN", "OPERATIONS_MANAGER")),
    db: Session = Depends(get_db)
):
    query = db.query(Customer)

    if name:
        query = query.filter(
            Customer.name.ilike(f"%{name}%")
        )

    if city:
        query = query.filter(
            Customer.address.ilike(f"%{city}%")
        )

    customers = query.order_by(
        Customer.name
    ).all()

    return [
        {
            "customer_id": customer.customer_id,
            "user_id": customer.user_id,
            "name": customer.name,
            "phone": customer.phone,
            "address": customer.address
        }
        for customer in customers
    ]
class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=3, max_length=100)
    phone: str = Field(min_length=7, max_length=20)
    address: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    class Config:
        extra = "forbid"


@app.post("/auth/register", status_code=201)
def register(register_data: RegisterRequest, db: Session = Depends(get_db)):
    name = register_data.name.strip()
    username = register_data.username.strip()
    email = register_data.email.strip().lower()
    phone = register_data.phone.strip()
    address = register_data.address.strip()

    if not name or not username or not phone or not address:
        raise HTTPException(status_code=422, detail="All registration fields are required")
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address")

    existing_user = db.query(User).filter(
        (User.username == username) | (User.email == email)
    ).first()
    if existing_user:
        detail = "Username is already in use" if existing_user.username == username else "Email is already in use"
        raise HTTPException(status_code=409, detail=detail)

    customer_role = db.query(Role).filter(Role.role_name == "CUSTOMER").first()
    if not customer_role:
        raise HTTPException(status_code=500, detail="Customer role is not configured")

    try:
        new_user = User(
            role_id=customer_role.role_id,
            username=username,
            email=email,
            password_hash=hash_password(register_data.password),
            is_active=True
        )
        db.add(new_user)
        db.flush()

        new_customer = Customer(
            user_id=new_user.user_id,
            name=name,
            phone=phone,
            address=address
        )
        db.add(new_customer)
        db.commit()
        db.refresh(new_user)
        db.refresh(new_customer)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username or email is already in use")

    return {
        "message": "Account created successfully",
        "user_id": new_user.user_id,
        "customer_id": new_customer.customer_id,
        "username": new_user.username,
        "role": "CUSTOMER"
    }


@app.post("/auth/login")
def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.username == login_data.username
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User account is inactive"
        )

    try:
        password_is_valid = verify_password(
            login_data.password,
            user.password_hash
        )
    except UnknownHashError:
        password_is_valid = False

    if not password_is_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    access_token = create_access_token({
        "user_id": user.user_id,
        "username": user.username,
        "role_id": user.role_id
    })

    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.user_id,
        "username": user.username,
        "role_id": user.role_id
    }
