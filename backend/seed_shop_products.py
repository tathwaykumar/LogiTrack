"""Idempotently add the Phase 1 Shop demo catalog without altering existing products."""

from database import SessionLocal
from models import Inventory, Product, Warehouse


DEMO_PRODUCTS = (
    {
        "product_name": "Portable Power Bank",
        "category": "Accessories",
        "unit_price": 1800.00,
        "weight": 0.25,
        "description": "10000 mAh USB-C portable power bank",
        "quantity": 60,
        "reorder_level": 12,
    },
    {
        "product_name": "Ergonomic Laptop Stand",
        "category": "Accessories",
        "unit_price": 2200.00,
        "weight": 0.80,
        "description": "Adjustable aluminium laptop stand",
        "quantity": 45,
        "reorder_level": 10,
    },
    {
        "product_name": "Bluetooth Speaker",
        "category": "Electronics",
        "unit_price": 2800.00,
        "weight": 0.55,
        "description": "Compact wireless speaker with 12-hour battery",
        "quantity": 35,
        "reorder_level": 8,
    },
)


def seed_shop_products():
    db = SessionLocal()
    try:
        existing_names = {
            name.casefold()
            for (name,) in db.query(Product.product_name).all()
        }
        missing_products = [
            product for product in DEMO_PRODUCTS
            if product["product_name"].casefold() not in existing_names
        ]

        if not missing_products:
            return 0

        warehouse = (
            db.query(Warehouse)
            .filter(Warehouse.status == "ACTIVE")
            .order_by(Warehouse.warehouse_id)
            .first()
        )
        if warehouse is None:
            raise RuntimeError("An active warehouse is required to seed Shop inventory.")

        for data in missing_products:
            product = Product(
                product_name=data["product_name"],
                category=data["category"],
                unit_price=data["unit_price"],
                weight=data["weight"],
                description=data["description"],
            )
            db.add(product)
            db.flush()
            db.add(
                Inventory(
                    warehouse_id=warehouse.warehouse_id,
                    product_id=product.product_id,
                    quantity=data["quantity"],
                    reorder_level=data["reorder_level"],
                )
            )

        db.commit()
        return len(missing_products)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    added = seed_shop_products()
    print(f"Added {added} Shop demo product(s).")
