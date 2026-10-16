import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'

function formatLabel(value) {
  return String(value ?? 'Unknown').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function MetricCard({ label, value, detail }) {
  return <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><p className="text-sm font-medium text-slate-500">{label}</p><p className="mt-3 text-2xl font-bold tracking-tight text-slate-950">{value}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></article>
}

function Analytics({ session, onAuthExpired }) {
  const [summary, setSummary] = useState(null)
  const [shipmentStatuses, setShipmentStatuses] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadAnalytics = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [summaryData, statusData] = await Promise.all([apiGet('/dashboard/summary', session.accessToken), apiGet('/analytics/shipment-status', session.accessToken)])
      if (!summaryData || typeof summaryData !== 'object' || !Array.isArray(statusData)) throw new Error('Unexpected response from the analytics API.')
      setSummary(summaryData)
      setShipmentStatuses(statusData)
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

  const totalStatusCount = useMemo(() => shipmentStatuses.reduce((sum, item) => sum + (Number(item.count) || 0), 0), [shipmentStatuses])
  const maxCount = Math.max(1, ...shipmentStatuses.map((item) => Number(item.count) || 0))

  return <div className="mx-auto max-w-7xl space-y-6">
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-sm font-medium text-cyan-700">Operations insight</p><h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-950">Analytics</h2><p className="mt-2 text-sm text-slate-500">Current shipment distribution and supported operational totals.</p></div><button type="button" onClick={loadAnalytics} disabled={loading} className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60">{loading ? 'Refreshing...' : 'Refresh analytics'}</button></div>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="Total orders" value={loading ? '-' : summary?.total_orders ?? '-'} detail="From dashboard summary" /><MetricCard label="Total shipments" value={loading ? '-' : summary?.total_shipments ?? '-'} detail="From dashboard summary" /><MetricCard label="Successful payments" value={loading ? '-' : summary?.successful_payments ?? '-'} detail="From dashboard summary" /><MetricCard label="Pending deliveries" value={loading ? '-' : summary?.pending_deliveries ?? '-'} detail="From dashboard summary" /></div>
    {error && <div role="alert" className="flex flex-col gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-sm text-rose-700">{error}</p><button type="button" onClick={loadAnalytics} className="shrink-0 rounded-lg border border-rose-200 bg-white px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-100">Try again</button></div>}
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"><div><h3 className="font-semibold text-slate-900">Shipment status breakdown</h3><p className="mt-1 text-sm text-slate-500">{loading ? 'Loading shipment status data...' : `${totalStatusCount} shipment${totalStatusCount === 1 ? '' : 's'} across ${shipmentStatuses.length} status${shipmentStatuses.length === 1 ? '' : 'es'}`}</p></div>
      {loading ? <div className="mt-6 space-y-5" aria-label="Loading shipment analytics">{[1, 2, 3].map((item) => <div key={item} className="h-10 animate-pulse rounded-lg bg-slate-100" />)}</div>
        : error ? <div className="py-12 text-center"><p className="font-medium text-slate-700">Shipment analytics could not be loaded.</p><p className="mt-1 text-sm text-slate-500">Resolve the error above and try again.</p></div>
          : shipmentStatuses.length === 0 ? <div className="py-12 text-center"><h3 className="font-semibold text-slate-900">No shipment analytics yet</h3><p className="mt-1 text-sm text-slate-500">The chart will appear when shipment records are available.</p></div>
            : <div className="mt-6 space-y-5">{shipmentStatuses.map((item) => { const count = Number(item.count) || 0; const percentage = Math.round((count / totalStatusCount) * 100); return <div key={item.status ?? 'unknown'}><div className="mb-2 flex items-center justify-between gap-4"><span className="text-sm font-medium text-slate-700">{formatLabel(item.status)}</span><span className="text-sm font-semibold text-slate-900">{count} <span className="font-normal text-slate-500">({percentage}%)</span></span></div><div className="h-3 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-cyan-500 transition-all" style={{ width: `${(count / maxCount) * 100}%` }} /></div></div> })}</div>}
    </section>
  </div>
}

export default Analytics
