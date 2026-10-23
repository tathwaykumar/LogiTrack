"""database/seed.sql must load cleanly in either order relative to the migrations."""
import pytest
from sqlalchemy import create_engine, text

from conftest import REPO_DIR, TEST_DB_URL, _load_sql

SETUP_DB = "logitrack_setupcheck_test"
SQL_DIR = REPO_DIR / "database"
MIGRATIONS = sorted((SQL_DIR / "migrations").glob("*.sql"))

ORDERS = {
    "schema-seed-migrations": lambda: [SQL_DIR / "schema.sql", SQL_DIR / "seed.sql", *MIGRATIONS],
    "schema-migrations-seed": lambda: [SQL_DIR / "schema.sql", *MIGRATIONS, SQL_DIR / "seed.sql"],
}


def build(files):
    admin = create_engine(TEST_DB_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SETUP_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{SETUP_DB}"'))
    target = TEST_DB_URL.set(database=SETUP_DB)
    for path in files:
        loader = create_engine(target, isolation_level="AUTOCOMMIT")
        raw = loader.raw_connection()
        try:
            raw.cursor().execute(_load_sql(path))
        finally:
            raw.close()
            loader.dispose()
    return admin, target


@pytest.mark.parametrize("order", ORDERS)
def test_seed_loads_and_leaves_a_usable_database(order):
    admin, target = build(ORDERS[order]())
    engine = create_engine(target)
    try:
        with engine.begin() as conn:
            counts = {
                table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
                for table in ("role", "users", "customer", "employee", "driver", "product", "orders", "shipment", "shipment_tracking", "delivery")
            }
            assert counts == {"role": 4, "users": 6, "customer": 2, "employee": 4, "driver": 2, "product": 8, "orders": 4, "shipment": 4, "shipment_tracking": 9, "delivery": 3}

            # Historical rows are loaded exactly as written.
            statuses = dict(conn.execute(text("SELECT shipment_id, shipment_status FROM shipment")).all())
            assert statuses == {1: "DELIVERED", 2: "IN_TRANSIT", 3: "OUT_FOR_DELIVERY", 4: "CREATED"}
            assert conn.execute(text("SELECT count(*) FROM delivery d JOIN shipment s USING (shipment_id) WHERE d.delivery_status = 'DELIVERED' AND s.shipment_status <> 'DELIVERED'")).scalar() == 0

            # No trigger is left switched off.
            assert conn.execute(text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgenabled <> 'O'")).scalar() == 0

            # ID sequences are past the seeded rows, so ordinary inserts do not collide.
            new_user = conn.execute(text("INSERT INTO users (role_id, username, email, password_hash) VALUES (4, 'seq.check', 'seq@example.test', 'x') RETURNING user_id")).scalar()
            assert new_user > 6
            new_product = conn.execute(text("INSERT INTO product (product_name, unit_price) VALUES ('Seq Check', 1) RETURNING product_id")).scalar()
            assert new_product > 8
            new_tracking = conn.execute(text("INSERT INTO shipment_tracking (shipment_id, status) VALUES (4, 'PICKED_UP') RETURNING tracking_id")).scalar()
            assert new_tracking > 9

            # Migration rules apply to new data once the seed has loaded.
            has_rules = conn.execute(text("SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_guard_tracking_event'")).scalar()
            assert has_rules == 1
            conn.execute(text("SAVEPOINT closed"))
            with pytest.raises(Exception) as error:
                conn.execute(text("INSERT INTO shipment_tracking (shipment_id, status) VALUES (1, 'IN_TRANSIT')"))
            assert "accepts no further tracking events" in str(error.value)
            conn.execute(text("ROLLBACK TO SAVEPOINT closed"))
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SETUP_DB}" WITH (FORCE)'))


def apply(target, path):
    loader = create_engine(target, isolation_level="AUTOCOMMIT")
    raw = loader.raw_connection()
    try:
        raw.cursor().execute(_load_sql(path))
    finally:
        raw.close()
        loader.dispose()


def test_migration_004_refuses_bad_data_and_is_rerunnable():
    migration_004 = SQL_DIR / "migrations" / "004_shipment_item_same_order.sql"
    first_three = [m for m in MIGRATIONS if m != migration_004]
    admin, target = build([SQL_DIR / "schema.sql", SQL_DIR / "seed.sql", *first_three])
    engine = create_engine(target, isolation_level="AUTOCOMMIT")
    try:
        # Shipment 4 belongs to order 4, but this row says it carries a line of order 1.
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO shipment_item (shipment_id, order_id, product_id, quantity) VALUES (4, 1, 1, 1)"))

        with pytest.raises(Exception) as error:
            apply(target, migration_004)
        assert "Cannot add fk_shipment_item_shipment_order" in str(error.value)
        with engine.connect() as conn:  # nothing was changed
            assert conn.execute(text("SELECT count(*) FROM pg_constraint WHERE conname IN ('uq_shipment_id_order', 'fk_shipment_item_shipment_order')")).scalar() == 0

        with engine.connect() as conn:
            conn.execute(text("DELETE FROM shipment_item WHERE shipment_id = 4 AND order_id = 1"))
        apply(target, migration_004)
        apply(target, migration_004)  # idempotent
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM pg_constraint WHERE conname IN ('uq_shipment_id_order', 'fk_shipment_item_shipment_order')")).scalar() == 2
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SETUP_DB}" WITH (FORCE)'))


def test_migration_005_changes_no_existing_data_and_can_rerun():
    migration_005 = SQL_DIR / "migrations" / "005_order_fulfilment_planning.sql"
    earlier = [m for m in MIGRATIONS if m.name < migration_005.name]
    admin, target = build([SQL_DIR / "schema.sql", SQL_DIR / "seed.sql", *earlier])
    engine = create_engine(target, isolation_level="AUTOCOMMIT")
    watched = {
        "orders": "order_id, customer_id, order_date, order_status, shipping_address",
        "delivery": "delivery_id, shipment_id, driver_id, delivery_date, delivery_status, delivery_address",
        "shipment": "shipment_id, order_id, warehouse_id, route_id, shipment_date, estimated_delivery, actual_delivery, shipment_status",
        "shipment_tracking": "tracking_id, shipment_id, status, location, tracking_timestamp, remarks",
        "inventory": "warehouse_id, product_id, quantity, reorder_level",
        "payment": "payment_id, order_id, amount, payment_status",
    }

    def snapshot(conn):
        return {
            table: conn.execute(text(f"SELECT md5(string_agg(t::text, '|' ORDER BY 1)) FROM (SELECT {cols} FROM {table}) t")).scalar()
            for table, cols in watched.items()
        }

    try:
        with engine.connect() as conn:
            before = snapshot(conn)
        apply(target, migration_005)
        apply(target, migration_005)   # idempotent
        with engine.connect() as conn:
            assert snapshot(conn) == before, "migration 005 must not change existing rows"
            # Old rows are not back-filled: what was never recorded stays NULL / absent.
            assert conn.execute(text("SELECT count(*) FROM delivery WHERE vehicle_id IS NOT NULL OR assigned_at IS NOT NULL")).scalar() == 0
            assert conn.execute(text("SELECT count(*) FROM orders WHERE destination_city IS NOT NULL")).scalar() == 0
            assert conn.execute(text("SELECT (SELECT count(*) FROM order_fulfilment) + (SELECT count(*) FROM order_fulfilment_event)")).scalar() == 0
            assert conn.execute(text("SELECT count(*) FROM order_inventory_reservation WHERE released_at IS NOT NULL")).scalar() == 0

            # The order-sync trigger applies to shipment changes made from now on, forward only.
            conn.execute(text("INSERT INTO shipment_tracking (shipment_id, status) VALUES (3, 'DELIVERED')"))
            statuses = dict(conn.execute(text("SELECT order_id, order_status FROM orders")).all())
            assert statuses[3] == "DELIVERED"
            assert {k: v for k, v in statuses.items() if k != 3} == {1: "DELIVERED", 2: "SHIPPED", 4: "CONFIRMED"}

            # The new foreign key on delivery.vehicle_id is enforced (checked below).
        with engine.connect() as conn:
            with pytest.raises(Exception) as error:
                conn.execute(text("UPDATE delivery SET vehicle_id = 99999 WHERE delivery_id = 2"))
            assert "fk_delivery_vehicle" in str(error.value)
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SETUP_DB}" WITH (FORCE)'))


def test_migrations_006_and_007_change_no_existing_data_and_can_rerun():
    m006 = SQL_DIR / "migrations" / "006_operations_approval_and_demo_ledger.sql"
    m007 = SQL_DIR / "migrations" / "007_shipment_route_optional.sql"
    earlier = [m for m in MIGRATIONS if m.name < m006.name]
    admin, target = build([SQL_DIR / "schema.sql", SQL_DIR / "seed.sql", *earlier])
    engine = create_engine(target, isolation_level="AUTOCOMMIT")
    watched = {
        "orders": "order_id, customer_id, order_date, order_status, shipping_address",
        "shipment": "shipment_id, order_id, warehouse_id, route_id, shipment_date, estimated_delivery, actual_delivery, shipment_status",
        "inventory": "warehouse_id, product_id, quantity, reorder_level",
        "payment": "payment_id, order_id, amount, payment_status",
    }

    def snapshot(conn):
        return {t: conn.execute(text(f"SELECT md5(string_agg(x::text, '|' ORDER BY 1)) FROM (SELECT {c} FROM {t}) x")).scalar()
                for t, c in watched.items()}

    try:
        with engine.connect() as conn:
            before = snapshot(conn)
            # Before 007 a shipment must have a route.
            assert conn.execute(text("SELECT is_nullable FROM information_schema.columns WHERE table_name='shipment' AND column_name='route_id'")).scalar() == "NO"
        for migration in (m006, m007):
            apply(target, migration)
            apply(target, migration)   # idempotent
        with engine.connect() as conn:
            assert snapshot(conn) == before, "migrations 006/007 must not change existing rows"
            assert conn.execute(text("SELECT is_nullable FROM information_schema.columns WHERE table_name='shipment' AND column_name='route_id'")).scalar() == "YES"
            assert conn.execute(text("SELECT count(*) FROM order_fulfilment WHERE approved_at IS NOT NULL")).scalar() == 0   # history is not marked approved
            assert conn.execute(text("SELECT count(*) FROM demo_seed_record")).scalar() == 0
            # A shipment without a route is now valid; the foreign key still rejects a route that does not exist.
            conn.execute(text("INSERT INTO shipment (order_id, warehouse_id, route_id, shipment_status) VALUES (4, 1, NULL, 'CANCELLED')"))
        with engine.connect() as conn:
            with pytest.raises(Exception) as error:
                conn.execute(text("INSERT INTO shipment (order_id, warehouse_id, route_id, shipment_status) VALUES (4, 1, 99999, 'CANCELLED')"))
            assert "fk_shipment_route" in str(error.value)
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SETUP_DB}" WITH (FORCE)'))
