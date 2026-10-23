-- Migration 007: a shipment no longer needs a configured route.
--
-- A paid, approved order is fulfilled from a warehouse that has the stock. Route configuration is optional
-- reference data: when exactly one active route matches the origin and destination it is recorded (and its
-- configured duration gives the estimated delivery); otherwise route_id stays NULL and no route, distance or
-- ETA is invented.
--
-- Relaxes a constraint only (DROP NOT NULL), so it is safe to re-run and changes no existing row. Existing
-- shipments keep the route they have. The foreign key to route(route_id) is unchanged.

ALTER TABLE public.shipment ALTER COLUMN route_id DROP NOT NULL;
