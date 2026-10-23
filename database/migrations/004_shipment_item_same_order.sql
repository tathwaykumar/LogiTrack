-- A shipment item must belong to the same order as its shipment.
--
-- shipment_item stores order_id so it can reference order_item (order_id, product_id),
-- but nothing stopped that order_id from differing from shipment.order_id. This adds a
-- composite foreign key shipment_item (shipment_id, order_id) -> shipment (shipment_id, order_id).
-- The referenced pair needs a unique constraint; (shipment_id, order_id) is trivially unique
-- because shipment_id already is, so it changes no data and no behaviour for valid rows.
--
-- Idempotent. If existing rows already violate the rule, it stops with the offending
-- shipment IDs and changes nothing.

BEGIN;

DO $$
DECLARE
    offenders text;
BEGIN
    SELECT string_agg(DISTINCT si.shipment_id::text, ', ')
    INTO offenders
    FROM public.shipment_item si
    JOIN public.shipment s ON s.shipment_id = si.shipment_id
    WHERE si.order_id <> s.order_id;

    IF offenders IS NOT NULL THEN
        RAISE EXCEPTION 'Cannot add fk_shipment_item_shipment_order: shipment_item.order_id differs from shipment.order_id for shipments: %', offenders;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_shipment_id_order'
                   AND conrelid = 'public.shipment'::regclass) THEN
        ALTER TABLE public.shipment
            ADD CONSTRAINT uq_shipment_id_order UNIQUE (shipment_id, order_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_shipment_item_shipment_order'
                   AND conrelid = 'public.shipment_item'::regclass) THEN
        ALTER TABLE public.shipment_item
            ADD CONSTRAINT fk_shipment_item_shipment_order
            FOREIGN KEY (shipment_id, order_id) REFERENCES public.shipment (shipment_id, order_id);
    END IF;
END $$;

COMMIT;
