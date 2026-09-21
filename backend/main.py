from models import Role,Customer,Order,Shipment,Warehouse,Route
from models import ShipmentTracking,Delivery,Payment,Invoice,Inventory
from models import Product,Employee,Driver,Vehicle,DriverVehicleAssignment
from models import VehicleMaintenance,User,OrderItem,ShipmentItem
from fastapi import FastAPI, Depends
from sqlalchemy import text, func, case
from pydantic import BaseModel
from sqlalchemy import text
from datetime import datetime,date
from sqlalchemy.orm import Session
from fastapi import HTTPException
from pydantic import BaseModel
from auth import verify_password

from database import get_db

app = FastAPI(title="LogiTrack API")
class OrderCreate(BaseModel):
    customer_id: int
    order_status: str = "PENDING"
    shipping_address: str

class OrderItemCreate(BaseModel):
    order_id: int
    product_id: int
    quantity: int
    unit_price: float


@app.get("/")
def root():
    return {
        "message": "LogiTrack API is running"
    }


@app.get("/db-test")
def database_test(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1"))
    return {
        "database": "connected",
        "result": result.scalar()
    }

@app.get("/roles")
def get_roles(db: Session = Depends(get_db)):
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
def get_customers(db: Session = Depends(get_db)):
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
def get_customer(customer_id: int, db: Session = Depends(get_db)):
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
def get_orders(db: Session = Depends(get_db)):
    orders = db.query(Order).all()

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

@app.get("/orders/{order_id}")
def get_order_details(order_id: int, db: Session = Depends(get_db)):
    order = (
        db.query(Order)
        .filter(Order.order_id == order_id)
        .first()
    )

    if not order:
        return {"error": "Order not found"}

    items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order_id)
        .all()
    )

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
def get_order_total(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_id == order_id).first()

    if not order:
        return {"error": "Order not found"}

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
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    new_order = Order(
        customer_id=order.customer_id,
        order_status=order.order_status,
        shipping_address=order.shipping_address
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
def get_shipments(db: Session = Depends(get_db)):
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
def get_shipment_details(db: Session = Depends(get_db)):
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
def get_tracking(shipment_id: int, db: Session = Depends(get_db)):
    tracking = (
        db.query(ShipmentTracking)
        .filter(ShipmentTracking.shipment_id == shipment_id)
        .order_by(ShipmentTracking.tracking_timestamp)
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
def get_deliveries(db: Session = Depends(get_db)):
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
def get_payments(db: Session = Depends(get_db)):
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
def get_invoices(db: Session = Depends(get_db)):
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
def get_inventory(db: Session = Depends(get_db)):
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
def get_products(db: Session = Depends(get_db)):
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

@app.get("/warehouses")
def get_warehouses(db: Session = Depends(get_db)):
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
def get_employees(db: Session = Depends(get_db)):
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
def get_drivers(db: Session = Depends(get_db)):
    drivers = db.query(Driver).all()

    return [
        {
            "employee_id": driver.employee_id,
            "license_no": driver.license_no,
            "license_expiry": driver.license_expiry,
            "availability_status": driver.availability_status
        }
        for driver in drivers
    ]

@app.get("/vehicles")
def get_vehicles(db: Session = Depends(get_db)):
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
def get_assignments(db: Session = Depends(get_db)):
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
def get_maintenance(db: Session = Depends(get_db)):
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
def get_routes(db: Session = Depends(get_db)):
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
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()

    return [
        {
            "user_id": user.user_id,
            "role_id": user.role_id,
            "username": user.username,
            "email": user.email,
            "created_at": user.created_at,
            "is_active": user.is_active
        }
        for user in users
    ]

@app.get("/order-items")
def get_order_items(db: Session = Depends(get_db)):
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
def get_shipment_items(db: Session = Depends(get_db)):
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
    db: Session = Depends(get_db)
):
    db.execute(
        text("CALL update_shipment_status(:shipment_id, :status)"),
        {
            "shipment_id": shipment_id,
            "status": data.status
        }
    )

    db.commit()

    return {
        "message": "Shipment status updated successfully",
        "shipment_id": shipment_id,
        "status": data.status
    }
class ShipmentCreate(BaseModel):
    order_id: int
    warehouse_id: int
    route_id: int
    estimated_delivery: datetime | None = None
@app.post("/shipments")
def create_shipment(
    shipment: ShipmentCreate,
    db: Session = Depends(get_db)
):
    new_shipment = Shipment(
        order_id=shipment.order_id,
        warehouse_id=shipment.warehouse_id,
        route_id=shipment.route_id,
        estimated_delivery=shipment.estimated_delivery
    )

    db.add(new_shipment)
    db.commit()
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
    db: Session = Depends(get_db)
):
    new_tracking = ShipmentTracking(
        shipment_id=tracking.shipment_id,
        status=tracking.status,
        location=tracking.location,
        remarks=tracking.remarks
    )

    db.add(new_tracking)
    db.commit()
    db.refresh(new_tracking)

    return {
        "message": "Tracking event added successfully",
        "tracking_id": new_tracking.tracking_id,
        "shipment_id": new_tracking.shipment_id,
        "status": new_tracking.status,
        "location": new_tracking.location,
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
    db: Session = Depends(get_db)
):
    new_delivery = Delivery(
        shipment_id=delivery.shipment_id,
        driver_id=delivery.driver_id,
        delivery_address=delivery.delivery_address,
        delivery_status=delivery.delivery_status
    )

    db.add(new_delivery)
    db.commit()
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
    password_hash: str
    is_active: bool = True
@app.post("/users")
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    new_user = User(
        role_id=user.role_id,
        username=user.username,
        email=user.email,
        password_hash=user.password_hash,
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
class CustomerCreate(BaseModel):
    user_id: int
    name: str
    phone: str | None = None
    address: str | None = None
@app.post("/customers")
def create_customer(
    customer: CustomerCreate,
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
class RoleCreate(BaseModel):
    role_name: str
    description: str | None = None
@app.post("/roles")
def create_role(
    role: RoleCreate,
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
    db: Session = Depends(get_db)
):
    delivery = db.query(Delivery).filter(
        Delivery.delivery_id == delivery_id
    ).first()

    if not delivery:
        return {"error": "Delivery not found"}

    delivery.delivery_status = data.delivery_status

    db.commit()
    db.refresh(delivery)

    return {
        "message": "Delivery status updated successfully",
        "delivery_id": delivery.delivery_id,
        "delivery_status": delivery.delivery_status
    }
class InventoryUpdate(BaseModel):
    quantity: int
    reorder_level: int | None = None
@app.put("/inventory/{warehouse_id}/{product_id}")
def update_inventory(
    warehouse_id: int,
    product_id: int,
    data: InventoryUpdate,
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
    db: Session = Depends(get_db)
):
    driver = db.query(Driver).filter(
        Driver.employee_id == employee_id
    ).first()

    if not driver:
        return {"error": "Driver not found"}

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
    db: Session = Depends(get_db)
):
    shipment = db.query(Shipment).filter(
        Shipment.shipment_id == shipment_id
    ).first()

    if not shipment:
        return {"error": "Shipment not found"}

    tracking_events = db.query(ShipmentTracking).filter(
        ShipmentTracking.shipment_id == shipment_id
    ).order_by(
        ShipmentTracking.tracking_timestamp
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
    db: Session = Depends(get_db)
):
    shipment = db.query(Shipment).filter(
        Shipment.shipment_id == shipment_id
    ).first()

    if not shipment:
        return {"error": "Shipment not found"}

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
        ShipmentTracking.tracking_timestamp
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
    db: Session = Depends(get_db)
):
    query = db.query(Shipment)

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

    if not verify_password(
        login_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    return {
        "message": "Login successful",
        "user_id": user.user_id,
        "username": user.username,
        "role_id": user.role_id
    }