import { useEffect, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'

const ROLE_LABELS = { 1: 'system overview', 2: 'operations overview', 3: 'delivery overview', 4: 'customer overview' }

function Dashboard({ session, onAuthExpired }) {
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
  if (state.error) return <DashboardError message={state.error} onRetry={() => setRefreshKey((key) => key + 1)} />
  if (!state.data) return null

  return <div className="mx-auto max-w-7xl space-y-6">
    <div><p className="text-sm font-semibold uppercase tracking-[0.16em] text-cyan-700">{ROLE_LABELS[roleId]}</p><h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Good to see you, {session.user.username}.</h2><p className="mt-2 text-slate-600">Here is the latest view of your logistics activity.</p></div>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{state.data.cards.map((card) => <MetricCard card={card} key={card.label} />)}</div>
    <div className="grid gap-6 xl:grid-cols-[1.35fr_0.65fr]"><ActivityPanel activities={state.data.activities} /><SummaryPanel items={state.data.summary} /></div>
  </div>
}

async function getDashboardData(roleId, token) {
  if (roleId === 1 || roleId === 2) {
    const [summary, shipments, deliveries, shipmentStatus] = await Promise.all([apiGet('/dashboard/summary', token), apiGet('/shipments', token), apiGet('/deliveries', token), apiGet('/analytics/shipment-status', token)])
    return { cards: [{ label: 'Total orders', value: summary.total_orders, tone: 'cyan' }, { label: 'Active shipments', value: summary.total_shipments, tone: 'violet' }, { label: 'Successful payments', value: summary.successful_payments, tone: 'emerald' }, { label: 'Pending deliveries', value: summary.pending_deliveries, tone: 'amber' }], activities: shipmentActivities(shipments, deliveries), summary: shipmentStatus.map((item) => ({ label: formatLabel(item.status), value: item.count })) }
  }
  if (roleId === 3) {
    const [deliveries, driverProfiles] = await Promise.all([apiGet('/deliveries', token), apiGet('/drivers/me', token)])
    const vehicles = []
    const completed = deliveries.filter((delivery) => delivery.delivery_status === 'DELIVERED').length
    const active = deliveries.filter((delivery) => delivery.delivery_status !== 'DELIVERED').length
    return { cards: [{ label: 'My deliveries', value: deliveries.length, tone: 'cyan' }, { label: 'To complete', value: active, tone: 'amber' }, { label: 'Completed', value: completed, tone: 'emerald' }, { label: 'Assigned vehicles', value: vehicles.length, tone: 'violet' }], activities: deliveries.map((item) => ({ title: `Delivery #${item.delivery_id}`, detail: `${formatLabel(item.delivery_status)} · Shipment #${item.shipment_id}`, date: item.delivery_date })), summary: driverProfiles.map((item) => ({ label: 'Availability', value: formatLabel(item.availability_status) })).concat(vehicles.map((item) => ({ label: item.registration_no, value: formatLabel(item.status) }))) }
  }
  const [orders, shipments, deliveries, payments, invoices] = await Promise.all([apiGet('/orders', token), apiGet('/shipments', token), apiGet('/deliveries', token), apiGet('/payments', token), apiGet('/invoices', token)])
  const openShipments = shipments.filter((item) => !['DELIVERED', 'CANCELLED'].includes(item.shipment_status)).length
  const dueInvoices = invoices.filter((item) => item.invoice_status !== 'PAID' && item.invoice_status !== 'CANCELLED').length
  return { cards: [{ label: 'My orders', value: orders.length, tone: 'cyan' }, { label: 'Active shipments', value: openShipments, tone: 'violet' }, { label: 'Deliveries', value: deliveries.length, tone: 'emerald' }, { label: 'Open invoices', value: dueInvoices, tone: 'amber' }], activities: shipmentActivities(shipments, deliveries, orders), summary: [{ label: 'Payments', value: payments.length }, { label: 'Invoices', value: invoices.length }, { label: 'Delivered', value: shipments.filter((item) => item.shipment_status === 'DELIVERED').length }] }
}

function shipmentActivities(shipments, deliveries, orders = []) {
  return [...shipments.map((item) => ({ title: `Shipment #${item.shipment_id}`, detail: formatLabel(item.shipment_status), date: item.estimated_delivery || item.shipment_date })), ...deliveries.map((item) => ({ title: `Delivery #${item.delivery_id}`, detail: formatLabel(item.delivery_status), date: item.delivery_date })), ...orders.map((item) => ({ title: `Order #${item.order_id}`, detail: formatLabel(item.order_status), date: item.order_date }))].sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0)).slice(0, 6)
}

function MetricCard({ card }) { const tones = { cyan: 'border-cyan-100 bg-cyan-50 text-cyan-700', violet: 'border-violet-100 bg-violet-50 text-violet-700', emerald: 'border-emerald-100 bg-emerald-50 text-emerald-700', amber: 'border-amber-100 bg-amber-50 text-amber-700' }; return <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><div className={`grid size-10 place-items-center rounded-xl border text-lg font-bold ${tones[card.tone]}`}>↗</div><p className="mt-5 text-sm font-medium text-slate-500">{card.label}</p><p className="mt-1 text-3xl font-semibold tracking-tight text-slate-950">{card.value}</p></article> }
function ActivityPanel({ activities }) { return <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"><div><p className="font-semibold text-slate-950">Recent activity</p><p className="mt-1 text-sm text-slate-500">Latest records from your workspace.</p></div>{activities.length ? <div className="mt-5 divide-y divide-slate-100">{activities.map((activity, index) => <div className="flex items-center justify-between gap-4 py-4" key={`${activity.title}-${index}`}><div className="min-w-0"><p className="font-medium text-slate-800">{activity.title}</p><p className="mt-1 truncate text-sm text-slate-500">{activity.detail}</p></div><time className="shrink-0 text-xs font-medium text-slate-400">{formatDate(activity.date)}</time></div>)}</div> : <EmptyState text="No recent activity is available yet." />}</section> }
function SummaryPanel({ items }) { return <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"><p className="font-semibold text-slate-950">At a glance</p><p className="mt-1 text-sm text-slate-500">Current status across your workspace.</p>{items.length ? <div className="mt-5 space-y-3">{items.slice(0, 6).map((item, index) => <div className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3" key={`${item.label}-${index}`}><span className="text-sm text-slate-600">{item.label}</span><span className="text-sm font-semibold text-slate-900">{item.value}</span></div>)}</div> : <EmptyState text="No summary data is available yet." />}</section> }
function DashboardLoading() { return <div className="mx-auto max-w-7xl animate-pulse space-y-6"><div className="h-24 rounded-2xl bg-slate-200" /><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[1, 2, 3, 4].map((item) => <div className="h-40 rounded-2xl bg-slate-200" key={item} />)}</div><div className="h-72 rounded-2xl bg-slate-200" /></div> }
function DashboardError({ message, onRetry }) { return <div className="mx-auto max-w-xl rounded-2xl border border-red-200 bg-white p-7 shadow-sm"><p className="text-lg font-semibold text-slate-950">Dashboard unavailable</p><p className="mt-2 leading-7 text-slate-600">{message}</p><button className="mt-6 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800" onClick={onRetry}>Try again</button></div> }
function EmptyState({ text }) { return <p className="mt-8 rounded-xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">{text}</p> }
function formatLabel(value) { return String(value || 'Unknown').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase()) }
function formatDate(value) { if (!value) return 'No date'; const date = new Date(value); return Number.isNaN(date.valueOf()) ? 'No date' : new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' }).format(date) }

export default Dashboard
