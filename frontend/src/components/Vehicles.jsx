import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApiError, apiGet } from '../services/apiClient.js'

function formatLabel(value) {
  if (!value) return '-'
  return String(value).replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? String(value) : new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(date)
}

function formatCapacity(value) {
  const capacity = Number(value)
  return Number.isFinite(capacity) ? `${capacity.toLocaleString('en-IN')} kg` : '-'
}

function StatusBadge({ status }) {
  const normalized = String(status ?? '').toUpperCase()
  const tone = ['ACTIVE', 'AVAILABLE'].includes(normalized)
    ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/20'
    : normalized.includes('MAINTENANCE') || normalized.includes('SERVICE')
      ? 'bg-amber-50 text-amber-700 ring-amber-600/20'
      : normalized === 'INACTIVE' || normalized.includes('OUT_OF_SERVICE')
        ? 'bg-rose-50 text-rose-700 ring-rose-600/20'
        : 'bg-slate-100 text-slate-700 ring-slate-500/20'
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${tone}`}>{formatLabel(status)}</span>
}

function SummaryCard({ label, value, detail }) {
  return <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><p className="text-sm font-medium text-slate-500">{label}</p><p className="mt-3 text-2xl font-bold tracking-tight text-slate-950">{value}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></article>
}

function Vehicles({ session, onAuthExpired }) {
  const [vehicles, setVehicles] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  const loadVehicles = useCallback(async (isRefresh = false) => {
    isRefresh ? setRefreshing(true) : setLoading(true)
    setError('')
    try {
      const data = await apiGet('/vehicles', session.accessToken)
      if (!Array.isArray(data)) throw new Error('Unexpected response from the vehicles API.')
      setVehicles(data)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onAuthExpired()
        return
      }
      setError(err instanceof ApiError && err.status === 403 ? 'You do not have permission to view vehicles.' : err.message || 'Unable to load vehicles.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [session.accessToken, onAuthExpired])

  useEffect(() => { loadVehicles() }, [loadVehicles])

  const filteredVehicles = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return vehicles
    return vehicles.filter((vehicle) => [vehicle.vehicle_id, vehicle.registration_no, vehicle.vehicle_type, vehicle.fuel_type, vehicle.status].some((value) => String(value ?? '').toLowerCase().includes(query)))
  }, [vehicles, search])

  const activeCount = vehicles.filter((vehicle) => ['ACTIVE', 'AVAILABLE'].includes(String(vehicle.status ?? '').toUpperCase())).length
  const maintenanceCount = vehicles.filter((vehicle) => ['MAINTENANCE', 'SERVICE'].some((status) => String(vehicle.status ?? '').toUpperCase().includes(status))).length

  return <div className="mx-auto max-w-7xl space-y-6">
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
      <div><p className="text-sm font-medium text-cyan-700">Fleet management</p><h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-950">Vehicles</h2><p className="mt-2 text-sm text-slate-500">Review current fleet capacity, fuel type, and availability.</p></div>
      <button type="button" onClick={() => loadVehicles(true)} disabled={loading || refreshing} className="inline-flex items-center justify-center rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60">{refreshing ? 'Refreshing...' : 'Refresh vehicles'}</button>
    </div>
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"><SummaryCard label="Total vehicles" value={loading ? '-' : vehicles.length} detail="Fleet records available" /><SummaryCard label="Active vehicles" value={loading ? '-' : activeCount} detail="Active or available" /><SummaryCard label="In maintenance" value={loading ? '-' : maintenanceCount} detail="Maintenance or service status" /></div>
    {error && <div role="alert" className="flex flex-col gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-sm text-rose-700">{error}</p><button type="button" onClick={() => loadVehicles()} className="shrink-0 rounded-lg border border-rose-200 bg-white px-3 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-100">Try again</button></div>}
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-col gap-3 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="font-semibold text-slate-900">Fleet records</h3><p className="mt-1 text-sm text-slate-500">{loading ? 'Loading vehicle records...' : `${filteredVehicles.length} record${filteredVehicles.length === 1 ? '' : 's'} found`}</p></div><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search vehicles..." aria-label="Search vehicles" className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100 sm:max-w-xs" /></div>
      {loading ? <div className="space-y-3 p-5" aria-label="Loading vehicles">{[1, 2, 3, 4].map((item) => <div key={item} className="h-12 animate-pulse rounded-lg bg-slate-100" />)}</div>
        : error ? <div className="p-10 text-center"><p className="font-medium text-slate-700">Vehicle records could not be loaded.</p><p className="mt-1 text-sm text-slate-500">Resolve the error above and try again.</p></div>
          : filteredVehicles.length === 0 ? <div className="px-5 py-14 text-center"><h3 className="font-semibold text-slate-900">{search ? 'No matching vehicles' : 'No vehicles yet'}</h3><p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">{search ? 'Try a registration number, type, fuel type, or status.' : 'Vehicle records will appear here when available.'}</p></div>
            : <div className="overflow-x-auto"><table className="w-full min-w-[860px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500"><tr><th className="px-5 py-3 font-semibold">Vehicle ID</th><th className="px-5 py-3 font-semibold">Registration</th><th className="px-5 py-3 font-semibold">Type</th><th className="px-5 py-3 font-semibold">Capacity</th><th className="px-5 py-3 font-semibold">Fuel</th><th className="px-5 py-3 font-semibold">Purchased</th><th className="px-5 py-3 font-semibold">Status</th></tr></thead><tbody className="divide-y divide-slate-100">{filteredVehicles.map((vehicle, index) => <tr key={vehicle.vehicle_id ?? index} className="transition hover:bg-slate-50"><td className="whitespace-nowrap px-5 py-4 font-semibold text-slate-900">#{vehicle.vehicle_id ?? '-'}</td><td className="whitespace-nowrap px-5 py-4 font-medium text-slate-900">{vehicle.registration_no ?? '-'}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">{formatLabel(vehicle.vehicle_type)}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">{formatCapacity(vehicle.capacity)}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">{formatLabel(vehicle.fuel_type)}</td><td className="whitespace-nowrap px-5 py-4 text-slate-600">{formatDate(vehicle.purchase_date)}</td><td className="whitespace-nowrap px-5 py-4"><StatusBadge status={vehicle.status} /></td></tr>)}</tbody></table></div>}
    </section>
  </div>
}

export default Vehicles
