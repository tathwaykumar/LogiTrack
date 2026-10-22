-- Phase 3B follow-up: at most one non-cancelled shipment per order.
--
-- A partial unique index enforces this in the database, so it holds for every
-- code path (payment fulfilment, POST /shipments, status changes made through
-- the shipment_tracking trigger). CANCELLED shipments are excluded so a
-- cancelled shipment can be replaced. No existing row is modified.
--
-- Safe to re-run. Aborts with a clear message, changing nothing, if existing
-- data already has duplicate non-cancelled shipments for an order.

BEGIN;

DO $$
DECLARE
    duplicate_orders text;
BEGIN
    SELECT string_agg(order_id::text, ', ' ORDER BY order_id)
    INTO duplicate_orders
    FROM (
        SELECT order_id
        FROM public.shipment
        WHERE shipment_status <> 'CANCELLED'
        GROUP BY order_id
        HAVING count(*) > 1
    ) duplicates;

    IF duplicate_orders IS NOT NULL THEN
        RAISE EXCEPTION 'Cannot add uq_shipment_order_active: orders with more than one non-cancelled shipment: %', duplicate_orders;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_shipment_order_active
    ON public.shipment USING btree (order_id)
    WHERE ((shipment_status)::text <> 'CANCELLED'::text);

COMMIT;
