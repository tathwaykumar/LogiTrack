import { useCallback, useEffect, useState } from 'react'
import { ApiError, apiGet, apiPost, queryString } from '../services/apiClient.js'
import { formatDate, formatLabel } from '../lib/format.js'
import OrderTracker from './OrderTracker.jsx'
import { DataTable, Drawer, EmptyState, ErrorState, FilterChips, IdTag, Notice, PageHeader, Pagination, Panel, RefreshButton, SearchField, SkeletonRows, StatTile, StatusBadge, stagger } from './ui.jsx'

const PAGE_SIZE = 15
const STATUSES = ['CREATED', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED']
const SORTS = [
  { value: 'shipment_id', label: 'Shipment' },
  { value: 'shipment_date', label: 'Shipped date' },
  { value: 'estimated_delivery', label: 'Estimated delivery' },
  { value: 'status', label: 'Status' },
  { value: 'customer', label: 'Customer' },
  { value: 'warehouse', label: 'Warehouse' },
]

/** The Operations Manager's shipment desk: server-side search, filters, sorting and paging. */
function OperationsShipments({ session, onAuthExpired, onNavigate }) {
  const [filters, setFilters] = useState({ q: '', status: '', assignment: '', delayed: false, sort: 'shipment_id', direction: 'desc' })
  const [page, setPage] = useState(1)
  const [result, setResult] = useState({ items: [], total: 0, pages: 1 })
  const [summary, setSummary] = useState(null)
  const [attention, setAttention] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [selected, setSelected] = useState(null)
  const [stockConfirmed, setStockConfirmed] = useState({})

  const fail = useCallback((err, fallback) => {
    if (err instanceof ApiError && err.status === 401) {
      onAuthExpired()
      return null
    }
    return err.message || fallback
  }, [onAuthExpired])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { ...filters, delayed: filters.delayed ? 'true' : '', page, page_size: PAGE_SIZE }
      const [rows, stats, orders] = await Promise.all([
        apiGet(`/operations/shipments${queryString(params)}`, session.accessToken),
        apiGet('/operations/summary', session.accessToken),
        apiGet('/operations/orders?stage=attention&page_size=10', session.accessToken),
      ])
      setResult(rows)
      setSummary(stats)
      setAttention(orders)
    } catch (err) {
      const message = fail(err, 'Unable to load shipments.')
      if (message) setError(message)
    } finally {
      setLoading(false)
    }
  }, [filters, page, session.accessToken, fail])

  useEffect(() => { load() }, [load, refreshKey])

  const update = (patch) => { setPage(1); setFilters((current) => ({ ...current, ...patch })) }
  const reload = () => setRefreshKey((key) => key + 1)

  async function recover(orderId) {
    setNotice(null)
    try {
      const outcome = await apiPost(`/operations/orders/${orderId}/recover-reservation`, { confirm_stock_not_deducted: true }, session.accessToken)
      setNotice({ tone: 'info', text: `Order #${orderId}: ${outcome.message}` })
      reload()
    } catch (err) {
      const message = fail(err, 'Could not reserve stock for this order.')
      if (message) setNotice({ tone: 'error', text: message })
    }
  }

  async function retry(orderId, approving = false) {
    setNotice(null)
    try {
      const path = approving ? `/operations/orders/${orderId}/approve` : `/operations/orders/${orderId}/retry-fulfilment`
      const outcome = await apiPost(path, {}, session.accessToken)
      const text = outcome.shipment_id
        ? `Order #${orderId} ${approving ? 'approved. ' : ''}Shipment #${outcome.shipment_id} ${outcome.driver_id ? 'has a driver and vehicle.' : 'is waiting for a driver and vehicle: open it to assign one.'}`
        : `Order #${orderId} ${approving ? 'approved, but ' : ''}${outcome.message ?? 'was re-checked.'}`
      setNotice({ tone: outcome.shipment_id ? 'info' : 'error', text })
      reload()
    } catch (err) {
      const message = fail(err, 'Retry failed.')
      if (message) setNotice({ tone: 'error', text: message })
    }
  }

  async function releaseAbandoned() {
    setNotice(null)
    try {
      const outcome = await apiPost('/operations/release-abandoned', {}, session.accessToken)
      setNotice({ tone: 'info', text: outcome.orders_cancelled ? `Cancelled ${outcome.orders_cancelled} abandoned unpaid order(s); ${outcome.units_released} unit(s) returned to stock.` : 'No unpaid orders have passed the abandonment limit.' })
      reload()
    } catch (err) {
      const message = fail(err, 'Could not release abandoned orders.')
      if (message) setNotice({ tone: 'error', text: message })
    }
  }

  const s = summary?.shipments
  const o = summary?.orders
  const statusOptions = [{ value: '', label: 'All' }, ...STATUSES.map((status) => ({ value: status, label: formatLabel(status) }))]
  const filtered = filters.q || filters.status || filters.assignment || filters.delayed

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Shipment operations"
        title="Shipments,"
        accent="under control."
        description="Search, assign and follow every shipment. Pending and blocked orders say exactly why."
        actions={<RefreshButton onClick={reload} loading={loading} label="Refresh shipments" />}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatTile label="Awaiting approval" value={o?.awaiting_approval ?? '—'} hint={`${o?.awaiting_payment ?? '—'} more awaiting payment`} icon="card" loading={!summary} />
        <StatTile label="Awaiting assignment" value={s?.awaiting_assignment ?? '—'} hint="Shipment without a driver" icon="users" tone="cream" loading={!summary} style={stagger(1)} />
        <StatTile label="In transit" value={s?.in_transit ?? '—'} icon="truck" tone="lime" loading={!summary} style={stagger(2)} />
        <StatTile label="Delayed" value={s?.delayed ?? '—'} hint="Past estimated delivery" icon="clock" loading={!summary} style={stagger(3)} />
        <StatTile label="Blocked orders" value={o?.blocked ?? '—'} hint="Cannot be planned" icon="alert" tone="ink" loading={!summary} style={stagger(4)} />
      </div>

      {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}

      {attention.total > 0 && (
        <Panel eyebrow="Needs attention" title="Orders not yet shipped" subtitle={`${attention.total} order${attention.total === 1 ? '' : 's'} to approve, or blocked`} actions={<button type="button" className="btn btn-outline" onClick={releaseAbandoned}>Release abandoned unpaid orders</button>}>
          <ul className="space-y-2">
            {attention.items.map((order) => (
              <li key={order.order_id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-paper px-4 py-3 text-sm">
                <div className="min-w-0">
                  <p className="font-semibold">Order #{order.order_id} <span className="font-normal text-stone">· {order.customer_name} · {order.destination_city ?? 'city not recorded'}</span></p>
                  <p className="mt-0.5 text-stone">{order.exception?.detail ?? order.reason_detail ?? (order.has_plan ? `Plan: ${formatLabel(order.fulfilment_status)}` : 'No fulfilment plan was recorded for this order (created before planning existed).')}</p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={order.fulfilment_status === 'BLOCKED' ? 'FAILED' : 'PENDING'} label={order.exception?.code === 'RESERVATION_MISSING' ? 'Stock not reserved' : order.payment_status === 'SUCCESS' && !order.approved ? 'Awaiting approval' : order.fulfilment_status ? formatLabel(order.fulfilment_status) : 'Unplanned'} />
                  {order.exception?.code === 'RESERVATION_MISSING' ? (
                    <>
                      <label className="flex max-w-56 items-start gap-2 text-xs text-stone">
                        <input type="checkbox" className="mt-0.5" checked={Boolean(stockConfirmed[order.order_id])} onChange={(event) => setStockConfirmed((current) => ({ ...current, [order.order_id]: event.target.checked }))} />
                        I confirm this order's stock was not already taken from inventory.
                      </label>
                      <button type="button" className="btn btn-ink py-1.5!" disabled={!stockConfirmed[order.order_id]} onClick={() => recover(order.order_id)}>Recover reservation</button>
                    </>
                  ) : order.payment_status === 'SUCCESS' && !order.approved
                    ? <button type="button" className="btn btn-ink py-1.5!" onClick={() => retry(order.order_id, true)}>Approve</button>
                    : <button type="button" className="btn btn-outline py-1.5!" onClick={() => retry(order.order_id)}>Re-check</button>}
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel
        bodyClassName="p-0"
        title="All shipments"
        subtitle={`${result.total} shipment${result.total === 1 ? '' : 's'}${filtered ? ' match' : ''}`}
        actions={<SearchField value={filters.q} onChange={(q) => update({ q })} placeholder="Shipment, order, customer, driver, vehicle…" label="Search shipments" className="w-full sm:w-80" />}
      >
        <div className="space-y-3 border-b border-line px-5 py-3 sm:px-6">
          <FilterChips label="Filter by status" options={statusOptions} value={filters.status} onChange={(status) => update({ status })} />
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <FilterChips
              label="Filter by assignment"
              options={[{ value: '', label: 'Any driver state' }, { value: 'unassigned', label: 'Unassigned' }, { value: 'assigned', label: 'Assigned' }]}
              value={filters.assignment}
              onChange={(assignment) => update({ assignment })}
            />
            <label className="inline-flex items-center gap-2 font-medium">
              <input type="checkbox" checked={filters.delayed} onChange={(event) => update({ delayed: event.target.checked })} /> Delayed only
            </label>
            <label className="ml-auto inline-flex items-center gap-2 text-stone">Sort
              <select className="input py-1.5!" value={filters.sort} onChange={(event) => update({ sort: event.target.value })} aria-label="Sort shipments by">
                {SORTS.map((sort) => <option key={sort.value} value={sort.value}>{sort.label}</option>)}
              </select>
              <button type="button" className="btn btn-outline py-1.5!" onClick={() => update({ direction: filters.direction === 'asc' ? 'desc' : 'asc' })} aria-label={`Sort direction: ${filters.direction === 'asc' ? 'ascending' : 'descending'}`}>{filters.direction === 'asc' ? '↑ Asc' : '↓ Desc'}</button>
            </label>
          </div>
        </div>

        {loading && result.items.length === 0 ? (
          <SkeletonRows rows={5} label="Loading shipments" />
        ) : error ? (
          <ErrorState title="Unable to load shipments" message={error} onRetry={reload} />
        ) : result.items.length === 0 ? (
          <EmptyState icon="route" title={filtered ? 'No matching shipments' : 'No shipments yet'} text={filtered ? 'Try different filters.' : 'Shipments appear once a paid order is dispatched.'} action={filtered && <button type="button" className="btn btn-ink" onClick={() => update({ q: '', status: '', assignment: '', delayed: false })}>Clear filters</button>} />
        ) : (
          <DataTable head={['Shipment', 'Order / customer', 'From → to', 'Driver / vehicle', 'Estimated', 'Status', '']} minWidth={1000} caption="Shipments">
            {result.items.map((row) => (
              <tr key={row.shipment_id}>
                <td><IdTag>{row.shipment_id}</IdTag></td>
                <td><span className="font-medium">#{row.order_id}</span><span className="block text-xs text-stone">{row.customer_name}</span></td>
                <td><span className="block">{row.warehouse_name}</span><span className="block text-xs text-stone">→ {row.destination_city ?? row.route_destination}</span></td>
                <td>
                  {row.driver_name ? (
                    <><span className="block">{row.driver_name}</span><span className="block text-xs text-stone">{row.vehicle_registration ?? (row.vehicle_recorded ? '—' : 'vehicle not recorded')}</span></>
                  ) : <span className="text-warn">{row.pending_reason ?? 'Not assigned'}</span>}
                </td>
                <td>{formatDate(row.actual_delivery ?? row.estimated_delivery)}{row.delayed && <span className="eyebrow ml-2 text-bad">Delayed</span>}</td>
                <td><StatusBadge status={row.shipment_status} /></td>
                <td><button type="button" className="btn btn-outline py-1.5!" onClick={() => setSelected(row)}>Open</button></td>
              </tr>
            ))}
          </DataTable>
        )}
        <Pagination page={page} pages={result.pages} total={result.total} pageSize={PAGE_SIZE} onPage={setPage} />
      </Panel>

      {onNavigate && <p className="text-sm text-stone">Event history by shipment? <button type="button" onClick={() => onNavigate('tracking')} className="font-semibold text-ink underline decoration-lime decoration-2 underline-offset-4">Open tracking</button></p>}

      <Drawer open={Boolean(selected)} onClose={() => setSelected(null)} eyebrow={selected ? `Order #${selected.order_id}` : ''} title={selected ? `Shipment #${selected.shipment_id}` : ''} wide>
        {selected && (
          <div className="space-y-8">
            <AssignmentPanel shipment={selected} session={session} onAuthExpired={onAuthExpired} onChanged={() => { reload(); setSelected(null) }} />
            <OrderTracker orderId={selected.order_id} session={session} onAuthExpired={onAuthExpired} refreshKey={refreshKey} />
          </div>
        )}
      </Drawer>
    </div>
  )
}

function AssignmentPanel({ shipment, session, onAuthExpired, onChanged }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [choice, setChoice] = useState('')
  const [saving, setSaving] = useState(false)
  const closed = ['DELIVERED', 'CANCELLED'].includes(shipment.shipment_status)

  useEffect(() => {
    if (closed) return
    let alive = true
    apiGet(`/operations/shipments/${shipment.shipment_id}/assignment-options`, session.accessToken)
      .then((value) => alive && setData(value))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) onAuthExpired()
        else if (alive) setError(err.message || 'Unable to load assignment options.')
      })
    return () => { alive = false }
  }, [shipment.shipment_id, closed, session.accessToken, onAuthExpired])

  if (closed) return <Notice tone="info">This shipment is {formatLabel(shipment.shipment_status).toLowerCase()}, so its assignment can no longer change.</Notice>
  if (error) return <Notice tone="error">{error}</Notice>
  if (!data) return <SkeletonRows rows={2} height="h-12" label="Loading assignment options" />

  const eligible = data.options.filter((option) => option.eligible)
  const blocked = data.options.filter((option) => !option.eligible)
  const key = (option) => `${option.driver_id}:${option.vehicle_id ?? ''}`

  async function save() {
    const option = data.options.find((candidate) => key(candidate) === choice)
    if (!option) return
    setSaving(true)
    setError('')
    try {
      await apiPost(`/shipments/${shipment.shipment_id}/assignment`, { driver_id: option.driver_id, vehicle_id: option.vehicle_id }, session.accessToken)
      onChanged()
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onAuthExpired()
      else setError(err.message || 'Assignment failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-label="Driver and vehicle assignment" className="space-y-4 rounded-2xl border border-line bg-paper p-5">
      <div>
        <h3 className="eyebrow text-stone">{data.current ? 'Reassign driver and vehicle' : 'Assign driver and vehicle'}</h3>
        <p className="mt-1 text-sm text-stone">
          {shipment.driver_name ? `Currently ${shipment.driver_name}${shipment.vehicle_registration ? ` in ${shipment.vehicle_registration}` : ''}.` : 'No driver is assigned yet.'}
          {data.weight_note ? ` ${data.weight_note}` : data.shipment_weight_kg != null ? ` Load: ${data.shipment_weight_kg} kg.` : ''}
        </p>
      </div>
      {eligible.length === 0 ? (
        <Notice tone="error">{data.summary ?? 'No driver and vehicle pair is currently eligible.'}</Notice>
      ) : (
        <div className="flex flex-col gap-3 sm:flex-row">
          <select className="input flex-1" value={choice} onChange={(event) => setChoice(event.target.value)} aria-label="Choose driver and vehicle">
            <option value="">Choose an eligible driver…</option>
            {eligible.map((option) => (
              <option key={key(option)} value={key(option)}>
                {option.driver_name} · {option.vehicle_registration} · {option.open_deliveries} open{option.remaining_capacity_kg != null ? ` · ${option.remaining_capacity_kg} kg free` : ''}
              </option>
            ))}
          </select>
          <button type="button" className="btn btn-ink" disabled={!choice || saving} onClick={save}>{saving ? 'Saving…' : data.current ? 'Reassign' : 'Assign'}</button>
        </div>
      )}
      {blocked.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold">{blocked.length} not eligible</summary>
          <ul className="mt-2 space-y-1 text-stone">
            {blocked.map((option) => <li key={key(option)}><span className="font-medium text-ink">{option.driver_name}</span>{option.vehicle_registration ? ` (${option.vehicle_registration})` : ''}: {option.reasons.join('; ')}</li>)}
          </ul>
        </details>
      )}
    </section>
  )
}

export default OperationsShipments
