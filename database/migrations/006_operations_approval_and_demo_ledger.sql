-- Migration 006: operations approval step and a ledger of demo-seeded rows.
--
-- Business sequence: customer places order -> customer pays -> Operations Manager approves ->
-- shipment is created -> driver and vehicle are assigned -> delivery is tracked.
--
-- Additive and re-runnable. Changes no existing row. Orders that are already paid or shipped are NOT
-- marked approved: the approval time of history is unknown and is not invented. Shipments that
-- already exist are unaffected (approval only gates creating a new shipment).
--
--   order_fulfilment.approved_at / approved_by_user_id  who approved a paid order, and when.
--   demo_seed_record                                    rows added by backend/seed_demo_data.py, so
--                                                        demo additions can be told from real data.

ALTER TABLE public.order_fulfilment ADD COLUMN IF NOT EXISTS approved_at timestamp without time zone;
ALTER TABLE public.order_fulfilment ADD COLUMN IF NOT EXISTS approved_by_user_id integer;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fulfilment_approved_by') THEN
        ALTER TABLE public.order_fulfilment
            ADD CONSTRAINT fk_fulfilment_approved_by FOREIGN KEY (approved_by_user_id) REFERENCES public.users (user_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.demo_seed_record (
    entity character varying(30) NOT NULL,
    entity_key character varying(100) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT demo_seed_record_pkey PRIMARY KEY (entity, entity_key)
);
