import { useCallback, useEffect, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'
import { formatCurrency, formatDate, formatDateTime, formatLabel } from '../lib/format.js'
import { ErrorState, Icon, Notice, SkeletonRows, StatusBadge } from './ui.jsx'

const STATE_STYLE = {
  done: { icon: 'check', ring: 'bg-lime text-ink', text: 'text-ink', label: null },
  current: { icon: 'clock', ring: 'bg-ink text-lime ring-4 ring-lime/40', text: 'text-ink', label: 'Next' },
  upcoming: { icon: 'clock', ring: 'bg-cream text-mist', text: 'text-mist', label: null },
  not_reached: { icon: 'minus', ring: 'bg-cream text-mist', text: 'text-mist', label: 'Not reached' },
  skipped: { icon: 'minus', ring: 'bg-cream text-graphite', text: 'text-stone', label: 'No event recorded' },
  blocked: { icon: 'alert', ring: 'bg-warn-soft text-warn', text: 'text-warn', label: 'Blocked' },
  failed: { icon: 'alert', ring: 'bg-bad-soft text-bad', text: 'text-bad', label: 'Failed' },
  cancelled: { icon: 'x', ring: 'bg-bad-soft text-bad', text: 'text-bad', label: 'Cancelled' },
  not_recorded: { icon: 'info', ring: 'bg-cream text-graphite', text: 'text-stone', label: 'Not recorded' },
}

/**
 * The journey of one order, built entirely from persisted data returned by GET /orders/{id}/tracking.
 * The server decides what each viewer may see, so this component only renders what it is given.
 */
function OrderTracker({ orderId, session, onAuthExpired, refreshKey = 0, onLoaded }) {
  const [state, setState] = useState({ loading: true, error: '', data: null })

  const load = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: '' }))
    try {
      const data = await apiGet(`/orders/${orderId}/tracking`, session.accessToken)
      setState({ loading: false, error: '', data })
      onLoaded?.(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setState({ loading: false, error: err.message || 'Unable to load the order journey.', data: null })
    }
  }, [orderId, session.accessToken, onAuthExpired, onLoaded])

  useEffect(() => { load() }, [load, refreshKey])

  if (state.loading && !state.data) return <SkeletonRows rows={4} height="h-16" label="Loading order journey" />
  if (state.error) return <ErrorState title="Unable to load the journey" message={state.error} onRetry={load} />
  const { data } = state
  if (!data) return null

  const { order, shipment, route, warehouse, assignment, fulfilment, payment } = data
  // Customers get a calm, plain-language view. Operational exceptions are for the operations desk.
  const staff = Number(session.user.roleId) === 1 || Number(session.user.roleId) === 2
  const stageTone = { PAYMENT_FAILED: 'FAILED', CANCELLED: 'CANCELLED', DELIVERED: 'DELIVERED', AWAITING_PAYMENT: 'PENDING', AWAITING_APPROVAL: 'PENDING' }[data.stage?.key] ?? 'ACTIVE'
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        {data.stage && <StatusBadge status={stageTone} label={data.stage.label} />}
        {staff && <StatusBadge status={order.order_status} label={`Order ${formatLabel(order.order_status)}`} />}
        {staff && payment && <StatusBadge status={payment.payment_status} label={`Payment ${formatLabel(payment.payment_status)}`} />}
        {staff && shipment && <StatusBadge status={shipment.shipment_status} label={`Shipment ${formatLabel(shipment.shipment_status)}`} />}
        {staff && fulfilment && <StatusBadge status={fulfilment.status === 'BLOCKED' ? 'FAILED' : fulfilment.status === 'ASSIGNED' ? 'ACTIVE' : 'PENDING'} label={`Fulfilment ${formatLabel(fulfilment.status)}`} />}
      </div>

      {data.explanation && <Notice tone={staff && /blocked|failed|later|cancelled/i.test(data.explanation) ? 'error' : 'info'}>{data.explanation}</Notice>}
      {data.warnings?.map((warning) => <Notice key={warning} tone="info">{warning}</Notice>)}

      <section aria-labelledby={`journey-${orderId}`}>
        <h3 id={`journey-${orderId}`} className="eyebrow text-stone">Journey</h3>
        <ol className="mt-4">
          {data.milestones.map((step, index) => {
            const style = STATE_STYLE[step.state] ?? STATE_STYLE.upcoming
            const last = index === data.milestones.length - 1
            return (
              <li key={step.key} className="relative flex gap-4 pb-5 last:pb-0" aria-current={step.state === 'current' ? 'step' : undefined}>
                {!last && <span className="absolute top-9 bottom-0 left-[1.1rem] w-px bg-line" aria-hidden="true" />}
                <span className={`relative z-10 grid size-9 shrink-0 place-items-center rounded-full ${style.ring}`}><Icon name={style.icon} className="size-4" strokeWidth={2.2} /></span>
                <div className="min-w-0 flex-1 pt-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                    <p className={`font-semibold ${style.text}`}>{step.label}{style.label && <span className="eyebrow ml-2 text-mist">{style.label}</span>}</p>
                    {step.at && <time className="eyebrow text-mist">{formatDateTime(step.at)}</time>}
                  </div>
                  {step.detail && <p className="mt-0.5 text-sm leading-5 text-stone">{step.detail}</p>}
                </div>
              </li>
            )
          })}
        </ol>
      </section>

      <section className="grid gap-4 sm:grid-cols-2" aria-label="Shipment details">
        {(staff || warehouse) && <Fact icon="warehouse" label="Shipping from" value={warehouse ? [warehouse.warehouse_name, warehouse.city].filter(Boolean).join(', ') : 'Not yet planned'} detail={warehouse?.address} />}
        <Fact icon="pin" label="Delivering to" value={order.destination_city || 'City not recorded'} detail={order.shipping_address} />
        {(staff || route) && (
          <Fact
            icon="route"
            label="Route"
            value={route ? route.route_name : 'None configured'}
            detail={route ? `${route.source} → ${route.destination} · ${route.distance_km} km${route.estimated_duration ? ` · usually ${route.estimated_duration}` : ''}` : 'No configured route matches. None is required to ship this order.'}
          />
        )}
        {/* Shown only when a real assignment exists; before that the stage above says what is happening. */}
        {(staff || assignment) && (
          <Fact
            icon="truck"
            label="Driver and vehicle"
            value={assignment ? (assignment.driver_name ?? 'Driver assigned') : 'Not assigned yet'}
            detail={assignment ? (assignment.vehicle_recorded ? `${assignment.vehicle_registration} · ${formatLabel(assignment.vehicle_type)}` : (staff ? 'Vehicle was not recorded for this assignment.' : undefined)) : undefined}
          />
        )}
        {shipment?.estimated_delivery && <Fact icon="calendar" label={shipment.actual_delivery ? 'Delivered' : 'Estimated delivery'} value={formatDate(shipment.actual_delivery ?? shipment.estimated_delivery)} detail={shipment.actual_delivery ? undefined : 'Based on the route’s configured duration, not live tracking.'} />}
        {fulfilment?.route_basis && <Fact icon="info" label="Route matched by" value={fulfilment.route_basis === 'DESTINATION_CITY' ? 'Destination city chosen at checkout' : 'City read from the address (older order)'} />}
      </section>

      {fulfilment?.selection_note && (
        <section>
          <h3 className="eyebrow text-stone">Why this warehouse</h3>
          <p className="mt-2 rounded-2xl border border-line bg-paper p-4 text-sm leading-6 text-graphite">{fulfilment.selection_note}</p>
        </section>
      )}

      <section>
        <h3 className="eyebrow text-stone">Items</h3>
        <ul className="mt-3 divide-y divide-line rounded-2xl border border-line bg-paper">
          {data.items.map((item) => (
            <li key={item.product_id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
              <span className="font-medium">{item.product_name} <span className="text-stone">× {item.quantity}</span></span>
              <span className="font-semibold tabular-nums">{formatCurrency(item.item_total)}</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="eyebrow text-stone">Tracking events</h3>
        {data.tracking_events.length === 0 ? (
          <p className="mt-2 text-sm text-stone">No tracking events have been recorded yet. {data.live_tracking.note}</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {[...data.tracking_events].reverse().map((event, index) => (
              <li key={event.tracking_id} className={`rounded-2xl border p-3 text-sm ${index === 0 ? 'border-ink bg-paper' : 'border-line bg-ivory/60'}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold">{formatLabel(event.status)}{index === 0 && <span className="eyebrow ml-2 rounded-full bg-ink px-2 py-0.5 text-lime">Latest</span>}</span>
                  <time className="eyebrow text-mist">{formatDateTime(event.tracking_timestamp)}</time>
                </div>
                {(event.location || event.remarks) && <p className="mt-1 text-stone">{[event.location, event.remarks].filter(Boolean).join(' — ')}</p>}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-mist">{data.live_tracking.note}</p>
      </section>

      {data.fulfilment_events && (
        <section>
          <h3 className="eyebrow text-stone">Fulfilment log</h3>
          {data.fulfilment_events.length === 0 ? <p className="mt-2 text-sm text-stone">No planning events were recorded for this order.</p> : (
            <ul className="mt-3 space-y-1.5 text-sm">
              {data.fulfilment_events.map((event) => (
                <li key={event.event_id} className="flex flex-wrap items-baseline gap-x-3 rounded-xl bg-paper px-3 py-2 ring-1 ring-line">
                  <span className="eyebrow rounded-full bg-cream px-2 py-0.5 text-graphite">{formatLabel(event.event_type)}</span>
                  <span className="min-w-0 flex-1 text-graphite">{event.detail}</span>
                  <time className="eyebrow text-mist">{formatDateTime(event.created_at)}</time>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}

function Fact({ icon, label, value, detail }) {
  return (
    <div className="rounded-2xl border border-line bg-paper p-4">
      <p className="eyebrow flex items-center gap-2 text-stone"><Icon name={icon} className="size-3.5" />{label}</p>
      <p className="mt-2 font-semibold leading-snug">{value}</p>
      {detail && <p className="mt-1 text-sm leading-5 text-stone">{detail}</p>}
    </div>
  )
}

export default OrderTracker
