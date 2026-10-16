
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'

function Shipments({ session, onAuthExpired }) {
  const [shipments, setShipments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const loadShipments = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const data = await apiGet('/shipments', session.accessToken)

      if (!Array.isArray(data)) {
        throw new Error('Unexpected response from the shipments API.')
      }

      setShipments(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }

      setError(err.message || 'Unable to load shipments.')
    } finally {
      setLoading(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => {
    loadShipments()
  }, [loadShipments, refreshKey])

  const filteredShipments = useMemo(() => {
    const query = search.trim().toLowerCase()

    if (!query) return shipments

    return shipments.filter((shipment) =>
      String(shipment.shipment_id ?? '').toLowerCase().includes(query) ||
      String(shipment.order_id ?? '').toLowerCase().includes(query) ||
      String(shipment.shipment_status ?? '').toLowerCase().includes(query)
    )
  }, [shipments, search])

  const activeCount = shipments.filter((shipment) =>
    !['DELIVERED', 'CANCELLED'].includes(
      String(shipment.shipment_status ?? '').toUpperCase()
    )
  ).length

  const deliveredCount = shipments.filter(
    (shipment) =>
      String(shipment.shipment_status ?? '').toUpperCase() === 'DELIVERED'
  ).length

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-cyan-700">
            Shipment management
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
            Shipments
          </h2>
          <p className="mt-2 text-slate-600">
            Monitor shipment status and delivery progress.
          </p>
        </div>

        <button
          onClick={() => setRefreshKey((key) => key + 1)}
          disabled={loading}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? 'Refreshing...' : 'Refresh shipments'}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <SummaryCard label="Total shipments" value={shipments.length} />
        <SummaryCard label="Active shipments" value={activeCount} />
        <SummaryCard label="Delivered" value={deliveredCount} />
      </div>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <div>
            <h3 className="font-semibold text-slate-950">
              All shipments
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              {filteredShipments.length} of {shipments.length} shipments
            </p>
          </div>

          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search shipment, order or status..."
            aria-label="Search shipments"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100 sm:max-w-sm"
          />
        </div>

        {loading ? (
          <div className="space-y-3 p-6" aria-label="Loading shipments">
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
              Unable to load shipments
            </p>
            <p className="mt-2 text-sm text-slate-600">{error}</p>
            <button
              onClick={() => setRefreshKey((key) => key + 1)}
              className="mt-4 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
            >
              Try again
            </button>
          </div>
        ) : filteredShipments.length === 0 ? (
          <div className="px-6 py-14 text-center">
            <div className="mx-auto grid size-12 place-items-center rounded-xl bg-cyan-50 text-cyan-700">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                className="size-6"
                aria-hidden="true"
              >
                <path d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5z" />
                <path d="m4 7.5 8 4.5 8-4.5M12 12v9" />
              </svg>
            </div>
            <h3 className="mt-4 font-semibold text-slate-900">
              {search ? 'No matching shipments' : 'No shipments yet'}
            </h3>
            <p className="mt-2 text-sm text-slate-500">
              {search
                ? 'Try another shipment ID, order ID or status.'
                : 'Shipments will appear here when they are available.'}
            </p>
            {search && (
              <button
                onClick={() => setSearch('')}
                className="mt-3 text-sm font-semibold text-cyan-700 hover:text-cyan-800"
              >
                Clear search
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-6 py-4 font-semibold">Shipment ID</th>
                  <th className="px-6 py-4 font-semibold">Order ID</th>
                  <th className="px-6 py-4 font-semibold">Shipment date</th>
                  <th className="px-6 py-4 font-semibold">Estimated delivery</th>
                  <th className="px-6 py-4 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredShipments.map((shipment, index) => (
                  <tr
                    key={shipment.shipment_id ?? index}
                    className="transition hover:bg-slate-50"
                  >
                    <td className="whitespace-nowrap px-6 py-4 font-semibold text-slate-900">
                      #{shipment.shipment_id ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-slate-600">
                      {shipment.order_id ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-slate-600">
                      {formatDate(shipment.shipment_date)}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-slate-600">
                      {formatDate(shipment.estimated_delivery)}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4">
                      <StatusBadge status={shipment.shipment_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
    CANCELLED: 'bg-red-50 text-red-700 ring-red-600/20',
    PENDING: 'bg-amber-50 text-amber-700 ring-amber-600/20',
    IN_TRANSIT: 'bg-cyan-50 text-cyan-700 ring-cyan-600/20',
    DISPATCHED: 'bg-violet-50 text-violet-700 ring-violet-600/20',
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

export default Shipments
