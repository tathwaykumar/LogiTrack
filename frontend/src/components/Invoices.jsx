import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'

function formatCurrency(value) {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '—'

  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(amount)
}

function formatDate(value) {
  if (!value) return '—'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)

  return date.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function getInvoiceStatus(invoice) {
  return String(
    invoice.invoice_status ??
      invoice.status ??
      invoice.payment_status ??
      'Unknown'
  )
}

function StatusBadge({ status }) {
  const normalized = status.toLowerCase()

  const style =
    normalized.includes('paid') || normalized.includes('complete')
      ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/20'
      : normalized.includes('issued') ||
          normalized.includes('pending') ||
          normalized.includes('unpaid') ||
          normalized.includes('due')
        ? 'bg-amber-50 text-amber-700 ring-amber-600/20'
        : normalized.includes('cancel')
          ? 'bg-rose-50 text-rose-700 ring-rose-600/20'
          : 'bg-slate-100 text-slate-700 ring-slate-500/20'

  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${style}`}
    >
      {status}
    </span>
  )
}

function SummaryCard({ label, value, detail }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-3 break-words text-2xl font-bold tracking-tight text-slate-950">
        {value}
      </p>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>
    </div>
  )
}

function Invoices({ session, onAuthExpired }) {
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  const loadInvoices = useCallback(
    async (isRefresh = false) => {
      if (isRefresh) {
        setRefreshing(true)
      } else {
        setLoading(true)
      }

      setError('')

      try {
        const data = await apiGet('/invoices', session.accessToken)

        const records = Array.isArray(data)
          ? data
          : data?.invoices ?? data?.items ?? data?.results ?? []

        setInvoices(Array.isArray(records) ? records : [])
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          onAuthExpired()
          return
        }

        if (err instanceof ApiError && err.status === 403) {
          setError('You do not have permission to view these invoices.')
        } else {
          setError(err.message || 'Unable to load invoices.')
        }
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [session.accessToken, onAuthExpired]
  )

  useEffect(() => {
    loadInvoices()
  }, [loadInvoices])

  const filteredInvoices = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return invoices

    return invoices.filter((invoice) =>
      [
        invoice.invoice_id,
        invoice.order_id,
        invoice.customer_id,
        invoice.invoice_number,
        invoice.invoice_status,
        invoice.status,
      ].some((value) =>
        String(value ?? '').toLowerCase().includes(query)
      )
    )
  }, [invoices, search])

  const totalAmount = invoices.reduce(
    (sum, invoice) =>
      sum +
      Number(
        invoice.total_amount ??
          invoice.amount ??
          invoice.invoice_amount ??
          0
      ),
    0
  )

  const paidCount = invoices.filter((invoice) => {
    const status = getInvoiceStatus(invoice).toLowerCase()
    return status.includes('paid') || status.includes('complete')
  }).length

  const pendingCount = invoices.filter((invoice) => {
    const status = getInvoiceStatus(invoice).toLowerCase()
    return (
      status.includes('issued') ||
      status.includes('pending') ||
      status.includes('unpaid') ||
      status.includes('due')
    )
  }).length

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-medium text-cyan-700">
            Finance management
          </p>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-950">
            Invoices
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            Review invoice records, amounts, and payment status.
          </p>
        </div>

        <button
          type="button"
          onClick={() => loadInvoices(true)}
          disabled={loading || refreshing}
          className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {refreshing ? 'Refreshing...' : 'Refresh invoices'}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          label="Total invoices"
          value={loading ? '—' : invoices.length}
          detail="Invoices available to you"
        />
        <SummaryCard
          label="Total amount"
          value={loading ? '—' : formatCurrency(totalAmount)}
          detail="Combined invoice amount"
        />
        <SummaryCard
          label="Paid invoices"
          value={loading ? '—' : paidCount}
          detail="Paid or completed"
        />
        <SummaryCard
          label="Pending invoices"
          value={loading ? '—' : pendingCount}
          detail="Awaiting payment"
        />
      </div>

      {error && (
        <div
          role="alert"
          className="flex flex-col gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <p className="text-sm text-rose-700">{error}</p>
          <button
            type="button"
            onClick={() => loadInvoices()}
            className="shrink-0 rounded-lg border border-rose-200 bg-white px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-100"
          >
            Try again
          </button>
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="font-semibold text-slate-900">
              Invoice records
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              {loading
                ? 'Loading invoice records...'
                : `${filteredInvoices.length} record${filteredInvoices.length === 1 ? '' : 's'} found`}
            </p>
          </div>

          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search invoices..."
            aria-label="Search invoices"
            className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100 sm:max-w-xs"
          />
        </div>

        {loading ? (
          <div className="space-y-3 p-5">
            {[1, 2, 3, 4].map((item) => (
              <div
                key={item}
                className="h-12 animate-pulse rounded-lg bg-slate-100"
              />
            ))}
          </div>
        ) : error ? (
          <div className="p-10 text-center">
            <p className="font-medium text-slate-700">
              Invoice records could not be loaded.
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Resolve the error above and try again.
            </p>
          </div>
        ) : filteredInvoices.length === 0 ? (
          <div className="px-5 py-14 text-center">
            <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-cyan-50 text-cyan-700">
              <svg
                aria-hidden="true"
                className="size-6"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6"
                />
              </svg>
            </div>
            <h3 className="mt-4 font-semibold text-slate-900">
              {search ? 'No matching invoices' : 'No invoices yet'}
            </h3>
            <p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">
              {search
                ? 'Try another invoice number, order ID, or status.'
                : 'Invoices will appear here when records are available for your account.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-semibold">Invoice ID</th>
                  <th className="px-5 py-3 font-semibold">Order ID</th>
                  <th className="px-5 py-3 font-semibold">Invoice date</th>
                  <th className="px-5 py-3 font-semibold">Amount</th>
                  <th className="px-5 py-3 font-semibold">Tax</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-100">
                {filteredInvoices.map((invoice, index) => (
                  <tr
                    key={invoice.invoice_id ?? invoice.invoice_number ?? index}
                    className="transition hover:bg-slate-50"
                  >
                    <td className="whitespace-nowrap px-5 py-4 font-semibold text-slate-900">
                      {invoice.invoice_number ?? invoice.invoice_id ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                      {invoice.order_id ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                      {formatDate(
                        invoice.invoice_date ??
                          invoice.issue_date ??
                          invoice.created_at
                      )}
                    </td>
                    <td className="whitespace-nowrap px-5 py-4 font-medium text-slate-900">
                      {formatCurrency(
                        invoice.total_amount ??
                          invoice.amount ??
                          invoice.invoice_amount
                      )}
                    </td>
                    <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                      {formatCurrency(invoice.tax)}
                    </td>
                    <td className="whitespace-nowrap px-5 py-4">
                      <StatusBadge status={getInvoiceStatus(invoice)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default Invoices
