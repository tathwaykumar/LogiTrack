import { useEffect, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'
import { daysUntil, formatCurrency, formatLabel, formatNumber, formatShortDate } from '../lib/format.js'
import { isOpenDelivery, summariseDeliveries } from '../lib/status.js'
import { BarList, Meter, StageStrip } from './charts.jsx'
import ProductImage from './ProductImage.jsx'
import { EmptyState, ErrorState, Icon, Panel, StatTile, StatusBadge, stagger } from './ui.jsx'

const SHIPMENT_STAGES = ['CREATED', 'PICKED_UP', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED']
const ORDER_STAGES = ['PENDING', 'CONFIRMED', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED']
const CLOSED = ['DELIVERED', 'CANCELLED']

function Dashboard({ session, onAuthExpired, onNavigate }) {
  const roleId = Number(session.user.roleId)
  const [state, setState] = useState({ loading: true, error: '', data: null })
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let active = true
    async function loadDashboard() {
      setState({ loading: true, error: '', data: null })
      try {
        const data = await getDashboardData(roleId, session.accessToken)
        if (active) setState({ loading: false, error: '', data })
      } catch (error) {
        if (!active) return
        if (error instanceof ApiError && error.status === 401) {
          onAuthExpired()
          return
        }
        setState({ loading: false, error: error.message || 'Unable to load dashboard data.', data: null })
      }
    }
    loadDashboard()
    return () => { active = false }
  }, [roleId, session.accessToken, onAuthExpired, refreshKey])

  if (state.loading) return <DashboardLoading />
  if (state.error) return <div className="panel mx-auto max-w-xl"><ErrorState title="Dashboard unavailable" message={state.error} onRetry={() => setRefreshKey((key) => key + 1)} /></div>
  if (!state.data) return null

  const name = session.user.username
  if (state.data.kind === 'operations') return <OperationsDashboard data={state.data} name={name} roleId={roleId} onNavigate={onNavigate} />
  if (state.data.kind === 'driver') return <DriverDashboard data={state.data} name={name} onNavigate={onNavigate} />
  return <CustomerDashboard data={state.data} name={name} onNavigate={onNavigate} />
}

async function optional(promise) {
  try {
    return await promise
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) throw error
    return null
  }
}

async function getDashboardData(roleId, token) {
  if (roleId === 1 || roleId === 2) {
    const [summary, shipments, deliveries, shipmentStatus] = await Promise.all([apiGet('/dashboard/summary', token), apiGet('/shipments', token), apiGet('/deliveries', token), apiGet('/analytics/shipment-status', token)])
    const [orderStatus, revenue, deliveryPerformance, topProducts, lowStock] = await Promise.all([
      optional(apiGet('/analytics/order-status', token)),
      optional(apiGet('/analytics/revenue', token)),
      optional(apiGet('/analytics/delivery-performance', token)),
      optional(apiGet('/analytics/top-products', token)),
      optional(apiGet('/analytics/low-stock', token)),
    ])
    return {
      kind: 'operations',
      summary,
      inMotion: shipments.filter((item) => !CLOSED.includes(item.shipment_status)).length,
      shipmentStages: toStages(shipmentStatus, SHIPMENT_STAGES),
      orderStages: Array.isArray(orderStatus) ? toStages(orderStatus, ORDER_STAGES) : null,
      revenue,
      deliveryPerformance,
      topProducts: Array.isArray(topProducts) ? topProducts.slice(0, 5) : null,
      lowStock: Array.isArray(lowStock) ? lowStock : null,
      activities: shipmentActivities(shipments, deliveries),
    }
  }
  if (roleId === 3) {
    const [deliveries, driverProfiles] = await Promise.all([apiGet('/deliveries', token), apiGet('/drivers/me', token)])
    const assignments = await optional(apiGet('/assignments', token))
    const today = new Date().toLocaleDateString('en-CA') // local YYYY-MM-DD, comparable with API dates
    const currentAssignments = Array.isArray(assignments)
      ? [...new Set(assignments.filter((item) => item.assigned_from <= today && (!item.assigned_to || item.assigned_to >= today)).map((item) => item.vehicle_id))]
      : null
    const counts = summariseDeliveries(deliveries)
    return {
      kind: 'driver',
      deliveries,
      profile: driverProfiles[0] ?? null,
      assignments: currentAssignments,
      completed: counts.delivered,
      active: counts.open,
    }
  }
  const [orders, shipments, deliveries, payments, invoices] = await Promise.all([apiGet('/orders', token), apiGet('/shipments', token), apiGet('/deliveries', token), apiGet('/payments', token), apiGet('/invoices', token)])
  return {
    kind: 'customer',
    orders,
    openShipments: shipments.filter((item) => !CLOSED.includes(item.shipment_status)).length,
    delivered: shipments.filter((item) => item.shipment_status === 'DELIVERED').length,
    deliveries: deliveries.length,
    payments: payments.length,
    invoices: invoices.length,
    dueInvoices: invoices.filter((item) => item.invoice_status !== 'PAID' && item.invoice_status !== 'CANCELLED'),
    activities: shipmentActivities(shipments, deliveries, orders),
  }
}

function toStages(rows, order) {
  const counts = Object.fromEntries((rows ?? []).map((row) => [String(row.status).toUpperCase(), Number(row.count) || 0]))
  const extra = Object.keys(counts).filter((status) => !order.includes(status))
  return [...order, ...extra].map((status) => ({ key: status, label: formatLabel(status), value: counts[status] ?? 0, muted: status === 'CANCELLED' }))
}

function shipmentActivities(shipments, deliveries, orders = []) {
  return [
    ...shipments.map((item) => ({ kind: 'route', title: `Shipment #${item.shipment_id}`, status: item.shipment_status, date: item.estimated_delivery || item.shipment_date })),
    ...deliveries.map((item) => ({ kind: 'truck', title: `Delivery #${item.delivery_id}`, status: item.delivery_status, date: item.delivery_date })),
    ...orders.map((item) => ({ kind: 'box', title: `Order #${item.order_id}`, status: item.order_status, date: item.order_date })),
  ].sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0)).slice(0, 6)
}

function greeting() {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
}

function Greeting({ name, eyebrow, children }) {
  return (
    <div>
      <p className="eyebrow text-stone">{eyebrow} · {new Intl.DateTimeFormat('en-IN', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date())}</p>
      <h1 className="font-display mt-4 text-[2.8rem] leading-[0.92] font-semibold sm:text-6xl xl:text-7xl">
        {greeting()},<br />
        <span className="font-serif-accent font-normal text-graphite">{name}</span>
        <span className="text-lime-deep">.</span>
      </h1>
      {children}
    </div>
  )
}

function OperationsDashboard({ data, name, roleId, onNavigate }) {
  const { summary, revenue, deliveryPerformance } = data
  return (
    <div className="space-y-6">
      <section className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
        <div className="panel animate-rise flex flex-col justify-between gap-10 p-7 sm:p-9">
          <Greeting name={name} eyebrow={roleId === 1 ? 'System overview' : 'Operations overview'}>
            <p className="mt-5 max-w-lg text-base leading-7 text-stone">Here is where every shipment stands right now, straight from the network.</p>
          </Greeting>
          <div>
            <div className="mb-3 flex items-baseline justify-between">
              <p className="eyebrow text-stone">Shipment pipeline</p>
              <p className="text-xs text-stone">{formatNumber(summary.total_shipments)} shipments</p>
            </div>
            <StageStrip items={data.shipmentStages} />
          </div>
        </div>

        <div className="on-dark animate-rise relative flex flex-col justify-between gap-8 overflow-hidden rounded-[1.5rem] bg-ink p-7 text-paper sm:p-9" style={stagger(1)}>
          <span className="absolute -top-24 -right-24 size-72 rounded-full border-[28px] border-lime/10" aria-hidden="true" />
          <div className="relative">
            <p className="eyebrow text-lime">In motion right now</p>
            <p className="mt-4 text-[6.5rem] leading-[0.8] font-semibold tracking-[-0.06em] sm:text-[8rem]">{data.inMotion}</p>
            <p className="mt-4 max-w-xs text-paper/70">shipment{data.inMotion === 1 ? '' : 's'} between a warehouse and a doorstep.</p>
          </div>
          <div className="relative space-y-5">
            {deliveryPerformance ? (
              <Meter surface="dark" label="Delivery success rate" value={deliveryPerformance.success_rate} detail={`${deliveryPerformance.delivered} of ${deliveryPerformance.total_deliveries} deliveries completed · ${deliveryPerformance.failed} failed`} />
            ) : (
              <p className="text-sm text-paper/60">Delivery performance is unavailable right now.</p>
            )}
            {onNavigate && <button type="button" onClick={() => onNavigate('tracking')} className="btn btn-lime">Open tracking <Icon name="arrowUpRight" className="size-4" /></button>}
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Total orders" value={formatNumber(summary.total_orders)} hint={`${formatNumber(summary.total_customers)} customers`} icon="box" style={stagger(2)} />
        <StatTile label="Pending deliveries" value={formatNumber(summary.pending_deliveries)} hint="Awaiting completion" icon="truck" tone="cream" style={stagger(3)} />
        <StatTile label="Successful payments" value={formatNumber(summary.successful_payments)} hint={`${formatNumber(summary.total_products)} products in catalog`} icon="card" tone="lime" style={stagger(4)} />
        <StatTile label="Revenue collected" value={revenue ? formatCurrency(revenue.total_revenue) : '—'} hint={revenue ? `${formatCurrency(revenue.total_invoiced)} invoiced` : 'Revenue data unavailable'} icon="wallet" tone="ink" style={stagger(5)} />
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <Panel eyebrow="Logistics" title="Shipments by stage" subtitle="Ordered from creation to delivery" style={stagger(2)}>
          <BarList items={data.shipmentStages} caption="Shipments by stage" />
        </Panel>
        <Panel eyebrow="Commerce" title="Orders by status" subtitle="Every order in the system" style={stagger(3)}>
          {data.orderStages ? <BarList items={data.orderStages} caption="Orders by status" /> : <EmptyState icon="chart" title="Order analytics unavailable" text="This breakdown could not be loaded." />}
        </Panel>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.15fr_1fr_1fr]">
        <Panel eyebrow="Best sellers" title="Top products" subtitle="By units ordered" style={stagger(2)}>
          {data.topProducts?.length ? (
            <BarList
              caption="Top products by units ordered"
              unit=" units"
              items={data.topProducts.map((item) => ({
                key: item.product_id,
                label: item.product_name,
                value: item.total_quantity,
                media: <ProductImage name={item.product_name} className="size-11 shrink-0 rounded-xl" />,
              }))}
            />
          ) : <EmptyState icon="shop" title="No sales yet" text={data.topProducts ? 'Best sellers appear once orders are placed.' : 'Product analytics could not be loaded.'} />}
        </Panel>

        <Panel eyebrow="Inventory" title="Low-stock watch" subtitle="At or below reorder level" style={stagger(3)} bodyClassName="p-0">
          {data.lowStock?.length ? (
            <ul className="divide-y divide-line">
              {data.lowStock.slice(0, 6).map((item) => (
                <li key={`${item.warehouse}-${item.product_id}`} className="flex items-center gap-3 px-5 py-3.5 sm:px-6">
                  <ProductImage name={item.product} className="size-10 shrink-0 rounded-xl" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{item.product}</p>
                    <p className="truncate text-xs text-stone">{item.warehouse}</p>
                  </div>
                  <span className="rounded-full bg-warn-soft px-2.5 py-1 text-xs font-semibold text-warn">{item.quantity} / {item.reorder_level}</span>
                </li>
              ))}
            </ul>
          ) : <EmptyState icon="warehouse" title={data.lowStock ? 'Stock levels look healthy' : 'Inventory data unavailable'} text={data.lowStock ? 'No product is at or below its reorder level.' : 'Low-stock data could not be loaded.'} />}
        </Panel>

        <ActivityPanel activities={data.activities} style={stagger(4)} />
      </section>
    </div>
  )
}

function DriverDashboard({ data, name, onNavigate }) {
  const queue = [...data.deliveries].sort((a, b) => Number(isOpenDelivery(b)) - Number(isOpenDelivery(a))).slice(0, 6)
  const licenceDays = daysUntil(data.profile?.license_expiry)
  return (
    <div className="space-y-6">
      <section className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="panel animate-rise p-7 sm:p-9">
          <Greeting name={name} eyebrow="Delivery overview">
            <p className="mt-5 max-w-lg text-base leading-7 text-stone">Your assigned deliveries, vehicle and availability in one place.</p>
            {onNavigate && <div className="mt-6 flex flex-wrap gap-2"><button type="button" onClick={() => onNavigate('tracking')} className="btn btn-ink">Update tracking <Icon name="arrowRight" className="size-4" /></button><button type="button" onClick={() => onNavigate('deliveries')} className="btn btn-outline">All deliveries</button></div>}
          </Greeting>
        </div>
        <div className="on-dark animate-rise flex flex-col justify-between rounded-[1.5rem] bg-ink p-7 text-paper sm:p-9" style={stagger(1)}>
          <p className="eyebrow text-lime">Still to complete</p>
          <p className="mt-4 text-[7rem] leading-[0.8] font-semibold tracking-[-0.06em]">{data.active}</p>
          <p className="mt-4 text-paper/70">of {data.deliveries.length} assigned deliver{data.deliveries.length === 1 ? 'y' : 'ies'}</p>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="My deliveries" value={data.deliveries.length} icon="truck" style={stagger(2)} />
        <StatTile label="Completed" value={data.completed} icon="check" tone="lime" style={stagger(3)} />
        <StatTile label="Assigned vehicles" value={data.assignments ? data.assignments.length : '—'} hint={data.assignments ? 'Currently assigned to you' : 'Assignments unavailable'} icon="vehicle" tone="cream" style={stagger(4)} />
        <StatTile label="Availability" value={formatLabel(data.profile?.availability_status)} hint={data.profile?.license_no ? `Licence ${data.profile.license_no}` : undefined} icon="idcard" tone="ink" style={stagger(5)} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <Panel eyebrow="Queue" title="Your deliveries" subtitle="Open deliveries first" bodyClassName="p-0" style={stagger(2)}>
          {queue.length ? (
            <ul className="divide-y divide-line">
              {queue.map((delivery) => (
                <li key={delivery.delivery_id} className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
                  <div className="flex items-center gap-3">
                    <span className="grid size-10 place-items-center rounded-full bg-cream"><Icon name="pin" className="size-4" /></span>
                    <div>
                      <p className="font-semibold">Delivery #{delivery.delivery_id} <span className="font-normal text-stone">· Shipment #{delivery.shipment_id}</span></p>
                      <p className="text-sm text-stone">{delivery.delivery_address || 'Address not recorded'}</p>
                    </div>
                  </div>
                  <StatusBadge status={delivery.delivery_status} />
                </li>
              ))}
            </ul>
          ) : <EmptyState icon="truck" title="No deliveries assigned" text="New assignments will appear here." />}
        </Panel>
        <Panel eyebrow="Profile" title="Driver details" style={stagger(3)}>
          {data.profile ? (
            <dl className="space-y-4 text-sm">
              {[
                ['Name', data.profile.name],
                ['Licence', data.profile.license_no],
                ['Licence expiry', data.profile.license_expiry ? `${formatShortDate(data.profile.license_expiry)}${licenceDays !== null ? ` · ${licenceDays >= 0 ? `${licenceDays} days left` : 'expired'}` : ''}` : '—'],
                ['Employment', formatLabel(data.profile.employment_status)],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between gap-4 border-b border-line pb-3 last:border-0 last:pb-0">
                  <dt className="text-stone">{label}</dt>
                  <dd className="text-right font-semibold">{value || '—'}</dd>
                </div>
              ))}
            </dl>
          ) : <EmptyState icon="user" title="Driver profile not found" />}
        </Panel>
      </section>
    </div>
  )
}

function CustomerDashboard({ data, name, onNavigate }) {
  const recentOrders = [...data.orders].sort((a, b) => new Date(b.order_date || 0) - new Date(a.order_date || 0)).slice(0, 4)
  return (
    <div className="space-y-6">
      <section className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="panel animate-rise p-7 sm:p-9">
          <Greeting name={name} eyebrow="Customer overview">
            <p className="mt-5 max-w-lg text-base leading-7 text-stone">Your orders, shipments and invoices — all tracked from checkout to doorstep.</p>
            {onNavigate && (
              <div className="mt-7 flex flex-wrap gap-2">
                <button type="button" onClick={() => onNavigate('shop')} className="btn btn-ink px-6! py-3!">Shop the catalog <Icon name="arrowRight" className="size-4" /></button>
                <button type="button" onClick={() => onNavigate('tracking')} className="btn btn-outline px-6! py-3!">Track a shipment</button>
              </div>
            )}
          </Greeting>
        </div>
        <div className="on-dark animate-rise flex flex-col justify-between rounded-[1.5rem] bg-ink p-7 text-paper sm:p-9" style={stagger(1)}>
          <p className="eyebrow text-lime">On the way to you</p>
          <p className="mt-4 text-[7rem] leading-[0.8] font-semibold tracking-[-0.06em]">{data.openShipments}</p>
          <p className="mt-4 text-paper/70">active shipment{data.openShipments === 1 ? '' : 's'} · {data.delivered} delivered so far</p>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="My orders" value={data.orders.length} icon="box" style={stagger(2)} />
        <StatTile label="Deliveries" value={data.deliveries} icon="truck" tone="cream" style={stagger(3)} />
        <StatTile label="Payments" value={data.payments} icon="card" tone="lime" style={stagger(4)} />
        <StatTile label="Open invoices" value={data.dueInvoices.length} hint={data.dueInvoices.length ? `${formatCurrency(data.dueInvoices.reduce((sum, item) => sum + Number(item.total_amount || 0), 0))} due` : 'Nothing outstanding'} icon="file" tone="ink" style={stagger(5)} />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <Panel eyebrow="Recent" title="Latest orders" bodyClassName="p-0" style={stagger(2)} actions={onNavigate && <button type="button" onClick={() => onNavigate('orders')} className="btn btn-ghost">View all <Icon name="arrowRight" className="size-4" /></button>}>
          {recentOrders.length ? (
            <ul className="divide-y divide-line">
              {recentOrders.map((order) => (
                <li key={order.order_id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
                  <div className="flex items-center gap-4">
                    <div className="flex -space-x-3">
                      {(order.items ?? []).slice(0, 3).map((item) => <ProductImage key={item.product_id} name={item.product_name} className="size-12 rounded-xl ring-2 ring-paper" />)}
                    </div>
                    <div>
                      <p className="font-semibold">Order #{order.order_id}</p>
                      <p className="text-sm text-stone">{formatShortDate(order.order_date)} · {(order.items ?? []).length} product{(order.items ?? []).length === 1 ? '' : 's'}</p>
                    </div>
                  </div>
                  <StatusBadge status={order.order_status} />
                </li>
              ))}
            </ul>
          ) : <EmptyState icon="shop" title="No orders yet" text="Your first order will show up here." action={onNavigate && <button type="button" onClick={() => onNavigate('shop')} className="btn btn-ink">Start shopping</button>} />}
        </Panel>
        <ActivityPanel activities={data.activities} style={stagger(3)} />
      </section>
    </div>
  )
}

function ActivityPanel({ activities, style }) {
  return (
    <Panel eyebrow="Live feed" title="Recent activity" style={style}>
      {activities.length ? (
        <ol className="relative space-y-5 before:absolute before:top-2 before:bottom-2 before:left-[1.05rem] before:w-px before:bg-line">
          {activities.map((activity, index) => (
            <li key={`${activity.title}-${index}`} className="relative flex items-start gap-4">
              <span className={`relative z-10 grid size-[2.1rem] shrink-0 place-items-center rounded-full ${index === 0 ? 'bg-lime text-ink' : 'bg-cream text-graphite'}`}>
                <Icon name={activity.kind} className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-semibold">{activity.title}</p>
                  <time className="eyebrow shrink-0 text-mist">{formatShortDate(activity.date, 'No date')}</time>
                </div>
                <div className="mt-1"><StatusBadge status={activity.status} /></div>
              </div>
            </li>
          ))}
        </ol>
      ) : <EmptyState icon="clock" title="Nothing yet" text="No recent activity is available yet." />}
    </Panel>
  )
}

function DashboardLoading() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading dashboard">
      <div className="grid gap-6 lg:grid-cols-[1.35fr_1fr]"><div className="skeleton h-80 rounded-[1.5rem]!" /><div className="h-80 rounded-[1.5rem] bg-ink/90" /></div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[1, 2, 3, 4].map((item) => <div className="skeleton h-40 rounded-[1.4rem]!" key={item} />)}</div>
      <div className="grid gap-6 xl:grid-cols-2"><div className="skeleton h-72 rounded-[1.5rem]!" /><div className="skeleton h-72 rounded-[1.5rem]!" /></div>
    </div>
  )
}

export default Dashboard
