import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'
import { formatCurrency, formatDate, formatLabel } from '../lib/format.js'
import { Meter } from './charts.jsx'
import { DataTable, EmptyState, ErrorState, IdTag, Notice, PageHeader, Panel, RefreshButton, SearchField, SkeletonRows, StatTile, StatusBadge, stagger } from './ui.jsx'

function getInvoiceStatus(invoice) {
  return String(invoice.invoice_status ?? invoice.status ?? invoice.payment_status ?? 'Unknown')
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
      [invoice.invoice_id, invoice.order_id, invoice.customer_id, invoice.invoice_number, invoice.invoice_status, invoice.status]
        .some((value) => String(value ?? '').toLowerCase().includes(query))
    )
  }, [invoices, search])

  const totalAmount = invoices.reduce((sum, invoice) => sum + Number(invoice.total_amount ?? invoice.amount ?? invoice.invoice_amount ?? 0), 0)

  const paidCount = invoices.filter((invoice) => {
    const status = getInvoiceStatus(invoice).toLowerCase()
    return status.includes('paid') || status.includes('complete')
  }).length

  const pendingCount = invoices.filter((invoice) => {
    const status = getInvoiceStatus(invoice).toLowerCase()
    return status.includes('issued') || status.includes('pending') || status.includes('unpaid') || status.includes('due')
  }).length

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Finance management"
        title="Invoices,"
        accent="on the ledger."
        description="Review invoice records, amounts, and payment status."
        actions={<RefreshButton onClick={() => loadInvoices(true)} loading={loading || refreshing} label="Refresh invoices" />}
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1.4fr]">
        <StatTile label="Total invoices" value={loading ? '—' : invoices.length} hint="Invoices available to you" icon="file" loading={loading} />
        <StatTile label="Total amount" value={loading ? '—' : formatCurrency(totalAmount)} hint="Combined invoice amount" icon="wallet" tone="ink" loading={loading} style={stagger(1)} />
        <Panel eyebrow="Collection" title={loading ? 'Loading…' : `${paidCount} paid · ${pendingCount} awaiting payment`} style={stagger(2)}>
          <Meter label="Invoices paid" value={invoices.length ? (paidCount / invoices.length) * 100 : 0} detail="Share of invoices marked paid or completed" />
        </Panel>
      </div>

      {error && <Notice tone="error" onRetry={() => loadInvoices()}>{error}</Notice>}

      <Panel
        bodyClassName="p-0"
        title="Invoice records"
        subtitle={loading ? 'Loading invoice records…' : `${filteredInvoices.length} record${filteredInvoices.length === 1 ? '' : 's'} found`}
        actions={<SearchField value={search} onChange={setSearch} placeholder="Search invoices…" label="Search invoices" className="w-full sm:w-72" />}
      >
        {loading ? <SkeletonRows rows={4} label="Loading invoices" />
          : error ? <ErrorState title="Invoice records could not be loaded" message="Resolve the error above and try again." />
            : filteredInvoices.length === 0 ? <EmptyState icon="file" title={search ? 'No matching invoices' : 'No invoices yet'} text={search ? 'Try another invoice number, order ID, or status.' : 'Invoices will appear here when records are available for your account.'} />
              : (
                <DataTable head={['Invoice', 'Order', 'Issued', 'Subtotal', 'Tax', 'Total', 'Status']} minWidth={820} caption="Invoices">
                  {filteredInvoices.map((invoice, index) => (
                    <tr key={invoice.invoice_id ?? invoice.invoice_number ?? index}>
                      <td><IdTag prefix="INV-">{invoice.invoice_number ?? invoice.invoice_id}</IdTag></td>
                      <td>#{invoice.order_id ?? '—'}</td>
                      <td>{formatDate(invoice.invoice_date ?? invoice.issue_date ?? invoice.created_at)}</td>
                      <td className="tabular-nums">{formatCurrency(invoice.subtotal)}</td>
                      <td className="tabular-nums">{formatCurrency(invoice.tax)}</td>
                      <td className="font-semibold text-ink tabular-nums">{formatCurrency(invoice.total_amount ?? invoice.amount ?? invoice.invoice_amount)}</td>
                      <td><StatusBadge status={getInvoiceStatus(invoice).toUpperCase()} label={formatLabel(getInvoiceStatus(invoice))} /></td>
                    </tr>
                  ))}
                </DataTable>
              )}
      </Panel>
    </div>
  )
}

export default Invoices
