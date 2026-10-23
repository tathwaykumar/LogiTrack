-- Order fulfilment planning, persisted vehicle assignment, exactly-once stock release.
--
-- Additive only: new nullable columns, two new tables, indexes and one trigger. No existing row is
-- rewritten and no existing constraint is weakened. Historical rows are NOT back-filled:
--   * orders.destination_city, delivery.vehicle_id, delivery.assigned_at stay NULL for old rows
--     (the data was never recorded; the application shows them as "not recorded");
--   * old orders get no order_fulfilment row and no fulfilment events.
--
-- Safe to re-run (every statement is guarded).

BEGIN;

-- ---------------------------------------------------------------------------------------------
-- Delivery: which vehicle carries the shipment, and when the assignment was made.
-- ---------------------------------------------------------------------------------------------
ALTER TABLE public.delivery ADD COLUMN IF NOT EXISTS vehicle_id integer;
ALTER TABLE public.delivery ADD COLUMN IF NOT EXISTS assigned_at timestamp without time zone;
-- Set AFTER adding the column so existing rows keep NULL (their real assignment time is unknown).
ALTER TABLE public.delivery ALTER COLUMN assigned_at SET DEFAULT CURRENT_TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_delivery_vehicle'
                   AND conrelid = 'public.delivery'::regclass) THEN
        ALTER TABLE public.delivery
            ADD CONSTRAINT fk_delivery_vehicle FOREIGN KEY (vehicle_id) REFERENCES public.vehicle (vehicle_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_delivery_vehicle ON public.delivery USING btree (vehicle_id);
CREATE INDEX IF NOT EXISTS idx_delivery_driver_status ON public.delivery USING btree (driver_id, delivery_status);

-- ---------------------------------------------------------------------------------------------
-- Orders: the destination city chosen at checkout (used for route planning instead of
-- searching the free-text address).
-- ---------------------------------------------------------------------------------------------
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS destination_city character varying(100);

-- ---------------------------------------------------------------------------------------------
-- Reservations: released_at marks stock that has been returned to inventory. The release routine
-- only touches rows where released_at IS NULL, so stock can be released exactly once.
-- ---------------------------------------------------------------------------------------------
ALTER TABLE public.order_inventory_reservation ADD COLUMN IF NOT EXISTS released_at timestamp without time zone;

CREATE INDEX IF NOT EXISTS idx_reservation_active
    ON public.order_inventory_reservation USING btree (order_id) WHERE released_at IS NULL;

-- ---------------------------------------------------------------------------------------------
-- order_fulfilment: one planning record per order (when the order was placed through checkout).
--   PLANNED              plan is ready; dispatch waits for payment
--   BLOCKED              planning could not complete; reason_code / reason_detail say why
--   AWAITING_ASSIGNMENT  paid, shipment created, no eligible driver and vehicle yet
--   ASSIGNED             paid, shipment created, driver and vehicle assigned
--   CANCELLED            order cancelled or abandoned, stock released
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.order_fulfilment (
    order_id integer NOT NULL,
    fulfilment_status character varying(30) NOT NULL,
    reason_code character varying(50),
    reason_detail character varying(500),
    origin_warehouse_id integer,
    route_id integer,
    route_basis character varying(30),
    selection_note character varying(1000),
    planned_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT order_fulfilment_pkey PRIMARY KEY (order_id),
    CONSTRAINT fk_fulfilment_order FOREIGN KEY (order_id) REFERENCES public.orders (order_id),
    CONSTRAINT fk_fulfilment_warehouse FOREIGN KEY (origin_warehouse_id) REFERENCES public.warehouse (warehouse_id),
    CONSTRAINT fk_fulfilment_route FOREIGN KEY (route_id) REFERENCES public.route (route_id),
    CONSTRAINT chk_fulfilment_status CHECK (fulfilment_status IN
        ('PLANNED', 'BLOCKED', 'AWAITING_ASSIGNMENT', 'ASSIGNED', 'CANCELLED')),
    CONSTRAINT chk_fulfilment_route_basis CHECK (route_basis IS NULL OR route_basis IN
        ('DESTINATION_CITY', 'ADDRESS_TEXT'))
);

CREATE INDEX IF NOT EXISTS idx_fulfilment_status ON public.order_fulfilment USING btree (fulfilment_status);
CREATE INDEX IF NOT EXISTS idx_fulfilment_warehouse ON public.order_fulfilment USING btree (origin_warehouse_id);

-- ---------------------------------------------------------------------------------------------
-- order_fulfilment_event: append-only audit trail of planning and allocation decisions.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.order_fulfilment_event (
    event_id integer GENERATED BY DEFAULT AS IDENTITY,
    order_id integer NOT NULL,
    shipment_id integer,
    event_type character varying(40) NOT NULL,
    detail character varying(500),
    actor_user_id integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT order_fulfilment_event_pkey PRIMARY KEY (event_id),
    CONSTRAINT fk_fulfilment_event_order FOREIGN KEY (order_id) REFERENCES public.orders (order_id),
    CONSTRAINT fk_fulfilment_event_shipment FOREIGN KEY (shipment_id) REFERENCES public.shipment (shipment_id),
    CONSTRAINT fk_fulfilment_event_actor FOREIGN KEY (actor_user_id) REFERENCES public.users (user_id)
);

CREATE INDEX IF NOT EXISTS idx_fulfilment_event_order ON public.order_fulfilment_event USING btree (order_id, event_id);

-- ---------------------------------------------------------------------------------------------
-- Keep the order status in step with its shipment (forward only), whatever path changed the
-- shipment: API, stored procedure or direct SQL.
--   shipment PICKED_UP / IN_TRANSIT / OUT_FOR_DELIVERY -> order SHIPPED
--   shipment DELIVERED                                  -> order DELIVERED
-- A cancelled order is never touched, and an order never moves backwards. Existing orders are not
-- changed by this migration; the rule applies to shipment changes made from now on.
-- ---------------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.sync_order_with_shipment() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    target character varying;
    ranks constant text[] := ARRAY['PENDING', 'CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED'];
BEGIN
    target := CASE
        WHEN NEW.shipment_status = 'DELIVERED' THEN 'DELIVERED'
        WHEN NEW.shipment_status IN ('PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY') THEN 'SHIPPED'
    END;
    IF target IS NULL THEN
        RETURN NULL;
    END IF;

    UPDATE public.orders
    SET order_status = target
    WHERE order_id = NEW.order_id
      AND order_status <> 'CANCELLED'
      AND array_position(ranks, order_status::text) < array_position(ranks, target::text);
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_order_with_shipment ON public.shipment;
CREATE TRIGGER trg_sync_order_with_shipment
    AFTER UPDATE OF shipment_status ON public.shipment
    FOR EACH ROW
    WHEN (OLD.shipment_status IS DISTINCT FROM NEW.shipment_status)
    EXECUTE FUNCTION public.sync_order_with_shipment();

COMMIT;
