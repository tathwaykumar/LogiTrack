import { useCallback, useEffect, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'
import { formatCurrency, formatDate, formatLabel, formatNumber, initials } from '../lib/format.js'
import { BarList, Meter } from './charts.jsx'
import ProductImage from './ProductImage.jsx'
import { Avatar, DataTable, EmptyState, IdTag, Notice, PageHeader, Panel, RefreshButton, StatTile, StatusBadge, stagger } from './ui.jsx'

const SHIPMENT_STAGES = ['CREATED', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED']
const ORDER_STAGES = ['PENDING', 'CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED']

function toStages(rows, order) {
  const counts = Object.fromEntries((rows ?? []).map((row) => [String(row.status).toUpperCase(), Number(row.count) || 0]))
  const extra = Object.keys(counts).filter((status) => !order.includes(status))
  return [...order, ...extra].map((status) => ({ key: status, label: formatLabel(status), value: counts[status] ?? 0, muted: status === 'CANCELLED' }))
}

async function optional(promise) {
  try {
    return await promise
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) throw error
    return null
  }
}

function Analytics({ session, onAuthExpired }) {
  const [summary, setSummary] = useState(null)
  const [shipmentStatuses, setShipmentStatuses] = useState([])
  const [extra, setExtra] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadAnalytics = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const token = session.accessToken
      const [summaryData, statusData] = await Promise.all([apiGet('/dashboard/summary', token), apiGet('/analytics/shipment-status', token)])
      if (!summaryData || typeof summaryData !== 'object' || !Array.isArray(statusData)) throw new Error('Unexpected response from the analytics API.')
      const [orderStatus, revenue, deliveryPerformance, topProducts, driverPerformance, stockValue, delayed] = await Promise.all([
        optional(apiGet('/analytics/order-status', token)),
        optional(apiGet('/analytics/revenue', token)),
        optional(apiGet('/analytics/delivery-performance', token)),
        optional(apiGet('/analytics/top-products', token)),
        optional(apiGet('/analytics/driver-performance', token)),
        optional(apiGet('/analytics/warehouse-stock-value', token)),
        optional(apiGet('/analytics/delayed-shipments', token)),
      ])
      setSummary(summaryData)
      setShipmentStatuses(statusData)
      setExtra({ orderStatus, revenue, deliveryPerformance, topProducts, driverPerformance, stockValue, delayed })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setError(err instanceof ApiError && err.status === 403 ? 'You do not have permission to view analytics.' : err.message || 'Unable to load analytics.')
    } finally {
      setLoading(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => { loadAnalytics() }, [loadAnalytics])

  const totalStatusCount = shipmentStatuses.reduce((sum, item) => sum + (Number(item.count) || 0), 0)
  const { orderStatus, revenue, deliveryPerformance, topProducts, driverPerformance, stockValue, delayed } = extra
  const ready = !loading && !error

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Operations insight"
        title="Analytics"
        accent="that move the needle."
        description="Shipment flow, revenue, delivery performance and inventory value — computed live from operational records."
        actions={<RefreshButton onClick={loadAnalytics} loading={loading} label="Refresh analytics" />}
      />

      {error && <Notice tone="error" onRetry={loadAnalytics}>{error}</Notice>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Total orders" value={formatNumber(summary?.total_orders)} hint={summary ? `${formatNumber(summary.total_customers)} customers` : undefined} icon="box" loading={loading} />
        <StatTile label="Total shipments" value={formatNumber(summary?.total_shipments)} icon="route" tone="cream" loading={loading} style={stagger(1)} />
        <StatTile label="Successful payments" value={formatNumber(summary?.successful_payments)} icon="card" tone="lime" loading={loading} style={stagger(2)} />
        <StatTile label="Pending deliveries" value={formatNumber(summary?.pending_deliveries)} icon="truck" tone="ink" loading={loading} style={stagger(3)} />
      </div>

      {ready && (
        <section className="on-dark animate-rise grid gap-8 overflow-hidden rounded-[1.8rem] bg-ink p-7 text-paper sm:p-9 lg:grid-cols-[1fr_1fr_1.2fr]">
          <div>
            <p className="eyebrow text-lime">Revenue collected</p>
            <p className="mt-3 text-5xl font-semibold tracking-[-0.05em]">{revenue ? formatCurrency(revenue.total_revenue) : '—'}</p>
            <p className="mt-2 text-sm text-paper/60">{revenue ? `${formatNumber(revenue.successful_payments)} successful payments` : 'Revenue data unavailable'}</p>
          </div>
          <div>
            <p className="eyebrow text-paper/50">Total invoiced</p>
            <p className="mt-3 text-5xl font-semibold tracking-[-0.05em]">{revenue ? formatCurrency(revenue.total_invoiced) : '—'}</p>
            <p className="mt-2 text-sm text-paper/60">Across all issued invoices</p>
          </div>
          <div className="flex flex-col justify-center">
            {deliveryPerformance ? (
              <Meter surface="dark" label="Delivery success rate" value={deliveryPerformance.success_rate} detail={`${deliveryPerformance.delivered} delivered · ${deliveryPerformance.pending} pending · ${deliveryPerformance.failed} failed of ${deliveryPerformance.total_deliveries}`} />
            ) : <p className="text-sm text-paper/60">Delivery performance unavailable.</p>}
          </div>
        </section>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel eyebrow="Logistics" title="Shipment status breakdown" subtitle={loading ? 'Loading shipment status data…' : `${totalStatusCount} shipment${totalStatusCount === 1 ? '' : 's'} across ${shipmentStatuses.length} status${shipmentStatuses.length === 1 ? '' : 'es'}`}>
          {loading ? <div className="space-y-3">{[1, 2, 3].map((item) => <div key={item} className="skeleton h-10" />)}</div>
            : error ? <EmptyState icon="chart" title="Shipment analytics could not be loaded" text="Resolve the error above and try again." />
              : shipmentStatuses.length === 0 ? <EmptyState icon="chart" title="No shipment analytics yet" text="The chart will appear when shipment records are available." />
                : <BarList items={toStages(shipmentStatuses, SHIPMENT_STAGES)} caption="Shipments by status" />}
        </Panel>
        <Panel eyebrow="Commerce" title="Orders by status" style={stagger(1)}>
          {loading ? <div className="space-y-3">{[1, 2, 3].map((item) => <div key={item} className="skeleton h-10" />)}</div>
            : orderStatus?.length ? <BarList items={toStages(orderStatus, ORDER_STAGES)} caption="Orders by status" />
              : <EmptyState icon="chart" title={orderStatus ? 'No orders yet' : 'Order analytics unavailable'} />}
        </Panel>
      </div>

      {ready && (
        <div className="grid gap-6 xl:grid-cols-2">
          <Panel eyebrow="Products" title="Top products by revenue" subtitle="Units ordered shown in each label">
            {topProducts?.length ? (
              <BarList
                caption="Top products by revenue"
                format={formatCurrency}
                items={topProducts.map((item) => ({
                  key: item.product_id,
                  label: `${item.product_name} · ${formatNumber(item.total_quantity)} units`,
                  value: item.total_revenue,
                  media: <ProductImage name={item.product_name} className="size-11 shrink-0 rounded-xl" />,
                }))}
              />
            ) : <EmptyState icon="shop" title={topProducts ? 'No product sales yet' : 'Product analytics unavailable'} />}
          </Panel>
          <Panel eyebrow="Inventory" title="Stock value by warehouse" subtitle="Quantity × unit price">
            {stockValue?.length ? (
              <BarList caption="Stock value by warehouse" format={formatCurrency} items={stockValue.map((item) => ({ key: item.warehouse, label: item.warehouse, value: item.stock_value }))} />
            ) : <EmptyState icon="warehouse" title={stockValue ? 'No stock recorded' : 'Inventory value unavailable'} />}
          </Panel>
        </div>
      )}

      {ready && (
        <div className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
          <Panel eyebrow="People" title="Driver performance" bodyClassName="p-0">
            {driverPerformance?.length ? (
              <DataTable head={['Driver', 'Deliveries', 'Completed', 'Completion']} minWidth={560} caption="Driver performance">
                {driverPerformance.map((driver) => {
                  const rate = driver.total_deliveries ? (Number(driver.completed_deliveries) / Number(driver.total_deliveries)) * 100 : 0
                  return (
                    <tr key={driver.driver_id}>
                      <td><div className="flex items-center gap-3"><Avatar text={initials(driver.driver_name)} className="size-9 text-xs" /><span className="font-semibold text-ink">{driver.driver_name}</span></div></td>
                      <td className="tabular-nums">{driver.total_deliveries}</td>
                      <td className="tabular-nums">{driver.completed_deliveries}</td>
                      <td className="w-48"><div className="flex items-center gap-3"><div className="h-2 flex-1 overflow-hidden rounded-full bg-cream"><div className="h-full rounded-full bg-ink" style={{ width: `${rate}%` }} /></div><span className="w-10 text-right text-xs font-semibold tabular-nums">{Math.round(rate)}%</span></div></td>
                    </tr>
                  )
                })}
              </DataTable>
            ) : <EmptyState icon="users" title={driverPerformance ? 'No driver deliveries yet' : 'Driver performance unavailable'} />}
          </Panel>
          <Panel eyebrow="Exceptions" title="Delayed shipments" subtitle="Past their estimated delivery" bodyClassName="p-0">
            {delayed?.length ? (
              <ul className="divide-y divide-line">
                {delayed.slice(0, 6).map((item) => (
                  <li key={item.shipment_id} className="flex items-center justify-between gap-3 px-5 py-3.5 sm:px-6">
                    <div>
                      <p className="text-sm"><IdTag>{item.shipment_id}</IdTag> <span className="text-stone">· Order #{item.order_id}</span></p>
                      <p className="text-xs text-stone">Estimated {formatDate(item.estimated_delivery)}</p>
                    </div>
                    <StatusBadge status={item.status} />
                  </li>
                ))}
              </ul>
            ) : <EmptyState icon="clock" title={delayed ? 'Nothing delayed' : 'Delay data unavailable'} text={delayed ? 'Every open shipment is within its estimate.' : undefined} />}
          </Panel>
        </div>
      )}
    </div>
  )
}

export default Analytics
