// Shared status definitions. They mirror the backend rules (main.py / migration 003):
// the shipment status is the source of truth and the delivery status is derived from it.

export const SHIPMENT_FLOW = ['CREATED', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED']
export const SHIPMENT_STATUSES = [...SHIPMENT_FLOW, 'CANCELLED']
export const TERMINAL_SHIPMENT_STATUSES = ['DELIVERED', 'CANCELLED']

export function isClosedShipment(status) {
  return TERMINAL_SHIPMENT_STATUSES.includes(String(status ?? '').toUpperCase())
}

/** Statuses a tracking update may set from the current one: same or later stage, or CANCELLED. */
export function nextShipmentStatuses(current) {
  const status = String(current ?? '').toUpperCase()
  if (isClosedShipment(status)) return []
  const index = SHIPMENT_FLOW.indexOf(status)
  return [...SHIPMENT_FLOW.slice(Math.max(index, 0)), 'CANCELLED']
}

// Delivery groups. Every delivery falls in exactly one group, so the board columns,
// the summary tiles and the driver dashboard all count the same records.
export const DELIVERY_GROUPS = [
  { id: 'pending', title: 'Pending', statuses: ['PENDING'] },
  { id: 'moving', title: 'Out for delivery', statuses: ['OUT_FOR_DELIVERY'] },
  { id: 'done', title: 'Delivered', statuses: ['DELIVERED'] },
  { id: 'issues', title: 'Exceptions', statuses: ['FAILED', 'CANCELLED'] },
]

export function deliveryStatus(delivery) {
  return String(delivery?.delivery_status ?? delivery?.status ?? '').toUpperCase()
}

export function deliveryGroupId(delivery) {
  const status = deliveryStatus(delivery)
  return DELIVERY_GROUPS.find((group) => group.statuses.includes(status))?.id ?? 'pending'
}

/** Open = still needs work: pending, out for delivery, or a failed attempt awaiting retry. */
export function isOpenDelivery(delivery) {
  return !['DELIVERED', 'CANCELLED'].includes(deliveryStatus(delivery))
}

export function summariseDeliveries(deliveries) {
  const counts = Object.fromEntries(DELIVERY_GROUPS.map((group) => [group.id, 0]))
  for (const delivery of deliveries) counts[deliveryGroupId(delivery)] += 1
  return {
    total: deliveries.length,
    open: deliveries.filter(isOpenDelivery).length,
    delivered: counts.done,
    groups: counts,
  }
}
