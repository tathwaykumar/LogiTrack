-- Shipment / delivery status rules.
--
-- Source of truth: shipment.shipment_status, advanced by shipment_tracking events
-- (the existing trg_update_shipment_status trigger copies each event's status onto
-- the shipment). delivery.delivery_status is a projection of it:
--
--   shipment CREATED | PICKED_UP | IN_TRANSIT -> delivery PENDING
--   shipment OUT_FOR_DELIVERY                 -> delivery OUT_FOR_DELIVERY (or FAILED after a failed attempt)
--   shipment DELIVERED                        -> delivery DELIVERED
--   shipment CANCELLED                        -> delivery CANCELLED
--
-- Shipment transitions: forward only through
--   CREATED < PICKED_UP < IN_TRANSIT < OUT_FOR_DELIVERY < DELIVERED
-- (stages may be skipped; same-status checkpoint events are allowed), CANCELLED from
-- any open stage. DELIVERED and CANCELLED are terminal: no further status change and
-- no new tracking events.
--
-- Violations raise SQLSTATE 'LT409', which the API maps to HTTP 409. The rules live
-- here so the stored procedure update_shipment_status(), direct SQL and every API
-- endpoint are held to the same rules.
--
-- Existing tracking history is never modified or deleted. The only data change is a
-- reconciliation of delivery rows whose status contradicts their shipment's status
-- (see the end of this file); it is idempotent.

BEGIN;

CREATE OR REPLACE FUNCTION public.shipment_stage(p_status character varying) RETURNS integer
    LANGUAGE sql IMMUTABLE
    AS $$
    SELECT CASE p_status
        WHEN 'CREATED' THEN 0
        WHEN 'PICKED_UP' THEN 1
        WHEN 'IN_TRANSIT' THEN 2
        WHEN 'OUT_FOR_DELIVERY' THEN 3
        WHEN 'DELIVERED' THEN 4
    END
$$;

CREATE OR REPLACE FUNCTION public.delivery_status_for_shipment(p_status character varying) RETURNS character varying
    LANGUAGE sql IMMUTABLE
    AS $$
    SELECT CASE p_status
        WHEN 'OUT_FOR_DELIVERY' THEN 'OUT_FOR_DELIVERY'
        WHEN 'DELIVERED' THEN 'DELIVERED'
        WHEN 'CANCELLED' THEN 'CANCELLED'
        ELSE 'PENDING'
    END::character varying
$$;

CREATE OR REPLACE FUNCTION public.delivery_status_compatible(p_delivery_status character varying, p_shipment_status character varying) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    AS $$
    SELECT p_delivery_status = public.delivery_status_for_shipment(p_shipment_status)
        OR (p_delivery_status = 'FAILED' AND p_shipment_status = 'OUT_FOR_DELIVERY')
$$;

-- Shipment: forward-only transitions, terminal states locked.
CREATE OR REPLACE FUNCTION public.enforce_shipment_status_transition() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.shipment_status IS NOT DISTINCT FROM OLD.shipment_status THEN
        RETURN NEW;
    END IF;

    IF OLD.shipment_status IN ('DELIVERED', 'CANCELLED') THEN
        RAISE EXCEPTION 'Shipment % is % and its status can no longer change (attempted %).',
            OLD.shipment_id, OLD.shipment_status, NEW.shipment_status
            USING ERRCODE = 'LT409';
    END IF;

    IF NEW.shipment_status <> 'CANCELLED'
       AND public.shipment_stage(NEW.shipment_status) < public.shipment_stage(OLD.shipment_status) THEN
        RAISE EXCEPTION 'Shipment % cannot move back from % to %.',
            OLD.shipment_id, OLD.shipment_status, NEW.shipment_status
            USING ERRCODE = 'LT409';
    END IF;

    IF NEW.shipment_status = 'DELIVERED' AND NEW.actual_delivery IS NULL THEN
        NEW.actual_delivery := GREATEST(LOCALTIMESTAMP, COALESCE(NEW.shipment_date, LOCALTIMESTAMP));
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_enforce_shipment_status_transition ON public.shipment;
CREATE TRIGGER trg_enforce_shipment_status_transition
    BEFORE UPDATE OF shipment_status ON public.shipment
    FOR EACH ROW EXECUTE FUNCTION public.enforce_shipment_status_transition();

-- Keep the delivery projection in step with any shipment status change, including
-- changes made through the stored procedure rather than a tracking event.
CREATE OR REPLACE FUNCTION public.sync_delivery_with_shipment() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE public.delivery
    SET delivery_status = public.delivery_status_for_shipment(NEW.shipment_status),
        delivery_date = CASE WHEN NEW.shipment_status = 'DELIVERED'
                             THEN COALESCE(delivery_date, NEW.actual_delivery)
                             ELSE delivery_date END
    WHERE shipment_id = NEW.shipment_id
      AND NOT public.delivery_status_compatible(delivery_status, NEW.shipment_status);
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_delivery_with_shipment ON public.shipment;
CREATE TRIGGER trg_sync_delivery_with_shipment
    AFTER UPDATE OF shipment_status ON public.shipment
    FOR EACH ROW
    WHEN (OLD.shipment_status IS DISTINCT FROM NEW.shipment_status)
    EXECUTE FUNCTION public.sync_delivery_with_shipment();

-- Tracking events: closed shipments accept none. Locking the shipment row
-- serialises concurrent events for the same shipment.
CREATE OR REPLACE FUNCTION public.guard_tracking_event() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    current_status character varying;
BEGIN
    SELECT shipment_status INTO current_status
    FROM public.shipment
    WHERE shipment_id = NEW.shipment_id
    FOR UPDATE;

    IF current_status IN ('DELIVERED', 'CANCELLED') THEN
        RAISE EXCEPTION 'Shipment % is % and accepts no further tracking events.',
            NEW.shipment_id, current_status
            USING ERRCODE = 'LT409';
    END IF;

    IF NEW.tracking_timestamp IS NULL THEN
        NEW.tracking_timestamp := LOCALTIMESTAMP;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_guard_tracking_event ON public.shipment_tracking;
CREATE TRIGGER trg_guard_tracking_event
    BEFORE INSERT ON public.shipment_tracking
    FOR EACH ROW EXECUTE FUNCTION public.guard_tracking_event();

-- Existing AFTER INSERT trigger function (same name and trigger). It still copies the
-- event status onto the shipment; it now also re-opens a FAILED delivery when a new
-- OUT_FOR_DELIVERY attempt is recorded.
CREATE OR REPLACE FUNCTION public.update_shipment_status() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE public.shipment
    SET shipment_status = NEW.status
    WHERE shipment_id = NEW.shipment_id;

    IF NEW.status = 'OUT_FOR_DELIVERY' THEN
        UPDATE public.delivery
        SET delivery_status = 'OUT_FOR_DELIVERY'
        WHERE shipment_id = NEW.shipment_id
          AND delivery_status = 'FAILED';
    END IF;

    RETURN NEW;
END;
$$;

-- Reconcile deliveries that contradict their shipment (for example a shipment marked
-- DELIVERED by tracking while its delivery still says PENDING). Only the status is
-- derived; a delivery date is copied only when the shipment recorded one. This runs
-- while the delivery guard is absent (it is dropped here on a re-run) so legacy rows
-- in any state can be corrected.
DROP TRIGGER IF EXISTS trg_enforce_delivery_status ON public.delivery;

UPDATE public.delivery d
SET delivery_status = public.delivery_status_for_shipment(s.shipment_status),
    delivery_date = CASE WHEN s.shipment_status = 'DELIVERED'
                         THEN COALESCE(d.delivery_date, s.actual_delivery)
                         ELSE d.delivery_date END
FROM public.shipment s
WHERE s.shipment_id = d.shipment_id
  AND NOT public.delivery_status_compatible(d.delivery_status, s.shipment_status);

-- Deliveries: a delivery status must be compatible with its shipment, and a
-- delivered or cancelled delivery is final.
CREATE OR REPLACE FUNCTION public.enforce_delivery_status() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    current_shipment_status character varying;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.delivery_status IS NOT DISTINCT FROM OLD.delivery_status THEN
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.delivery_status IN ('DELIVERED', 'CANCELLED') THEN
        RAISE EXCEPTION 'Delivery % is % and its status can no longer change (attempted %).',
            OLD.delivery_id, OLD.delivery_status, NEW.delivery_status
            USING ERRCODE = 'LT409';
    END IF;

    SELECT shipment_status INTO current_shipment_status
    FROM public.shipment
    WHERE shipment_id = NEW.shipment_id;

    IF current_shipment_status IS NOT NULL
       AND NOT public.delivery_status_compatible(NEW.delivery_status, current_shipment_status) THEN
        RAISE EXCEPTION 'Delivery status % is not compatible with shipment % status %.',
            NEW.delivery_status, NEW.shipment_id, current_shipment_status
            USING ERRCODE = 'LT409';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_enforce_delivery_status ON public.delivery;
CREATE TRIGGER trg_enforce_delivery_status
    BEFORE INSERT OR UPDATE OF delivery_status ON public.delivery
    FOR EACH ROW EXECUTE FUNCTION public.enforce_delivery_status();

COMMIT;
