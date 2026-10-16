import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'

function Orders({ session, onAuthExpired }) {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
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

    if (!query) return orders

    return orders.filter((order) => {
      const orderMatches =
        String(order.order_id ?? '').toLowerCase().includes(query) ||
        String(order.order_status ?? '').toLowerCase().includes(query)

      const itemMatches = (order.items ?? []).some((item) =>
        String(item.product_name ?? '').toLowerCase().includes(query)
      )

      return orderMatches || itemMatches
    })
  }, [orders, search])

  const pendingCount = orders.filter((order) =>
    !['DELIVERED', 'COMPLETED', 'CANCELLED'].includes(
      String(order.order_status ?? '').toUpperCase()
    )
  ).length

  function getOrderAmount(order) {
    if (
      order.total_amount !== null &&
      order.total_amount !== undefined &&
      order.total_amount !== ''
    ) {
      return formatAmount(order.total_amount)
    }

    const items = order.items ?? []

    if (items.length === 0) return '—'

    const total = items.reduce(
      (sum, item) =>
        sum +
        Number(item.item_total ?? (
          Number(item.quantity ?? 0) * Number(item.unit_price ?? 0)
        )),
      0
    )

    return formatAmount(total)
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-cyan-700">
            Order management
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
            Orders
          </h2>
          <p className="mt-2 text-slate-600">
            View your orders and the products included in each order.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setRefreshKey((key) => key + 1)}
          disabled={loading}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Refreshing...' : 'Refresh orders'}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <SummaryCard label="Total orders" value={loading ? '—' : orders.length} />
        <SummaryCard label="Open orders" value={loading ? '—' : pendingCount} />
      </div>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <div>
            <h3 className="font-semibold text-slate-950">All orders</h3>
            <p className="mt-1 text-sm text-slate-500">
              {filteredOrders.length} of {orders.length} orders
            </p>
          </div>

          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search order ID, status, or product..."
            aria-label="Search orders and products"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100 sm:max-w-xs"
          />
        </div>

        {loading ? (
          <div className="space-y-3 p-6" aria-label="Loading orders">
            {[1, 2, 3].map((item) => (
              <div
                key={item}
                className="h-16 animate-pulse rounded-lg bg-slate-100"
              />
            ))}
          </div>
        ) : error ? (
          <div className="p-8 text-center">
            <p className="font-semibold text-slate-900">
              Unable to load orders
            </p>
            <p className="mt-2 text-sm text-slate-600">{error}</p>
            <button
              type="button"
              onClick={() => setRefreshKey((key) => key + 1)}
              className="mt-4 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
            >
              Try again
            </button>
          </div>
        ) : filteredOrders.length === 0 ? (
          <div className="px-6 py-14 text-center">
            <h3 className="font-semibold text-slate-900">
              {search ? 'No matching orders' : 'No orders yet'}
            </h3>
            <p className="mt-2 text-sm text-slate-500">
              {search
                ? 'Try another order ID, status, or product name.'
                : 'Orders will appear here when they are available.'}
            </p>
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                className="mt-3 text-sm font-semibold text-cyan-700 hover:text-cyan-800"
              >
                Clear search
              </button>
            )}
          </div>
        ) : (
          <div className="divide-y divide-slate-200">
            {filteredOrders.map((order, index) => (
              <article
                key={order.order_id ?? index}
                className="p-5 transition hover:bg-slate-50 sm:p-6"
              >
                <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                  <div>
                    <h4 className="font-semibold text-slate-950">
                      Order #{order.order_id ?? '—'}
                    </h4>
                    <p className="mt-1 text-sm text-slate-500">
                      Order date: {formatDate(order.order_date)}
                    </p>
                    {order.shipping_address && (
                      <p className="mt-1 text-sm text-slate-500">
                        Shipping address: {order.shipping_address}
                      </p>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-3 sm:justify-end">
                    <StatusBadge status={order.order_status} />
                    <div className="sm:text-right">
                      <p className="text-xs text-slate-500">Order amount</p>
                      <p className="mt-1 font-semibold text-slate-950">
                        {getOrderAmount(order)}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="mt-5 overflow-hidden rounded-xl border border-slate-200">
                  <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
                    <h5 className="text-sm font-semibold text-slate-800">
                      Ordered items ({(order.items ?? []).length})
                    </h5>
                  </div>

                  {(order.items ?? []).length === 0 ? (
                    <p className="px-4 py-5 text-sm text-slate-500">
                      No item details were returned for this order.
                    </p>
                  ) : (
                    <div className="divide-y divide-slate-100">
                      {(order.items ?? []).map((item, itemIndex) => (
                        <div
                          key={`${item.product_id ?? itemIndex}-${itemIndex}`}
                          className="flex flex-col justify-between gap-3 px-4 py-4 sm:flex-row sm:items-center"
                        >
                          <div className="min-w-0">
                            <p className="font-medium text-slate-900">
                              {item.product_name ?? `Product #${item.product_id ?? '—'}`}
                            </p>
                            <p className="mt-1 text-sm text-slate-500">
                              Product ID: {item.product_id ?? '—'}
                            </p>
                          </div>

                          <div className="grid grid-cols-3 gap-4 text-sm sm:min-w-[300px]">
                            <div>
                              <p className="text-xs text-slate-500">Quantity</p>
                              <p className="mt-1 font-medium text-slate-800">
                                {item.quantity ?? '—'}
                              </p>
                            </div>
                            <div>
                              <p className="text-xs text-slate-500">Unit price</p>
                              <p className="mt-1 font-medium text-slate-800">
                                {formatAmount(item.unit_price)}
                              </p>
                            </div>
                            <div>
                              <p className="text-xs text-slate-500">Item total</p>
                              <p className="mt-1 font-semibold text-slate-900">
                                {formatAmount(
                                  item.item_total ??
                                    Number(item.quantity ?? 0) *
                                      Number(item.unit_price ?? 0)
                                )}
                              </p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function SummaryCard({ label, value }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
        {value}
      </p>
    </article>
  )
}

function StatusBadge({ status }) {
  const value = String(status ?? 'UNKNOWN')
  const normalized = value.toUpperCase()

  const styles = {
    DELIVERED: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
    COMPLETED: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
    CANCELLED: 'bg-red-50 text-red-700 ring-red-600/20',
    PENDING: 'bg-amber-50 text-amber-700 ring-amber-600/20',
    PROCESSING: 'bg-cyan-50 text-cyan-700 ring-cyan-600/20',
    CONFIRMED: 'bg-violet-50 text-violet-700 ring-violet-600/20',
  }

  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${
        styles[normalized] ?? 'bg-slate-100 text-slate-700 ring-slate-500/20'
      }`}
    >
      {value.replaceAll('_', ' ')}
    </span>
  )
}

function formatDate(value) {
  if (!value) return '—'

  const date = new Date(value)

  return Number.isNaN(date.valueOf())
    ? '—'
    : new Intl.DateTimeFormat('en-IN', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      }).format(date)
}

function formatAmount(value) {
  if (value === null || value === undefined || value === '') return '—'

  const amount = Number(value)

  return Number.isFinite(amount)
    ? new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 2,
      }).format(amount)
    : String(value)
}

export default Orders