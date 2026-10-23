import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet, apiPost, apiPut } from '../services/apiClient.js'
import { formatDate } from '../lib/format.js'
import { DELIVERY_GROUPS, deliveryGroupId, deliveryStatus, summariseDeliveries } from '../lib/status.js'
import OrderTracker from './OrderTracker.jsx'
import { Drawer, EmptyState, ErrorState, Icon, Notice, PageHeader, RefreshButton, SearchField, StatTile, StatusBadge, stagger } from './ui.jsx'

const COLUMN_TONES = { pending: 'bg-cream', moving: 'bg-lime', done: 'bg-ok-soft', issues: 'bg-bad-soft' }
// The backend validates every transition; this only decides which button to offer.
const NEXT_STEP = {
  CREATED: { status: 'PICKED_UP', label: 'Mark picked up' },
  PICKED_UP: { status: 'IN_TRANSIT', label: 'Mark in transit' },
  IN_TRANSIT: { status: 'OUT_FOR_DELIVERY', label: 'Out for delivery' },
  OUT_FOR_DELIVERY: { status: 'DELIVERED', label: 'Mark delivered' },
}

const COLUMNS = DELIVERY_GROUPS.map((group) => ({ ...group, tone: COLUMN_TONES[group.id] }))

function Deliveries({ session, onAuthExpired }) {
  const [deliveries, setDeliveries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [selected, setSelected] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [notice, setNotice] = useState(null)
  const isDriver = Number(session.user.roleId) === 3

  const loadDeliveries = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const data = await apiGet('/deliveries', session.accessToken)

      if (!Array.isArray(data)) {
        throw new Error('Unexpected response from the deliveries API.')
      }

      setDeliveries(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }

      setError(err.message || 'Unable to load deliveries.')
    } finally {
      setLoading(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => {
    loadDeliveries()
  }, [loadDeliveries, refreshKey])

  const filteredDeliveries = useMemo(() => {
    const query = search.trim().toLowerCase()

    if (!query) return deliveries

    return deliveries.filter((delivery) =>
      String(delivery.delivery_id ?? '').toLowerCase().includes(query) ||
      String(delivery.shipment_id ?? '').toLowerCase().includes(query) ||
      String(delivery.delivery_address ?? '').toLowerCase().includes(query) ||
      deliveryStatus(delivery).toLowerCase().includes(query)
    )
  }, [deliveries, search])

  async function advance(delivery, action) {
    setBusyId(delivery.delivery_id)
    setNotice(null)
    try {
      if (action === 'FAILED') {
        await apiPut(`/deliveries/${delivery.delivery_id}/status`, { delivery_status: 'FAILED' }, session.accessToken)
      } else {
        await apiPost('/tracking', { shipment_id: delivery.shipment_id, status: action }, session.accessToken)
      }
      setRefreshKey((key) => key + 1)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setNotice({ tone: 'error', text: err.message || 'The update was rejected.' })
    } finally {
      setBusyId(null)
    }
  }

  const summary = summariseDeliveries(deliveries)
  const columns = COLUMNS.map((column) => ({
    ...column,
    items: filteredDeliveries.filter((delivery) => deliveryGroupId(delivery) === column.id),
  }))

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Delivery management"
        title="The last mile,"
        accent="on one board."
        description="Monitor delivery progress and completion status, grouped by stage."
        actions={<RefreshButton onClick={() => setRefreshKey((key) => key + 1)} loading={loading} label="Refresh deliveries" />}
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile label="Total deliveries" value={deliveries.length} icon="truck" loading={loading && !deliveries.length} />
        <StatTile label="Open" value={summary.open} hint="Pending, out for delivery or failed attempt" icon="clock" tone="lime" loading={loading && !deliveries.length} style={stagger(1)} />
        <StatTile label="Delivered" value={summary.delivered} icon="check" tone="ink" loading={loading && !deliveries.length} style={stagger(2)} />
      </div>

      {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-stone" aria-live="polite">{loading ? 'Loading deliveries…' : `${filteredDeliveries.length} of ${deliveries.length} deliveries`}</p>
        <SearchField value={search} onChange={setSearch} placeholder="Delivery, shipment, address or status…" label="Search deliveries" className="sm:w-96" />
      </div>

      {loading && deliveries.length === 0 ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{COLUMNS.map((column) => <div key={column.id} className="skeleton h-72 rounded-[1.5rem]!" />)}</div>
      ) : error ? (
        <div className="panel"><ErrorState title="Unable to load deliveries" message={error} onRetry={() => setRefreshKey((key) => key + 1)} /></div>
      ) : filteredDeliveries.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon="truck"
            title={search ? 'No matching deliveries' : 'No deliveries yet'}
            text={search ? 'Try another delivery ID, shipment ID or status.' : 'Delivery records will appear here when available.'}
            action={search && <button type="button" onClick={() => setSearch('')} className="btn btn-ink">Clear search</button>}
          />
        </div>
      ) : (
        <div className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-4">
          {columns.map((column, columnIndex) => (
            <section key={column.id} aria-label={column.title} className="animate-rise rounded-[1.5rem] border border-line bg-ivory/70 p-3" style={stagger(columnIndex)}>
              <header className="flex items-center justify-between px-2 pt-1 pb-3">
                <h2 className="flex items-center gap-2 font-display text-lg font-semibold">
                  <span className={`size-2.5 rounded-full ring-1 ring-ink/20 ${column.tone}`} aria-hidden="true" />
                  {column.title}
                </h2>
                <span className="rounded-full bg-paper px-2.5 py-0.5 text-xs font-semibold ring-1 ring-line">{column.items.length}</span>
              </header>
              <ul className="space-y-2.5">
                {column.items.map((delivery, index) => (
                  <li key={delivery.delivery_id ?? index} className="rounded-2xl border border-line bg-paper p-4 shadow-[var(--shadow-card)] transition hover:-translate-y-0.5 hover:border-ink/40">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="eyebrow text-stone">Delivery</p>
                        <p className="font-display text-2xl font-semibold">#{delivery.delivery_id ?? '—'}</p>
                      </div>
                      <StatusBadge status={delivery.delivery_status ?? delivery.status} />
                    </div>
                    <dl className="mt-3 space-y-1.5 text-sm text-graphite">
                      <div className="flex items-center gap-2"><Icon name="route" className="size-4 text-stone" /><dt className="sr-only">Shipment</dt><dd>Shipment #{delivery.shipment_id ?? '—'}</dd></div>
                      {delivery.delivery_address && <div className="flex items-start gap-2"><Icon name="pin" className="mt-0.5 size-4 text-stone" /><dt className="sr-only">Address</dt><dd className="leading-5">{delivery.delivery_address}</dd></div>}
                      <div className="flex items-center gap-2"><Icon name="calendar" className="size-4 text-stone" /><dt className="sr-only">Delivery date</dt><dd>{formatDate(delivery.actual_delivery_date ?? delivery.delivery_date ?? delivery.scheduled_date, deliveryStatus(delivery) === 'DELIVERED' ? 'Delivery date not recorded' : 'Not delivered yet')}</dd></div>
                      {(delivery.driver_name || delivery.vehicle_registration) && (
                        <div className="flex items-center gap-2"><Icon name="truck" className="size-4 text-stone" /><dt className="sr-only">Driver and vehicle</dt><dd>{[delivery.driver_name, delivery.vehicle_registration].filter(Boolean).join(' · ')}{!delivery.vehicle_registration && ' · vehicle not recorded'}</dd></div>
                      )}
                      {delivery.assigned_at && <div className="flex items-center gap-2"><Icon name="clock" className="size-4 text-stone" /><dt className="sr-only">Assigned</dt><dd>Assigned {formatDate(delivery.assigned_at)}</dd></div>}
                    </dl>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {isDriver && NEXT_STEP[delivery.shipment_status] && !['DELIVERED', 'CANCELLED'].includes(delivery.delivery_status) && (
                        <button type="button" className="btn btn-ink py-1.5!" disabled={busyId === delivery.delivery_id} onClick={() => advance(delivery, NEXT_STEP[delivery.shipment_status].status)}>{NEXT_STEP[delivery.shipment_status].label}</button>
                      )}
                      {isDriver && delivery.shipment_status === 'OUT_FOR_DELIVERY' && delivery.delivery_status !== 'FAILED' && (
                        <button type="button" className="btn btn-outline py-1.5!" disabled={busyId === delivery.delivery_id} onClick={() => advance(delivery, 'FAILED')}>Delivery attempt failed</button>
                      )}
                      {delivery.order_id && <button type="button" className="btn btn-outline py-1.5!" onClick={() => setSelected(delivery)}>Details</button>}
                    </div>
                  </li>
                ))}
                {column.items.length === 0 && <li className="rounded-2xl border border-dashed border-sand px-4 py-8 text-center text-sm text-mist">Nothing here</li>}
              </ul>
            </section>
          ))}
        </div>
      )}

      <Drawer open={Boolean(selected)} onClose={() => setSelected(null)} eyebrow={selected ? `Order #${selected.order_id}` : ''} title={selected ? `Delivery #${selected.delivery_id}` : ''} wide>
        {selected && <OrderTracker orderId={selected.order_id} session={session} onAuthExpired={onAuthExpired} refreshKey={refreshKey} />}
      </Drawer>
    </div>
  )
}

export default Deliveries
