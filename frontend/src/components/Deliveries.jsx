
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'

function Deliveries({ session, onAuthExpired }) {
  const [deliveries, setDeliveries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

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
      String(delivery.delivery_status ?? delivery.status ?? '')
        .toLowerCase()
        .includes(query)
    )
  }, [deliveries, search])

  const deliveredCount = deliveries.filter((delivery) =>
    ['DELIVERED', 'COMPLETED'].includes(
      String(delivery.delivery_status ?? delivery.status ?? '').toUpperCase()
    )
  ).length

  const pendingCount = deliveries.filter((delivery) =>
    ['PENDING', 'SCHEDULED', 'IN_PROGRESS', 'OUT_FOR_DELIVERY'].includes(
      String(delivery.delivery_status ?? delivery.status ?? '').toUpperCase()
    )
  ).length

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-cyan-700">
            Delivery management
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
            Deliveries
          </h2>
          <p className="mt-2 text-slate-600">
            Monitor delivery progress and completion status.
          </p>
        </div>

        <button
          onClick={() => setRefreshKey((key) => key + 1)}
          disabled={loading}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? 'Refreshing...' : 'Refresh deliveries'}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <SummaryCard label="Total deliveries" value={deliveries.length} />
        <SummaryCard label="Pending deliveries" value={pendingCount} />
        <SummaryCard label="Delivered" value={deliveredCount} />
      </div>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <div>
            <h3 className="font-semibold text-slate-950">
              All deliveries
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              {filteredDeliveries.length} of {deliveries.length} deliveries
            </p>
          </div>

          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search delivery, shipment or status..."
            aria-label="Search deliveries"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100 sm:max-w-sm"
          />
        </div>

        {loading ? (
          <div className="space-y-3 p-6" aria-label="Loading deliveries">
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
              Unable to load deliveries
            </p>
            <p className="mt-2 text-sm text-slate-600">{error}</p>
            <button
              onClick={() => setRefreshKey((key) => key + 1)}
              className="mt-4 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
            >
              Try again
            </button>
          </div>
        ) : filteredDeliveries.length === 0 ? (
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
                <path d="M3 6h11v11H3zM14 9h3l4 4v4h-7z" />
                <circle cx="7" cy="19" r="2" />
                <circle cx="18" cy="19" r="2" />
              </svg>
            </div>
            <h3 className="mt-4 font-semibold text-slate-900">
              {search ? 'No matching deliveries' : 'No deliveries yet'}
            </h3>
            <p className="mt-2 text-sm text-slate-500">
              {search
                ? 'Try another delivery ID, shipment ID or status.'
                : 'Delivery records will appear here when available.'}
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
            <table className="w-full min-w-[650px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-6 py-4 font-semibold">Delivery ID</th>
                  <th className="px-6 py-4 font-semibold">Shipment ID</th>
                  <th className="px-6 py-4 font-semibold">Delivery date</th>
                  <th className="px-6 py-4 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredDeliveries.map((delivery, index) => (
                  <tr
                    key={delivery.delivery_id ?? index}
                    className="transition hover:bg-slate-50"
                  >
                    <td className="whitespace-nowrap px-6 py-4 font-semibold text-slate-900">
                      #{delivery.delivery_id ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-slate-600">
                      {delivery.shipment_id ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-slate-600">
                      {formatDate(
                        delivery.actual_delivery_date ??
                        delivery.delivery_date ??
                        delivery.scheduled_date
                      )}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4">
                      <StatusBadge
                        status={delivery.delivery_status ?? delivery.status}
                      />
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
    COMPLETED: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
    CANCELLED: 'bg-red-50 text-red-700 ring-red-600/20',
    PENDING: 'bg-amber-50 text-amber-700 ring-amber-600/20',
    SCHEDULED: 'bg-violet-50 text-violet-700 ring-violet-600/20',
    IN_PROGRESS: 'bg-cyan-50 text-cyan-700 ring-cyan-600/20',
    OUT_FOR_DELIVERY: 'bg-cyan-50 text-cyan-700 ring-cyan-600/20',
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

export default Deliveries
