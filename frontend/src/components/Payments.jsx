import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet, apiPost } from '../services/apiClient.js'
import { formatCurrency, formatDate, formatLabel } from '../lib/format.js'
import { DataTable, EmptyState, ErrorState, Icon, IdTag, Notice, PageHeader, Panel, RefreshButton, SearchField, SkeletonRows, StatTile, StatusBadge, stagger } from './ui.jsx'

function Payments({ session, onAuthExpired }) {
  const [payments, setPayments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  const [paymentOrders, setPaymentOrders] = useState([])
  const [simulatingOrderId, setSimulatingOrderId] = useState(null)
  const [simulationReceipt, setSimulationReceipt] = useState(null)
  const isCustomer = Number(session.user.roleId) === 4

  const loadPayments = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const [data, pendingOrders] = await Promise.all([
        apiGet('/payments', session.accessToken),
        isCustomer ? apiGet('/shop/payment-orders', session.accessToken) : Promise.resolve([]),
      ])

      if (!Array.isArray(data)) {
        throw new Error('Unexpected response from the payments API.')
      }

      setPayments(data)
      setPaymentOrders(Array.isArray(pendingOrders) ? pendingOrders : [])
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }

      setError(err.message || 'Unable to load payments.')
    } finally {
      setLoading(false)
    }
  }, [session.accessToken, onAuthExpired, isCustomer])

  useEffect(() => {
    loadPayments()
  }, [loadPayments, refreshKey])

  const filteredPayments = useMemo(() => {
    const query = search.trim().toLowerCase()

    if (!query) return payments

    return payments.filter((payment) =>
      String(payment.payment_id ?? '').toLowerCase().includes(query) ||
      String(payment.order_id ?? '').toLowerCase().includes(query) ||
      String(payment.payment_status ?? payment.status ?? '').toLowerCase().includes(query) ||
      String(payment.payment_method ?? '').toLowerCase().includes(query)
    )
  }, [payments, search])

  const completedCount = payments.filter((payment) =>
    ['COMPLETED', 'SUCCESS', 'PAID'].includes(String(payment.payment_status ?? payment.status ?? '').toUpperCase())
  ).length

  const pendingCount = payments.filter((payment) =>
    ['PENDING', 'PROCESSING'].includes(String(payment.payment_status ?? payment.status ?? '').toUpperCase())
  ).length

  const totalAmount = payments.reduce((sum, payment) => {
    const amount = Number(payment.amount ?? payment.payment_amount ?? 0)
    return sum + (Number.isFinite(amount) ? amount : 0)
  }, 0)

  async function simulatePayment(orderId, outcome) {
    setError('')
    setSimulationReceipt(null)
    setSimulatingOrderId(orderId)
    try {
      const data = await apiPost('/shop/payments/simulate', { order_id: orderId, outcome }, session.accessToken)
      setSimulationReceipt(data)
      setRefreshKey((key) => key + 1)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setError(err.message || 'Unable to simulate payment.')
    } finally {
      setSimulatingOrderId(null)
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Financial management"
        title="Payments,"
        accent="reconciled."
        description="Review payment records and transaction statuses."
        actions={<RefreshButton onClick={() => setRefreshKey((key) => key + 1)} loading={loading} label="Refresh payments" />}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Total payments" value={payments.length} icon="card" loading={loading && !payments.length} />
        <StatTile label="Completed" value={completedCount} icon="check" tone="lime" loading={loading && !payments.length} style={stagger(1)} />
        <StatTile label="Pending" value={pendingCount} icon="clock" tone="cream" loading={loading && !payments.length} style={stagger(2)} />
        <StatTile label="Recorded amount" value={formatCurrency(totalAmount)} icon="wallet" tone="ink" loading={loading && !payments.length} style={stagger(3)} />
      </div>

      {error && <Notice tone="error">{error}</Notice>}

      {isCustomer && (
        <section aria-labelledby="simulator-heading" className="animate-rise overflow-hidden rounded-[1.6rem] border-2 border-ink bg-paper">
          <div className="hazard h-3" aria-hidden="true" />
          <div className="flex flex-col gap-4 border-b border-line p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6">
            <div>
              <p className="eyebrow inline-flex items-center gap-2 rounded-full bg-ink px-3 py-1.5 text-lime">
                <Icon name="alert" className="size-3.5" /> Development only · no real payment
              </p>
              <h2 id="simulator-heading" className="font-display mt-3 text-3xl font-semibold">Payment simulator</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-stone">This does not collect money or contact a payment provider. The backend records the selected test result and calculates the order amount itself.</p>
            </div>
          </div>

          <div className="space-y-3 p-5 sm:p-6">
            {simulationReceipt && (
              <div role="status" className="on-dark animate-rise rounded-2xl bg-ink p-5 text-paper">
                <p className="eyebrow text-lime">Simulated payment receipt · development only</p>
                <p className="mt-2 font-semibold">Order #{simulationReceipt.order_id} — {formatLabel(simulationReceipt.payment_status)}. Invoice #{simulationReceipt.invoice_id} is {formatLabel(simulationReceipt.invoice_status)} for {formatCurrency(simulationReceipt.total_amount)}.</p>
                {simulationReceipt.fulfilment && <p className="mt-2 text-sm text-paper/70">{simulationReceipt.fulfilment.shipment_id ? `Shipment #${simulationReceipt.fulfilment.shipment_id}: ` : ''}{simulationReceipt.fulfilment.message}</p>}
              </div>
            )}

            {loading && paymentOrders.length === 0 ? (
              <div className="skeleton h-24" />
            ) : paymentOrders.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-sand px-4 py-6 text-center text-sm text-stone">No pending customer orders are ready for simulated payment.</p>
            ) : (
              <ul className="space-y-3">
                {paymentOrders.map((order) => (
                  <li key={order.order_id} className="flex flex-col gap-4 rounded-2xl border border-line bg-ivory/60 p-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-4">
                      <span className="grid size-12 place-items-center rounded-2xl bg-cream"><Icon name="file" className="size-5" /></span>
                      <div>
                        <p className="font-semibold">Order #{order.order_id} <span className="font-normal text-stone">· Invoice #{order.invoice_id}</span></p>
                        <p className="mt-0.5 text-sm text-stone">{formatCurrency(order.total_amount)} · Current payment: {formatLabel(order.payment_status || 'NOT STARTED')}</p>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button type="button" onClick={() => simulatePayment(order.order_id, 'SUCCESS')} disabled={simulatingOrderId !== null} className="btn btn-ink">
                        <Icon name="check" className="size-4" />{simulatingOrderId === order.order_id ? 'Processing…' : 'Simulate successful payment'}
                      </button>
                      <button type="button" onClick={() => simulatePayment(order.order_id, 'FAILED')} disabled={simulatingOrderId !== null} className="btn btn-danger">
                        <Icon name="x" className="size-4" />Simulate failed payment
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}

      <Panel
        bodyClassName="p-0"
        title="Payment records"
        subtitle={`${filteredPayments.length} of ${payments.length} payments`}
        actions={<SearchField value={search} onChange={setSearch} placeholder="Payment, order or status…" label="Search payments" className="w-full sm:w-72" />}
      >
        {loading && payments.length === 0 ? (
          <SkeletonRows rows={3} label="Loading payments" />
        ) : error && payments.length === 0 ? (
          <ErrorState title="Unable to load payments" message={error} onRetry={() => setRefreshKey((key) => key + 1)} />
        ) : filteredPayments.length === 0 ? (
          <EmptyState
            icon="card"
            title={search ? 'No matching payments' : 'No payments yet'}
            text={search ? 'Try another payment ID, order ID or status.' : 'Payment records will appear here when available.'}
            action={search && <button type="button" onClick={() => setSearch('')} className="btn btn-ink">Clear search</button>}
          />
        ) : (
          <DataTable head={['Payment', 'Order', 'Amount', 'Method', 'Status', 'Date']} minWidth={760} caption="Payments">
            {filteredPayments.map((payment, index) => (
              <tr key={payment.payment_id ?? index}>
                <td><IdTag>{payment.payment_id}</IdTag></td>
                <td>#{payment.order_id ?? '—'}</td>
                <td className="font-semibold text-ink tabular-nums">{formatCurrency(payment.amount ?? payment.payment_amount)}</td>
                <td>{formatLabel(payment.payment_method)}</td>
                <td><StatusBadge status={payment.payment_status ?? payment.status} /></td>
                <td>{formatDate(payment.payment_date ?? payment.transaction_date)}</td>
              </tr>
            ))}
          </DataTable>
        )}
      </Panel>
    </div>
  )
}

export default Payments
