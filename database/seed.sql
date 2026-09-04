-- ============================================
-- LogiTrack Seed Data
-- ============================================

-- 1. ROLES
INSERT INTO role (role_id, role_name, description) VALUES
(1, 'ADMIN', 'Full system access'),
(2, 'OPERATIONS_MANAGER', 'Manages logistics operations'),
(3, 'DRIVER', 'Handles deliveries and shipment updates'),
(4, 'CUSTOMER', 'Places orders and tracks shipments');


-- 2. USERS
INSERT INTO users
(user_id, role_id, username, email, password_hash, is_active)
VALUES
(1, 1, 'admin01', 'admin@logitrack.com', 'seed_hash_admin', TRUE),
(2, 2, 'manager01', 'manager@logitrack.com', 'seed_hash_manager', TRUE),
(3, 3, 'driver01', 'driver1@logitrack.com', 'seed_hash_driver1', TRUE),
(4, 3, 'driver02', 'driver2@logitrack.com', 'seed_hash_driver2', TRUE),
(5, 4, 'customer01', 'customer1@example.com', 'seed_hash_customer1', TRUE),
(6, 4, 'customer02', 'customer2@example.com', 'seed_hash_customer2', TRUE);


-- 3. CUSTOMERS
INSERT INTO customer
(customer_id, user_id, name, phone, address)
VALUES
(1, 5, 'Arjun Mehta', '9876543210', 'Vellore, Tamil Nadu'),
(2, 6, 'Priya Sharma', '9876543211', 'Chennai, Tamil Nadu');


-- 4. EMPLOYEES
INSERT INTO employee
(employee_id, user_id, name, phone, department, hire_date, salary, employment_status)
VALUES
(1, 2, 'Rahul Verma', '9876500001', 'Operations', '2024-06-10', 65000.00, 'ACTIVE'),
(2, 3, 'Vikram Singh', '9876500002', 'Transport', '2024-08-15', 45000.00, 'ACTIVE'),
(3, 4, 'Amit Kumar', '9876500003', 'Transport', '2025-01-20', 44000.00, 'ACTIVE'),
(4, NULL, 'Neha Patel', '9876500004', 'Warehouse', '2025-03-12', 38000.00, 'ACTIVE');


-- ============================================
-- End of foundational seed data
-- ============================================
-- 5. DRIVERS
INSERT INTO driver
(employee_id, license_no, license_expiry, availability_status)
VALUES
(2, 'TN-DRV-1001', '2028-06-30', 'AVAILABLE'),
(3, 'TN-DRV-1002', '2027-11-15', 'AVAILABLE');


-- 6. VEHICLES
INSERT INTO vehicle
(vehicle_id, registration_no, vehicle_type, capacity, fuel_type, status, purchase_date)
VALUES
(1, 'TN01AB1234', 'Mini Truck', 1500.00, 'DIESEL', 'ACTIVE', '2023-04-10'),
(2, 'TN02CD5678', 'Delivery Van', 1000.00, 'DIESEL', 'ACTIVE', '2024-01-15'),
(3, 'TN03EF9012', 'Heavy Truck', 5000.00, 'DIESEL', 'ACTIVE', '2022-08-20'),
(4, 'TN04GH3456', 'Electric Van', 800.00, 'ELECTRIC', 'ACTIVE', '2025-05-12');


-- 7. DRIVER-VEHICLE ASSIGNMENTS
INSERT INTO driver_vehicle_assignment
(assignment_id, driver_id, vehicle_id, assigned_from, assigned_to)
VALUES
(1, 2, 1, '2026-01-01', NULL),
(2, 3, 2, '2026-01-01', NULL);


-- 8. WAREHOUSES
INSERT INTO warehouse
(warehouse_id, warehouse_name, address, city, capacity, manager_employee_id, status)
VALUES
(1, 'Vellore Central Warehouse', 'Katpadi Road', 'Vellore', 10000.00, 1, 'ACTIVE'),
(2, 'Chennai Distribution Hub', 'Guindy Industrial Area', 'Chennai', 20000.00, 1, 'ACTIVE'),
(3, 'Bangalore Logistics Hub', 'Peenya Industrial Area', 'Bangalore', 15000.00, NULL, 'ACTIVE');

-- 9. PRODUCTS
INSERT INTO product
(product_id, product_name, category, unit_price, weight, description)
VALUES
(1, 'Laptop', 'Electronics', 55000.00, 2.20, 'Business laptop'),
(2, 'Wireless Mouse', 'Electronics', 1200.00, 0.10, 'Wireless optical mouse'),
(3, 'Mechanical Keyboard', 'Electronics', 3500.00, 0.90, 'Mechanical keyboard'),
(4, 'Monitor', 'Electronics', 15000.00, 4.50, '24-inch LED monitor'),
(5, 'USB-C Hub', 'Accessories', 2500.00, 0.20, 'Multi-port USB-C hub'),
(6, 'Headphones', 'Accessories', 3000.00, 0.35, 'Wireless headphones'),
(7, 'Webcam', 'Electronics', 4500.00, 0.30, 'HD webcam'),
(8, 'External SSD', 'Storage', 7000.00, 0.15, '1TB portable SSD');


-- 10. INVENTORY
INSERT INTO inventory
(warehouse_id, product_id, quantity, reorder_level)
VALUES
(1, 1, 25, 5),
(1, 2, 80, 20),
(1, 3, 40, 10),
(1, 4, 20, 5),
(2, 1, 40, 10),
(2, 2, 100, 25),
(2, 5, 50, 10),
(2, 6, 35, 8),
(3, 3, 30, 8),
(3, 4, 25, 5),
(3, 7, 20, 5),
(3, 8, 30, 8);

-- 11. ORDERS
INSERT INTO orders
(order_id, customer_id, order_date, order_status, shipping_address)
VALUES
(1, 1, '2026-08-20 10:30:00', 'DELIVERED',
 'Vellore, Tamil Nadu'),

(2, 1, '2026-08-25 14:15:00', 'SHIPPED',
 'Vellore, Tamil Nadu'),

(3, 2, '2026-08-27 09:45:00', 'PROCESSING',
 'Chennai, Tamil Nadu'),

(4, 2, '2026-08-30 16:20:00', 'CONFIRMED',
 'Chennai, Tamil Nadu');


-- 12. ORDER ITEMS
INSERT INTO order_item
(order_id, product_id, quantity, unit_price)
VALUES
(1, 1, 1, 55000.00),
(1, 2, 2, 1200.00),

(2, 3, 1, 3500.00),
(2, 4, 1, 15000.00),

(3, 5, 2, 2500.00),
(3, 6, 1, 3000.00),

(4, 7, 1, 4500.00),
(4, 8, 1, 7000.00);

-- 13. ROUTES
INSERT INTO route
(route_id, route_name, source, destination, distance_km, estimated_duration, route_status)
VALUES
(1, 'Vellore-Chennai Route', 'Vellore', 'Chennai', 140.00, INTERVAL '3 hours',
 'ACTIVE'),

(2, 'Chennai-Bangalore Route', 'Chennai', 'Bangalore', 350.00, INTERVAL '7 hours',
 'ACTIVE'),

(3, 'Vellore-Bangalore Route', 'Vellore', 'Bangalore', 220.00, INTERVAL '5 hours',
 'ACTIVE');


-- 14. SHIPMENTS
INSERT INTO shipment
(shipment_id, order_id, warehouse_id, route_id,
 shipment_date, estimated_delivery, actual_delivery, shipment_status)
VALUES
(1, 1, 1, 1,
 '2026-08-20 13:00:00',
 '2026-08-21 16:00:00',
 '2026-08-21 15:30:00',
 'DELIVERED'),

(2, 2, 1, 1,
 '2026-08-25 17:00:00',
 '2026-08-27 16:00:00',
 NULL,
 'IN_TRANSIT'),

(3, 3, 2, 2,
 '2026-08-27 14:00:00',
 '2026-08-30 18:00:00',
 NULL,
 'OUT_FOR_DELIVERY'),

(4, 4, 2, 3,
 '2026-08-30 18:00:00',
 '2026-09-02 18:00:00',
 NULL,
 'CREATED');


-- 15. SHIPMENT ITEMS
INSERT INTO shipment_item
(shipment_id, order_id, product_id, quantity)
VALUES
(1, 1, 1, 1),
(1, 1, 2, 2),

(2, 2, 3, 1),
(2, 2, 4, 1),

(3, 3, 5, 2),
(3, 3, 6, 1),

(4, 4, 7, 1),
(4, 4, 8, 1);

INSERT INTO shipment_tracking
(tracking_id, shipment_id, status, location, tracking_timestamp, remarks)
VALUES
(1, 1, 'PICKED_UP', 'Vellore Warehouse', '2026-08-20 13:15:00', 'Shipment picked up from warehouse'),
(2, 1, 'IN_TRANSIT', 'Ranipet', '2026-08-20 18:00:00', 'Shipment is in transit'),
(3, 1, 'DELIVERED', 'Chennai', '2026-08-21 15:30:00', 'Shipment delivered successfully'),

(4, 2, 'PICKED_UP', 'Vellore Warehouse', '2026-08-25 17:15:00', 'Shipment picked up'),
(5, 2, 'IN_TRANSIT', 'Kanchipuram', '2026-08-26 10:00:00', 'Shipment is in transit'),

(6, 3, 'PICKED_UP', 'Chennai Distribution Hub', '2026-08-27 14:15:00', 'Shipment picked up'),
(7, 3, 'IN_TRANSIT', 'Sriperumbudur', '2026-08-28 09:30:00', 'Shipment is in transit'),
(8, 3, 'OUT_FOR_DELIVERY', 'Chennai', '2026-08-30 10:00:00', 'Shipment is out for delivery'),

(9, 4, 'CREATED', 'Chennai Distribution Hub', '2026-08-30 18:15:00', 'Shipment created and awaiting pickup');


INSERT INTO delivery
(delivery_id, shipment_id, driver_id, delivery_date, delivery_status, delivery_address)
VALUES
(1, 1, 2, '2026-08-21 15:30:00', 'DELIVERED', 'Vellore, Tamil Nadu'),
(2, 2, 2, NULL, 'PENDING', 'Vellore, Tamil Nadu'),
(3, 3, 3, NULL, 'OUT_FOR_DELIVERY', 'Chennai, Tamil Nadu');



INSERT INTO payment
(payment_id, order_id, amount, payment_method, payment_status, payment_date, transaction_reference)
VALUES
(1, 1, 57400.00, 'UPI', 'SUCCESS', '2026-08-20 10:35:00', 'TXN10001'),
(2, 2, 18500.00, 'CARD', 'SUCCESS', '2026-08-25 14:20:00', 'TXN10002'),
(3, 3, 8000.00, 'UPI', 'PENDING', '2026-08-27 09:50:00', 'TXN10003'),
(4, 4, 11500.00, 'NET_BANKING', 'SUCCESS', '2026-08-30 16:25:00', 'TXN10004');


INSERT INTO invoice
(invoice_id, order_id, invoice_date, subtotal, tax, total_amount, invoice_status)
VALUES
(1, 1, '2026-08-20 10:40:00', 57400.00, 10332.00, 67732.00, 'ISSUED'),
(2, 2, '2026-08-25 14:25:00', 18500.00, 3330.00, 21830.00, 'ISSUED'),
(3, 3, '2026-08-27 09:55:00', 8000.00, 1440.00, 9440.00, 'ISSUED'),
(4, 4, '2026-08-30 16:30:00', 11500.00, 2070.00, 13570.00, 'ISSUED');



INSERT INTO vehicle_maintenance
(maintenance_id, vehicle_id, maintenance_date, maintenance_type, cost, description)
VALUES
(1, 1, '2026-02-15', 'SERVICE', 8500.00, 'Regular engine and oil service'),
(2, 1, '2026-07-10', 'REPAIR', 12000.00, 'Brake pad replacement'),
(3, 2, '2026-03-20', 'SERVICE', 6500.00, 'Routine vehicle servicing'),
(4, 3, '2026-05-05', 'SERVICE', 15000.00, 'Heavy vehicle maintenance'),
(5, 4, '2026-08-12', 'INSPECTION', 3000.00, 'Electric vehicle inspection');