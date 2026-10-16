
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'

function Payments({ session, onAuthExpired }) {
  const [payments, setPayments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const loadPayments = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const data = await apiGet('/payments', session.accessToken)

      if (!Array.isArray(data)) {
        throw new Error('Unexpected response from the payments API.')
      }

      setPayments(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }

      setError(err.message || 'Unable to load payments.')
    } finally {
      setLoading(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => {
    loadPayments()
  }, [loadPayments, refreshKey])

  const filteredPayments = useMemo(() => {
    const query = search.trim().toLowerCase()

    if (!query) return payments

    return payments.filter((payment) =>
      String(payment.payment_id ?? '').toLowerCase().includes(query) ||
      String(payment.order_id ?? '').toLowerCase().includes(query) ||
      String(payment.payment_status ?? payment.status ?? '')
        .toLowerCase().includes(query) ||
      String(payment.payment_method ?? '').toLowerCase().includes(query)
    )
  }, [payments, search])

  const completedCount = payments.filter((payment) =>
    ['COMPLETED', 'SUCCESS', 'PAID'].includes(
      String(payment.payment_status ?? payment.status ?? '').toUpperCase()
    )
  ).length

  const pendingCount = payments.filter((payment) =>
    ['PENDING', 'PROCESSING'].includes(
      String(payment.payment_status ?? payment.status ?? '').toUpperCase()
    )
  ).length

  const totalAmount = payments.reduce((sum, payment) => {
    const amount = Number(payment.amount ?? payment.payment_amount ?? 0)
    return sum + (Number.isFinite(amount) ? amount : 0)
  }, 0)

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.16em] text-cyan-700">
            Financial management
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
            Payments
          </h2>
          <p className="mt-2 text-slate-600">
            Review payment records and transaction statuses.
          </p>
        </div>

        <button
          onClick={() => setRefreshKey((key) => key + 1)}
          disabled={loading}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? 'Refreshing...' : 'Refresh payments'}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard label="Total payments" value={payments.length} />
        <SummaryCard label="Completed" value={completedCount} />
        <SummaryCard label="Pending" value={pendingCount} />
        <SummaryCard
          label="Recorded amount"
          value={formatAmount(totalAmount)}
        />
      </div>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-4 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <div>
            <h3 className="font-semibold text-slate-950">
              Payment records
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              {filteredPayments.length} of {payments.length} payments
            </p>
          </div>

          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search payment, order or status..."
            aria-label="Search payments"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100 sm:max-w-sm"
          />
        </div>

        {loading ? (
          <div className="space-y-3 p-6" aria-label="Loading payments">
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
              Unable to load payments
            </p>
            <p className="mt-2 text-sm text-slate-600">{error}</p>
            <button
              onClick={() => setRefreshKey((key) => key + 1)}
              className="mt-4 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
            >
              Try again
            </button>
          </div>
        ) : filteredPayments.length === 0 ? (
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
                <rect x="3" y="5" width="18" height="14" rx="2" />
                <path d="M3 10h18M7 15h3" />
              </svg>
            </div>
            <h3 className="mt-4 font-semibold text-slate-900">
              {search ? 'No matching payments' : 'No payments yet'}
            </h3>
            <p className="mt-2 text-sm text-slate-500">
              {search
                ? 'Try another payment ID, order ID or status.'
                : 'Payment records will appear here when available.'}
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
            <table className="w-full min-w-[700px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-6 py-4 font-semibold">Payment ID</th>
                  <th className="px-6 py-4 font-semibold">Order ID</th>
                  <th className="px-6 py-4 font-semibold">Amount</th>
                  <th className="px-6 py-4 font-semibold">Method</th>
                  <th className="px-6 py-4 font-semibold">Status</th>
                  <th className="px-6 py-4 font-semibold">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredPayments.map((payment, index) => (
                  <tr
                    key={payment.payment_id ?? index}
                    className="transition hover:bg-slate-50"
                  >
                    <td className="whitespace-nowrap px-6 py-4 font-semibold text-slate-900">
                      #{payment.payment_id ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-slate-600">
                      {payment.order_id ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 font-medium text-slate-800">
                      {formatAmount(payment.amount ?? payment.payment_amount)}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-slate-600">
                      {formatLabel(payment.payment_method)}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4">
                      <StatusBadge
                        status={payment.payment_status ?? payment.status}
                      />
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-slate-600">
                      {formatDate(
                        payment.payment_date ?? payment.transaction_date
                      )}
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
      <p className="mt-2 truncate text-2xl font-semibold tracking-tight text-slate-950">
        {value}
      </p>
    </article>
  )
}

function StatusBadge({ status }) {
  const value = String(status ?? 'UNKNOWN')
  const normalized = value.toUpperCase()

  const styles = {
    COMPLETED: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
    SUCCESS: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
    PAID: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
    FAILED: 'bg-red-50 text-red-700 ring-red-600/20',
    CANCELLED: 'bg-red-50 text-red-700 ring-red-600/20',
    PENDING: 'bg-amber-50 text-amber-700 ring-amber-600/20',
    PROCESSING: 'bg-cyan-50 text-cyan-700 ring-cyan-600/20',
  }

  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${
        styles[normalized] ?? 'bg-slate-100 text-slate-700 ring-slate-500/20'
      }`}
    >
      {formatLabel(value)}
    </span>
  )
}

function formatLabel(value) {
  if (!value) return '—'

  return String(value)
    .replaceAll('_', ' ')
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatAmount(value) {
  if (value === null || value === undefined || value === '') {
    return '—'
  }

  const amount = Number(value)

  return Number.isFinite(amount)
    ? new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 2,
      }).format(amount)
    : String(value)
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

export default Payments
