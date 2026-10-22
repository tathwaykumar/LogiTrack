import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'
import { formatCurrency, formatDate, formatLabel } from '../lib/format.js'
import ProductImage from './ProductImage.jsx'
import { EmptyState, ErrorState, FilterChips, Icon, PageHeader, RefreshButton, SearchField, SkeletonRows, StatTile, StatusBadge, stagger } from './ui.jsx'

const ORDER_STATUSES = ['PENDING', 'CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED']

function Orders({ session, onAuthExpired }) {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [refreshKey, setRefreshKey] = useState(0)

  const loadOrders = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const data = await apiGet('/orders', session.accessToken)

      if (!Array.isArray(data)) {
        throw new Error('Unexpected response from the orders API.')
      }

      setOrders(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }

      setError(err.message || 'Unable to load orders.')
    } finally {
      setLoading(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => {
    loadOrders()
  }, [loadOrders, refreshKey])

  const filteredOrders = useMemo(() => {
    const query = search.trim().toLowerCase()

    return orders.filter((order) => {
      if (statusFilter !== 'ALL' && String(order.order_status ?? '').toUpperCase() !== statusFilter) return false
      if (!query) return true

      const orderMatches =
        String(order.order_id ?? '').toLowerCase().includes(query) ||
        String(order.order_status ?? '').toLowerCase().includes(query)

      const itemMatches = (order.items ?? []).some((item) =>
        String(item.product_name ?? '').toLowerCase().includes(query)
      )

      return orderMatches || itemMatches
    })
  }, [orders, search, statusFilter])

  const pendingCount = orders.filter((order) =>
    !['DELIVERED', 'COMPLETED', 'CANCELLED'].includes(
      String(order.order_status ?? '').toUpperCase()
    )
  ).length

  const statusCounts = orders.reduce((counts, order) => {
    const key = String(order.order_status ?? '').toUpperCase()
    return { ...counts, [key]: (counts[key] ?? 0) + 1 }
  }, {})
  const statusOptions = [
    { value: 'ALL', label: 'All', count: orders.length },
    ...ORDER_STATUSES.filter((status) => statusCounts[status]).map((status) => ({ value: status, label: formatLabel(status), count: statusCounts[status] })),
  ]

  const totalValue = orders.reduce((sum, order) => sum + (orderAmountValue(order) ?? 0), 0)

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Order management"
        title="Orders,"
        accent="line by line."
        description="Every order with the products, quantities and amounts it contains."
        actions={<RefreshButton onClick={() => setRefreshKey((key) => key + 1)} loading={loading} label="Refresh orders" />}
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile label="Total orders" value={loading ? '—' : orders.length} icon="box" loading={loading && !orders.length} />
        <StatTile label="Open orders" value={loading ? '—' : pendingCount} hint="Not yet delivered or cancelled" icon="clock" tone="lime" loading={loading && !orders.length} style={stagger(1)} />
        <StatTile label="Order value" value={loading ? '—' : formatCurrency(totalValue)} hint="Sum of item totals" icon="wallet" tone="ink" loading={loading && !orders.length} style={stagger(2)} />
      </div>

      <section className="space-y-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <FilterChips label="Filter orders by status" options={statusOptions} value={statusFilter} onChange={setStatusFilter} />
          <SearchField value={search} onChange={setSearch} placeholder="Order ID, status or product…" label="Search orders and products" className="lg:w-80" />
        </div>
        <p className="text-sm text-stone" aria-live="polite">{loading ? 'Loading orders…' : `${filteredOrders.length} of ${orders.length} orders`}</p>

        {loading && orders.length === 0 ? (
          <div className="panel"><SkeletonRows rows={3} height="h-28" label="Loading orders" /></div>
        ) : error ? (
          <div className="panel"><ErrorState title="Unable to load orders" message={error} onRetry={() => setRefreshKey((key) => key + 1)} /></div>
        ) : filteredOrders.length === 0 ? (
          <div className="panel">
            <EmptyState
              icon="box"
              title={search || statusFilter !== 'ALL' ? 'No matching orders' : 'No orders yet'}
              text={search || statusFilter !== 'ALL' ? 'Try another order ID, status, or product name.' : 'Orders will appear here when they are available.'}
              action={(search || statusFilter !== 'ALL') && <button type="button" onClick={() => { setSearch(''); setStatusFilter('ALL') }} className="btn btn-ink">Clear filters</button>}
            />
          </div>
        ) : (
          <div className="space-y-4">
            {filteredOrders.map((order, index) => <OrderTicket key={order.order_id ?? index} order={order} index={index} />)}
          </div>
        )}
      </section>
    </div>
  )
}

function orderAmountValue(order) {
  if (order.total_amount !== null && order.total_amount !== undefined && order.total_amount !== '') return Number(order.total_amount)
  const items = order.items ?? []
  if (items.length === 0) return null
  return items.reduce((sum, item) => sum + Number(item.item_total ?? Number(item.quantity ?? 0) * Number(item.unit_price ?? 0)), 0)
}

function OrderTicket({ order, index }) {
  const items = order.items ?? []
  const amount = orderAmountValue(order)
  return (
    <article className="panel animate-rise overflow-hidden" style={stagger(Math.min(index, 6), 50)}>
      <div className="grid gap-0 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <div className="flex flex-col justify-between gap-6 border-b border-line bg-ivory/60 p-5 sm:p-6 lg:border-r lg:border-b-0">
          <div>
            <p className="eyebrow text-stone">Order</p>
            <p className="font-display mt-1 text-4xl font-semibold">#{order.order_id ?? '—'}</p>
            <div className="mt-3"><StatusBadge status={order.order_status} /></div>
          </div>
          <dl className="space-y-3 text-sm">
            <div className="flex items-center gap-2 text-stone"><Icon name="calendar" className="size-4" /><dd>{formatDate(order.order_date)}</dd></div>
            {order.shipping_address && <div className="flex items-start gap-2 text-stone"><Icon name="pin" className="mt-0.5 size-4" /><dd className="leading-5">{order.shipping_address}</dd></div>}
            <div className="border-t border-line pt-3">
              <dt className="eyebrow text-stone">Order amount</dt>
              <dd className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-ink">{amount === null ? '—' : formatCurrency(amount)}</dd>
            </div>
          </dl>
        </div>

        <div className="p-2 sm:p-3">
          {items.length === 0 ? (
            <p className="px-4 py-8 text-sm text-stone">No item details were returned for this order.</p>
          ) : (
            <ul className="divide-y divide-line">
              {items.map((item, itemIndex) => (
                <li key={`${item.product_id ?? itemIndex}-${itemIndex}`} className="flex flex-col gap-3 px-3 py-3 sm:flex-row sm:items-center">
                  <div className="flex min-w-0 flex-1 items-center gap-4">
                    <ProductImage name={item.product_name} className="size-16 shrink-0 rounded-2xl" />
                    <div className="min-w-0">
                      <p className="truncate font-semibold">{item.product_name ?? `Product #${item.product_id ?? '—'}`}</p>
                      <p className="font-mono text-xs text-stone">SKU {item.product_id ?? '—'}</p>
                    </div>
                  </div>
                  <dl className="grid grid-cols-3 gap-4 text-sm sm:w-80 sm:text-right">
                    <div><dt className="eyebrow text-mist">Qty</dt><dd className="mt-1 font-semibold">{item.quantity ?? '—'}</dd></div>
                    <div><dt className="eyebrow text-mist">Unit</dt><dd className="mt-1 text-graphite">{formatCurrency(item.unit_price)}</dd></div>
                    <div><dt className="eyebrow text-mist">Total</dt><dd className="mt-1 font-semibold">{formatCurrency(item.item_total ?? Number(item.quantity ?? 0) * Number(item.unit_price ?? 0))}</dd></div>
                  </dl>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </article>
  )
}

export default Orders
